"""Supprimer definitivement un salon ou un compte, depuis l'administration.

---------------------------------------------------------------------------
Pourquoi une procedure a part, et pas le bouton « Supprimer » de Django
---------------------------------------------------------------------------

Le bouton de Django travaille sur l'alias `default`, soumis aux politiques
RLS : hors contexte salon, il ne voit aucune des donnees du salon. Et
plusieurs relations sont en PROTECT (un rendez-vous protege sa prestation,
sa cliente, sa prestataire ; une facture, son abonnement) : une cascade
naive echoue a mi-chemin. Ce bouton est donc retire pour les salons et les
comptes, et remplace par ceci :

  - tout se passe sur l'alias `admin`, dans **une seule transaction** :
    soit tout part, soit rien ;
  - les tables du salon sont videes dans l'ordre de leurs dependances
    (qui reference d'abord, reference ensuite), calcule a partir des
    modeles — un modele ajoute demain est pris en compte sans y penser ;
  - les fichiers (photos, preuves de versement) ne sont effaces du disque
    qu'apres la validation (voir `media/signals.py`) ;
  - la trace d'audit est ecrite dans la meme transaction, sans lien vers
    ce qu'elle decrit : elle survit a la suppression ;
  - les garde-fous (salon en ligne, dernier proprietaire, compte
    d'administration, soi-meme) sont verifies ici, pas seulement a l'ecran.

Ce qui reste volontairement : le journal d'audit et le grand livre de la
plateforme (`platformledger`), dont les lignes perdent leur lien vers le
salon mais gardent les montants encaisses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.apps import apps as registre
from django.db import transaction

from apps.common.admin import ADMIN_DB

logger = logging.getLogger(__name__)


class SuppressionRefusee(Exception):
    """Un garde-fou s'oppose a la suppression. Le message dit lequel."""


# ---------------------------------------------------------------------------
# L'ordre des tables
# ---------------------------------------------------------------------------


def _modeles_du_salon() -> list:
    """Les modeles d'un salon, ordonnes : ceux qui referencent d'abord.

    Tri topologique sur les cles etrangeres entre modeles de salon. Une
    cle vers soi-meme est ignoree (le collecteur de Django la gere dans la
    table). Un cycle eventuel est place a la fin : le collecteur le
    traitera, ou la transaction s'annulera entiere.
    """
    from apps.common.models import TenantOwnedModel

    modeles = [
        m
        for m in registre.get_models()
        if issubclass(m, TenantOwnedModel) and not m._meta.proxy and m._meta.managed
    ]
    ensemble = set(modeles)
    # dependances[M] : les modeles que M reference (a supprimer apres M).
    dependances = {
        m: {
            f.related_model
            for f in m._meta.concrete_fields
            if f.is_relation and f.related_model in ensemble and f.related_model is not m
        }
        for m in modeles
    }
    referents = {m: set() for m in modeles}
    for m, cibles in dependances.items():
        for cible in cibles:
            referents[cible].add(m)

    ordre, restants = [], set(modeles)
    while restants:
        # Un modele peut partir quand plus personne ne le reference.
        libres = sorted(
            (m for m in restants if not (referents[m] & restants)),
            key=lambda m: m._meta.label,
        )
        if not libres:
            logger.warning(
                "Cycle entre modeles de salon : %s", sorted(m._meta.label for m in restants)
            )
            ordre.extend(sorted(restants, key=lambda m: m._meta.label))
            break
        ordre.extend(libres)
        restants -= set(libres)
    return ordre


# ---------------------------------------------------------------------------
# Le salon
# ---------------------------------------------------------------------------


@dataclass
class InventaireSalon:
    comptes: dict[str, int] = field(default_factory=dict)
    # Comptes d'equipe qui n'appartiennent qu'a ce salon.
    comptes_equipe: list = field(default_factory=list)
    # Comptes de clientes qui ne sont liees qu'a ce salon.
    comptes_clientes: list = field(default_factory=list)
    domaines: list[str] = field(default_factory=list)
    fichiers: int = 0


def _est_administrateur(user) -> bool:
    return bool(user.is_superuser or user.is_staff or user.is_platform_admin)


def inventaire_salon(tenant) -> InventaireSalon:
    """Ce qu'effacerait la suppression : a montrer avant de confirmer."""
    from apps.accounts.models import Membership, User
    from apps.clients.models import ClientSalonLink
    from apps.domains.models import Domain
    from apps.media.models import MediaAsset

    inv = InventaireSalon()
    for modele in _modeles_du_salon():
        n = modele.all_tenants.using(ADMIN_DB).filter(tenant_id=tenant.id).count()
        if n:
            inv.comptes[str(modele._meta.verbose_name_plural)] = n
    inv.domaines = list(
        Domain.objects.using(ADMIN_DB)
        .filter(tenant_id=tenant.id)
        .values_list("hostname", flat=True)
    )
    inv.fichiers = (
        MediaAsset.all_tenants.using(ADMIN_DB).filter(tenant_id=tenant.id).exclude(file="").count()
    )

    equipe = User.objects.using(ADMIN_DB).filter(memberships__tenant_id=tenant.id).distinct()
    for user in equipe:
        autres = Membership.objects.using(ADMIN_DB).filter(user=user).exclude(tenant_id=tenant.id)
        if not autres.exists() and not _est_administrateur(user):
            inv.comptes_equipe.append(user)

    clientes = User.objects.using(ADMIN_DB).filter(salon_links__tenant_id=tenant.id).distinct()
    for user in clientes:
        ailleurs = (
            ClientSalonLink.objects.using(ADMIN_DB).filter(user=user).exclude(tenant_id=tenant.id)
        )
        membre = Membership.objects.using(ADMIN_DB).filter(user=user).exists()
        if not ailleurs.exists() and not membre and not _est_administrateur(user):
            inv.comptes_clientes.append(user)
    return inv


def supprimer_salon(tenant, *, administrateur, motif: str, avec_comptes: bool) -> dict:
    """Efface un salon et tout ce qui lui appartient. Irreversible.

    `avec_comptes` : efface aussi les comptes (equipe, clientes) qui
    n'appartenaient qu'a ce salon. Un compte d'administration n'est jamais
    efface par ce biais.
    """
    from apps.accounts.models import Membership
    from apps.audit.models import AuditLog
    from apps.clients.models import ClientSalonLink
    from apps.domains.models import Domain
    from apps.tenants.models import Tenant

    motif = (motif or "").strip()
    if len(motif) < 10:
        raise SuppressionRefusee("Indiquez le motif de la suppression (10 caractères au moins).")

    with transaction.atomic(using=ADMIN_DB):
        salon = Tenant.objects.using(ADMIN_DB).select_for_update().filter(pk=tenant.pk).first()
        if salon is None:
            raise SuppressionRefusee("Ce salon n'existe plus.")
        if salon.status == Tenant.Status.ACTIVE:
            raise SuppressionRefusee(
                "Ce salon est en ligne. Suspendez-le d'abord : sa page disparaît, "
                "et vous gardez le temps de revenir en arrière."
            )

        inv = inventaire_salon(salon)
        comptes = (inv.comptes_equipe + inv.comptes_clientes) if avec_comptes else []
        instance_whatsapp = _instance_whatsapp(salon)

        # La trace d'abord, sans lien vers le salon : elle doit lui survivre.
        AuditLog.objects.using(ADMIN_DB).create(
            tenant=None,
            actor_user=administrateur,
            action=AuditLog.Action.TENANT_DELETED,
            resource_type="tenants.tenant",
            resource_id=str(salon.pk),
            metadata={
                "nom": salon.name,
                "identifiant": salon.slug,
                "motif": motif[:500],
                "donnees": inv.comptes,
                "domaines": inv.domaines,
                "fichiers": inv.fichiers,
                "comptes_supprimes": len(comptes),
            },
        )

        for modele in _modeles_du_salon():
            modele.all_tenants.using(ADMIN_DB).filter(tenant_id=salon.pk).delete()
        ClientSalonLink.objects.using(ADMIN_DB).filter(tenant_id=salon.pk).delete()
        Membership.objects.using(ADMIN_DB).filter(tenant_id=salon.pk).delete()
        # Un par un : le signal de `Domain` vide le cache de resolution.
        for domaine in Domain.objects.using(ADMIN_DB).filter(tenant_id=salon.pk):
            domaine.delete(using=ADMIN_DB)
        for compte in comptes:
            compte.delete(using=ADMIN_DB)
        salon.delete(using=ADMIN_DB)

        if instance_whatsapp:
            transaction.on_commit(lambda: _deconnecter_whatsapp(instance_whatsapp), using=ADMIN_DB)

    return {"donnees": inv.comptes, "comptes": len(comptes), "fichiers": inv.fichiers}


def _instance_whatsapp(salon) -> str:
    from apps.assistants.models import AssistantReglages

    reglages = AssistantReglages.all_tenants.using(ADMIN_DB).filter(tenant_id=salon.pk).first()
    return reglages.whatsapp_instance if reglages else ""


def _deconnecter_whatsapp(instance: str) -> None:
    """Le numero du salon ne doit pas rester relie a une instance orpheline."""
    from apps.assistants import evolution

    if not evolution.configuree():
        return
    try:
        evolution.supprimer(instance)
    except Exception:  # noqa: BLE001 - le salon est parti quoi qu'il arrive
        logger.exception("Instance WhatsApp %s non supprimée.", instance)


# ---------------------------------------------------------------------------
# Le compte
# ---------------------------------------------------------------------------


def masquer(email: str) -> str:
    """« j***@gmail.com » : assez pour retrouver une demande, pas plus."""
    nom, _, domaine = (email or "").partition("@")
    return f"{nom[:1]}***@{domaine}" if domaine else "***"


def obstacles_compte(user, administrateur) -> list[str]:
    """Pourquoi ce compte ne peut pas etre supprime, s'il ne le peut pas."""
    from apps.accounts.models import Membership

    raisons = []
    if user.pk == getattr(administrateur, "pk", None):
        raisons.append("Vous ne pouvez pas supprimer votre propre compte.")
    if _est_administrateur(user):
        raisons.append(
            "C'est un compte d'administration : retirez-lui d'abord ses droits "
            "(équipe, superutilisateur, administrateur plateforme)."
        )
    proprietaire = Membership.Role.OWNER
    for adhesion in Membership.objects.using(ADMIN_DB).filter(user=user, role=proprietaire):
        autres = (
            Membership.objects.using(ADMIN_DB)
            .filter(tenant_id=adhesion.tenant_id, role=proprietaire)
            .exclude(user=user)
        )
        if not autres.exists():
            raisons.append(
                f"Seul propriétaire du salon « {adhesion.tenant} » : supprimez le salon "
                "ou confiez-le d'abord à un autre propriétaire."
            )
    return raisons


def supprimer_compte(user, *, administrateur, motif: str) -> None:
    """Efface un compte et ce qui n'appartient qu'a lui. Irreversible.

    Ses adhesions, appareils, notifications et espace cliente partent ; ce
    qu'il a fait dans les salons reste, sans son nom (rendez-vous, gestes
    d'abonnement, journal).
    """
    from apps.accounts.models import User
    from apps.audit.models import AuditLog

    motif = (motif or "").strip()
    if len(motif) < 10:
        raise SuppressionRefusee("Indiquez le motif de la suppression (10 caractères au moins).")

    with transaction.atomic(using=ADMIN_DB):
        compte = User.objects.using(ADMIN_DB).select_for_update().filter(pk=user.pk).first()
        if compte is None:
            raise SuppressionRefusee("Ce compte n'existe plus.")
        raisons = obstacles_compte(compte, administrateur)
        if raisons:
            raise SuppressionRefusee(" ".join(raisons))

        AuditLog.objects.using(ADMIN_DB).create(
            tenant=None,
            actor_user=administrateur,
            action=AuditLog.Action.USER_DELETED,
            resource_type="accounts.user",
            resource_id=str(compte.pk),
            metadata={"compte": masquer(compte.email), "motif": motif[:500]},
        )
        compte.delete(using=ADMIN_DB)
