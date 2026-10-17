"""Domaines personnalises : relier au mini-site un domaine que le salon possede.

---------------------------------------------------------------------------
Le parcours
---------------------------------------------------------------------------

  1. **Demande** : le salon indique `monsalon.com`. Une `DomainClaim` est
     creee avec un jeton aleatoire. Rien n'est route : taper un nom ne
     suffit jamais a le pointer sur un salon.
  2. **Preuve** : chez son registraire, le salon ajoute
       - un enregistrement TXT `_beauty-salon.monsalon.com` = le jeton ;
       - le pointage du domaine vers la plateforme (CNAME vers son
         sous-domaine, ou A vers l'adresse du serveur pour un domaine nu).
  3. **Verification** : on lit le DNS. Le TXT prouve le controle du domaine
     (seul qui gere sa zone peut l'ecrire) ; le pointage prouve que le
     trafic arrivera bien chez nous. Les deux sont exiges.
  4. **Connexion** : une ligne `Domain`, unique par nom, est creee. C'est
     elle qui route le trafic ; Caddy n'obtient un certificat que pour un
     domaine verifie (voir `views.certificat_autorise`).

Plusieurs salons peuvent deposer une demande pour le meme nom : seul le
premier a produire la preuve l'obtient, et les autres recoivent « deja relie ».

---------------------------------------------------------------------------
Pause
---------------------------------------------------------------------------

Sans Pro (descente, fin de periode, fonction coupee), le domaine reste en
base mais ne sert plus le mini-site : ses visiteurs sont renvoyes vers le
sous-domaine du salon. Il revient tel quel au retour a Pro.
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.db import bypass_tenant_context, tenant_context

from .models import Domain, DomainClaim
from .services import invalidate_hostname, platform_hostname

logger = logging.getLogger(__name__)

PREFIXE_TXT = "_beauty-salon"
DUREE_CACHE_DROIT = 120
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class DomaineRefuse(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Le nom
# ---------------------------------------------------------------------------


def normaliser(saisie: str) -> str:
    """`https://Www.MonSalon.com/` -> `www.monsalon.com`, ou DomaineRefuse."""
    nom = (saisie or "").strip().lower()
    nom = re.sub(r"^[a-z]+://", "", nom).split("/")[0].split("?")[0].rstrip(".")
    if ":" in nom or "@" in nom or " " in nom:
        raise DomaineRefuse(
            "Indiquez seulement le nom de domaine, par exemple monsalon.com.", "nom_invalide"
        )
    try:
        nom = nom.encode("idna").decode("ascii")
    except UnicodeError as erreur:
        raise DomaineRefuse("Ce nom de domaine n'est pas valide.", "nom_invalide") from erreur

    labels = nom.split(".")
    if (
        len(nom) > 253
        or len(labels) < 2
        or not all(_LABEL.match(label) for label in labels)
        or not re.match(r"^(xn--)?[a-z][a-z0-9-]*$", labels[-1])
    ):
        raise DomaineRefuse("Ce nom de domaine n'est pas valide.", "nom_invalide")

    plateforme = settings.PLATFORM_DOMAIN.lower()
    if nom == plateforme or nom.endswith(f".{plateforme}") or nom in ("localhost",):
        raise DomaineRefuse(
            "Ce domaine appartient à la plateforme : votre adresse gratuite existe déjà.",
            "domaine_plateforme",
        )
    return nom


def est_domaine_nu(nom: str) -> bool:
    """`monsalon.com` (nu) ou `www.monsalon.com` (sous-domaine).

    Approximation par le nombre de labels : un domaine sous un suffixe a deux
    niveaux (`monsalon.co.uk`) sera traite comme un sous-domaine ; les deux
    consignes restent valables, seule la recommandation change.
    """
    return len(nom.split(".")) == 2


def consignes(demande: DomainClaim, slug: str) -> dict:
    """Les deux enregistrements a creer chez le registraire."""
    nu = est_domaine_nu(demande.hostname)
    ips = adresses_de_la_plateforme()
    return {
        "txt": {"type": "TXT", "nom": f"{PREFIXE_TXT}.{demande.hostname}", "valeur": demande.token},
        "routage": (
            {"type": "A", "nom": demande.hostname, "valeur": ips[0] if ips else ""}
            if nu
            else {"type": "CNAME", "nom": demande.hostname, "valeur": platform_hostname(slug)}
        ),
    }


# ---------------------------------------------------------------------------
# Le DNS
# ---------------------------------------------------------------------------


@dataclass
class Lecteur:
    """Lecture DNS, remplacable dans les tests."""

    def txt(self, nom: str) -> list[str]:
        import dns.exception
        import dns.resolver

        try:
            reponse = dns.resolver.resolve(nom, "TXT", lifetime=6)
        except (dns.exception.DNSException, OSError):
            return []
        return [b"".join(rdata.strings).decode("utf-8", "replace") for rdata in reponse]

    def adresses(self, nom: str) -> set[str]:
        import dns.exception
        import dns.resolver

        try:
            reponse = dns.resolver.resolve(nom, "A", lifetime=6)
        except (dns.exception.DNSException, OSError):
            return set()
        return {rdata.address for rdata in reponse}


LECTEUR = Lecteur()


def adresses_de_la_plateforme() -> list[str]:
    """Les adresses IPv4 du serveur : reglage explicite, sinon le DNS de la plateforme."""
    configurees = [ip for ip in getattr(settings, "PLATFORM_PUBLIC_IPS", []) if ip]
    if configurees:
        return configurees
    return sorted(LECTEUR.adresses(settings.PLATFORM_DOMAIN))


# ---------------------------------------------------------------------------
# Les gestes
# ---------------------------------------------------------------------------


def demander(tenant_id, saisie: str, utilisateur) -> DomainClaim:
    nom = normaliser(saisie)
    if Domain.objects.filter(hostname=nom).exclude(tenant_id=tenant_id).exists():
        # Meme reponse que le domaine soit a un autre salon ou non : on ne
        # dit pas a qui il est.
        raise DomaineRefuse("Ce domaine est déjà relié à un autre site.", "deja_pris")
    demande, creee = DomainClaim.objects.get_or_create(
        tenant_id=tenant_id,
        hostname=nom,
        defaults={"token": f"bs-{secrets.token_hex(16)}", "requested_by": utilisateur},
    )
    if creee:
        _journaliser("DOMAIN_CLAIMED", tenant_id, utilisateur, demande)
    return demande


def verifier(demande: DomainClaim, utilisateur, lecteur: Lecteur | None = None) -> DomainClaim:
    """Lit le DNS ; relie le domaine si la preuve et le pointage y sont."""
    lecteur = lecteur or LECTEUR
    demande.last_checked_at = timezone.now()

    valeurs = lecteur.txt(f"{PREFIXE_TXT}.{demande.hostname}")
    if demande.token not in [valeur.strip().strip('"') for valeur in valeurs]:
        return _echec(
            demande,
            "txt_absent" if not valeurs else "txt_incorrect",
            "L'enregistrement TXT de vérification est introuvable ou différent. "
            "La propagation DNS peut prendre jusqu'à quelques heures.",
        )

    attendues = set(adresses_de_la_plateforme())
    if not attendues or not (lecteur.adresses(demande.hostname) & attendues):
        return _echec(
            demande,
            "routage",
            "Le domaine ne pointe pas encore vers la plateforme. Ajoutez "
            "l'enregistrement de routage indiqué, puis réessayez.",
        )

    try:
        with transaction.atomic():
            Domain.objects.create(
                tenant_id=demande.tenant_id,
                hostname=demande.hostname,
                kind=Domain.Kind.CUSTOM_DOMAIN,
                is_primary=False,
                verified_at=timezone.now(),
                active=True,
            )
    except IntegrityError:
        # Deja relie a ce salon : rien a faire. A un autre : refuse.
        if not Domain.objects.filter(
            hostname=demande.hostname, tenant_id=demande.tenant_id
        ).exists():
            return _echec(demande, "deja_pris", "Ce domaine est déjà relié à un autre site.")

    demande.status = DomainClaim.Status.CONNECTED
    demande.last_error = ""
    demande.save(update_fields=["status", "last_error", "last_checked_at", "updated_at"])
    invalidate_hostname(demande.hostname)
    _journaliser("DOMAIN_CONNECTED", demande.tenant_id, utilisateur, demande)
    return demande


def retirer(demande: DomainClaim, utilisateur) -> None:
    """Retire le domaine : plus de routage, plus de nouveau certificat."""
    Domain.objects.filter(
        tenant_id=demande.tenant_id,
        hostname=demande.hostname,
        kind=Domain.Kind.CUSTOM_DOMAIN,
    ).delete()
    invalidate_hostname(demande.hostname)
    _journaliser("DOMAIN_REMOVED", demande.tenant_id, utilisateur, demande)
    demande.delete()


def _echec(demande: DomainClaim, code: str, message: str) -> DomainClaim:
    demande.last_error = message[:255]
    demande.save(update_fields=["last_error", "last_checked_at", "updated_at"])
    raise DomaineRefuse(message, code)


def _journaliser(action: str, tenant_id, utilisateur, demande: DomainClaim) -> None:
    from apps.audit.models import AuditLog

    AuditLog.objects.create(
        tenant_id=tenant_id,
        actor_user=utilisateur if getattr(utilisateur, "pk", None) else None,
        action=getattr(AuditLog.Action, action),
        resource_type="domain",
        resource_id=str(demande.pk),
        metadata={"hostname": demande.hostname},
    )


# ---------------------------------------------------------------------------
# Le droit de servir
# ---------------------------------------------------------------------------


def domaine_perso_ouvert(tenant_id) -> bool:
    """Le salon a-t-il (encore) la fonction ? Mis en cache deux minutes.

    Appele pour chaque requete arrivant par un domaine personnalise, avant
    toute resolution de contexte : d'ou le cache, et le contexte pose ici.
    """
    cle = f"domaine-perso:{tenant_id}"
    en_cache = cache.get(cle)
    if en_cache is not None:
        return en_cache == "1"
    from apps.billing.droits import a_la_fonction

    with bypass_tenant_context(), tenant_context(tenant_id):
        ouvert = a_la_fonction(tenant_id, "custom_domain")
    cache.set(cle, "1" if ouvert else "0", DUREE_CACHE_DROIT)
    return ouvert


def canonique_en_pause(hostname: str) -> str | None:
    """Le sous-domaine vers lequel renvoyer un domaine perso en pause."""
    domaine = (
        Domain.objects.select_related("tenant")
        .filter(hostname=hostname.strip().lower(), kind=Domain.Kind.CUSTOM_DOMAIN, active=True)
        .first()
    )
    if domaine is None or domaine_perso_ouvert(domaine.tenant_id):
        return None
    return platform_hostname(domaine.tenant.slug)


def domaines_verifies() -> list[str]:
    """Les domaines personnalises relies, pour la route du proxy d'entree."""
    return list(
        Domain.objects.filter(
            kind=Domain.Kind.CUSTOM_DOMAIN, active=True, verified_at__isnull=False
        )
        .order_by("hostname")
        .values_list("hostname", flat=True)
    )
