"""Cas A : identité par salon, attribution à la création, conditions figées."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.clients.services import est_cliente
from apps.scheduling.models import Booking

from .models import CodeClientSalon, EvenementParrainage, PolitiqueSalon, RecompenseClient
from .services import (
    _chiffres,
    _meme_personne,
    _nouveau_code,
    actif,
    arrondir,
    empreinte,
    normaliser_code,
)


def journal(r, action, **details):
    EvenementParrainage.objects.create(
        cas="A", tenant_id=r.tenant_id, ressource=r.pk, action=action, details=details
    )


def politique():
    if not actif():
        return None
    p = PolitiqueSalon.objects.filter(active=True).first()
    if p:
        try:
            p.full_clean()
        except ValidationError:
            return None
    return p


def verrou_identite(tenant_id, email):
    # Même verrou pour réservation organique et parrainée. Pas d'IP utilisée comme preuve.
    cle = int(empreinte(f"{tenant_id}:{email.strip().lower()}")[:15], 16)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [cle])


def code_client(user, tenant_id):
    if not est_cliente(user) or not user.email_verified_at:
        raise ValueError("Confirmez votre adresse e-mail pour partager un parrainage.")
    with transaction.atomic():
        from apps.accounts.models import User

        User.objects.select_for_update().get(pk=user.pk)
        for _ in range(5):
            try:
                with transaction.atomic():
                    return CodeClientSalon.objects.get_or_create(
                        user=user, tenant_id=tenant_id, defaults={"code": _nouveau_code()}
                    )[0]
            except IntegrityError:
                continue
        raise RuntimeError("Impossible de générer un code unique.")


def capturer(booking, saisie):
    if not saisie:
        return
    from apps.scheduling.services.booking import BookingRefused

    p = politique()
    c = (
        CodeClientSalon.objects.select_related("user")
        .filter(tenant_id=booking.tenant_id, code=normaliser_code(saisie), actif=True)
        .first()
    )
    if not p or not c or not est_cliente(c.user) or not c.user.email_verified_at:
        raise BookingRefused("Ce code de parrainage n’est pas disponible pour ce salon.")
    email = booking.contact_email.strip().lower()
    if not email:
        raise BookingRefused("Une adresse e-mail est nécessaire au parrainage.")
    if (
        email == c.user.email.strip().lower()
        or (booking.compte_id and _meme_personne(booking.compte, c.user))
        or (c.user.phone and _chiffres(booking.customer.phone) == _chiffres(c.user.phone))
    ):
        raise BookingRefused("Vous ne pouvez pas vous parrainer vous-même.")
    identite = empreinte(email)
    avant = (
        Booking.objects.filter(tenant_id=booking.tenant_id)
        .exclude(pk=booking.pk)
        .filter(
            Q(contact_email__iexact=email)
            | Q(customer_id=booking.customer_id)
            | (Q(compte_id=booking.compte_id) if booking.compte_id else Q(pk=None))
        )
    )
    if not p.reservations_annulees_excluent:
        avant = avant.exclude(status=Booking.Status.CANCELLED)
    if avant.exists() or RecompenseClient.objects.filter(identite_filleul=identite).exists():
        raise BookingRefused("Ce parrainage est réservé à une première réservation dans ce salon.")
    conditions = {
        "validite_jours": p.validite_jours,
        "formule": p.formule,
        "annulation_declencheur": p.annulation_declencheur,
        "annulation_utilisation": p.annulation_utilisation,
    }
    r = RecompenseClient.objects.create(
        tenant_id=booking.tenant_id,
        parrain=c.user,
        filleul=booking.compte,
        identite_filleul=identite,
        declencheur=booking,
        taux=p.taux,
        plafond_montant=p.plafond_montant,
        devise=p.devise,
        conditions=conditions,
    )
    journal(r, "creation", reservation=str(booking.pk))


def prix(initial, promotions, taux, plafond, devise):
    """Formule validée : après promotions, HALF_UP, plafond, jamais négatif."""
    base = max(Decimal(0), initial - promotions)
    reduction = min(base, plafond, arrondir(base * taux / 100, devise))
    return reduction, max(Decimal(0), base - reduction)


def reserver(booking, user):
    if not actif() or not est_cliente(user) or not user.email_verified_at:
        return
    maintenant = timezone.now()
    for r in (
        RecompenseClient.objects.select_for_update()
        .filter(
            tenant_id=booking.tenant_id, parrain=user, statut="disponible", devise=booking.currency
        )
        .order_by("expire_le", "created_at")
    ):
        if not r.expire_le or r.expire_le <= maintenant:
            r.statut = "expiree"
            r.save(update_fields=["statut"])
            journal(r, "expiration")
            continue
        initial = booking.prix_initial if booking.prix_initial is not None else booking.total_amount
        base = initial - booking.items_amount - booking.travel_fee_amount
        reduction, final = prix(
            base, booking.promotion_montant, r.taux, r.plafond_montant, r.devise
        )
        if reduction <= 0:
            return
        r.statut, r.utilisation, r.montant_deduit = "reservee", booking, reduction
        r.save(update_fields=["statut", "utilisation", "montant_deduit"])
        booking.reduction_parrainage = reduction
        booking.total_amount = final + booking.items_amount + booking.travel_fee_amount
        from apps.salons.models import SalonProfile
        from apps.scheduling.services.deposit import compute_deposit

        profil = SalonProfile.objects.get(tenant_id=booking.tenant_id)
        booking.deposit_amount = compute_deposit(
            service_amount=final,
            items_amount=booking.items_amount,
            travel_amount=booking.travel_fee_amount,
            requires_deposit=booking.service.requires_deposit,
            rate=profil.deposit_rate or 0,
            minimum=profil.deposit_minimum or Decimal(0),
            covers_items=profil.deposit_covers_items,
            currency=booking.currency,
        )
        champs = ["reduction_parrainage", "total_amount", "deposit_amount"]
        if booking.status == Booking.Status.PENDING_PAYMENT and booking.deposit_amount == 0:
            booking.status = Booking.Status.REQUESTED
            champs.append("status")
        booking.save(update_fields=champs)
        journal(r, "reservation", reservation=str(booking.pk), montant=str(reduction))
        return


@transaction.atomic
def transition(booking, precedent):
    maintenant = timezone.now()
    if booking.status == Booking.Status.CONFIRMED and precedent != Booking.Status.CONFIRMED:
        r = RecompenseClient.objects.select_for_update().filter(declencheur=booking).first()
        if r and r.statut == "en_attente":
            r.statut, r.disponible_le = "disponible", maintenant
            r.expire_le = maintenant + timedelta(days=r.conditions["validite_jours"])
            r.save(update_fields=["statut", "disponible_le", "expire_le"])
            journal(r, "disponibilite", expire_le=r.expire_le.isoformat())
        r = RecompenseClient.objects.select_for_update().filter(utilisation=booking).first()
        if r and r.statut == "reservee":
            r.statut = "utilisee"
            r.save(update_fields=["statut"])
            journal(r, "utilisation", reservation=str(booking.pk))
    if booking.status == Booking.Status.CANCELLED and precedent != Booking.Status.CANCELLED:
        for r in RecompenseClient.objects.select_for_update().filter(
            Q(declencheur=booking) | Q(utilisation=booking)
        ):
            declencheur = r.declencheur_id == booking.pk
            regle = r.conditions[
                "annulation_declencheur" if declencheur else "annulation_utilisation"
            ]
            journal(r, "annulation_reservation", reservation=str(booking.pk), politique=regle)
            if declencheur and r.statut == "en_attente":
                r.statut = "annulee"
            elif regle == "revue":
                r.statut = "suspendue"
            elif not declencheur and regle == "restituer":
                r.statut = "disponible" if r.expire_le > maintenant else "expiree"
                r.utilisation, r.montant_deduit = None, None
            r.save(update_fields=["statut", "utilisation", "montant_deduit"])
            journal(r, "decision_annulation", statut=r.statut)


def etat(user, tenant_id):
    from django.conf import settings

    from apps.tenants.models import Tenant

    p = politique()
    c = code_client(user, tenant_id) if p else None
    tenant = Tenant.objects.get(pk=tenant_id)
    from apps.domains.models import Domain

    domaine = Domain.objects.filter(tenant_id=tenant_id, active=True, is_primary=True).first()
    host = domaine.hostname if domaine else f"{tenant.slug}.{settings.PLATFORM_DOMAIN}"
    scheme = "http" if settings.DEBUG else "https"
    port = f":{settings.WEB_PORT}" if settings.DEBUG else ""
    return {
        "actif": bool(p),
        "code": c.code if c else "",
        "lien": f"{scheme}://{host}{port}/reserver?parrain_client={c.code}" if c else "",
        "taux": str(p.taux) if p else None,
        "plafond": str(p.plafond_montant) if p else None,
        "devise": p.devise if p else tenant.currency,
        "validite_jours": p.validite_jours if p else None,
        "recompenses": [
            {
                "id": str(r.pk),
                "taux": str(r.taux),
                "plafond": str(r.plafond_montant),
                "devise": r.devise,
                "statut": r.statut,
                "expire_le": r.expire_le,
                "montant_deduit": str(r.montant_deduit) if r.montant_deduit is not None else None,
            }
            for r in RecompenseClient.objects.filter(tenant_id=tenant_id, parrain=user).order_by(
                "-created_at"
            )[:100]
        ],
    }
