"""Inscription d'un salon, invitations d'equipe, mots de passe.

Ces operations touchent a la fois des tables plateforme (User, Membership)
et des tables de salon (Tenant, SalonProfile, Invitation). Elles sont donc
regroupees ici plutot que dans les vues : le contexte tenant doit etre pose
et retire au bon moment, et une inscription a moitie faite laisserait un
sous-domaine reserve sans personne pour l'administrer.
"""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.common.db import tenant_context
from apps.domains.services import ensure_platform_domain
from apps.notifications.details import grouper
from apps.notifications.email import send_email
from apps.salons.models import SalonProfile
from apps.tenants.models import Tenant

from .models import Invitation, Membership, User

logger = logging.getLogger(__name__)

ADMIN_DB = "admin"


class SignupError(Exception):
    """Inscription refusee pour une raison metier."""


class InvitationError(Exception):
    """Invitation invalide, expiree, revoquee ou deja utilisee."""


def _send(subject: str, template: str, context: dict, to: str) -> None:
    """Un destinataire unique, mais le meme envoi que partout ailleurs.

    Ces trois messages partaient en texte brut parce qu'ils avaient leur
    propre fonction d'envoi. Ils passent maintenant par celle du produit,
    et recoivent donc leur version HTML comme les autres.
    """
    send_email(subject=subject, template=template, context=context, to=[to])


# ---------------------------------------------------------------------------
# Inscription d'un salon
# ---------------------------------------------------------------------------


@transaction.atomic
def signup_salon(
    *,
    name: str,
    slug: str,
    email: str,
    password: str,
    display_name: str = "",
    phone: str = "",
    country: str = Tenant.Country.CONGO,
    timezone_name: str = "Africa/Brazzaville",
    currency: str = Tenant.Currency.XAF,
    theme_config: dict | None = None,
) -> tuple[Tenant, User]:
    """Cree un salon et son compte proprietaire.

    Le salon nait en statut « en preparation » : son sous-domaine est
    reserve, mais son mini-site n'est pas public tant que l'equipe
    plateforme ne l'a pas valide. C'est ce qui permet d'ouvrir les
    inscriptions sans laisser publier n'importe quelle page sous le domaine.
    """
    email = email.strip().lower()
    slug = slug.strip().lower()

    if slug in settings.RESERVED_SUBDOMAINS:
        raise SignupError("Cette adresse est réservée.")
    if Tenant.objects.filter(slug=slug).exists():
        raise SignupError("Cette adresse est déjà prise.")
    if User.objects.filter(email=email).exists():
        # On ne cree pas un second compte : la personne se connecte, puis
        # demande a l'equipe de rattacher un nouveau salon.
        raise SignupError("Un compte existe déjà avec cette adresse e-mail.")

    tenant = Tenant.objects.create(
        name=name.strip(),
        slug=slug,
        status=Tenant.Status.PENDING,
        plan=Tenant.Plan.TRIAL,
        country=country,
        timezone=timezone_name,
        currency=currency,
    )
    ensure_platform_domain(tenant)

    user = User.objects.create_user(
        email=email,
        password=password,
        display_name=display_name.strip() or name.strip(),
        phone=phone.strip(),
    )
    membership = Membership.objects.create(
        tenant=tenant,
        user=user,
        role=Membership.Role.OWNER,
        status=Membership.Status.ACTIVE,
    )

    # Fiche vide des le depart : le proprietaire a quelque chose a remplir
    # au lieu d'un ecran qui parle de creation.
    with tenant_context(tenant.id):
        # Les couleurs choisies avant l'inscription sont reprises : sans
        # cela, la page d'accueil promettrait un report qui n'a pas lieu.
        # L'e-mail de contact publie part de l'adresse d'inscription : le
        # mini-site affiche une adresse des le premier jour. Le salon la
        # change ou l'efface depuis son profil.
        SalonProfile.objects.create(
            tenant=tenant, theme_config=theme_config or {}, contact_email=user.email
        )
        _seed_business_hours(tenant)
        _seed_owner_as_staff(tenant, user, membership)

    # Periode d'essai ouverte des l'inscription : sans elle, le salon n'a
    # aucun statut d'abonnement et le tableau de bord n'a rien a montrer.
    from apps.billing.services import BillingError, start_trial

    try:
        start_trial(tenant)
    except BillingError:
        # Aucune offre d'essai configuree : l'inscription reste valable,
        # l'equipe rattachera l'abonnement a la main.
        logger.warning("Inscription sans offre d'essai configurée (%s).", tenant.slug)

    transaction.on_commit(lambda: _notify_signup(tenant, user))

    # L'equipe de la plateforme est prevenue dans son administration :
    # une inscription est le seul evenement qu'on veut voir arriver le
    # jour meme, pour accompagner un salon qui demarre.
    from apps.notifications import evenements

    evenements.salon_inscrit(tenant)
    return tenant, user


def _notify_signup(tenant: Tenant, user: User) -> None:
    hostname = f"{tenant.slug}.{settings.PLATFORM_DOMAIN}"
    _send(
        subject=f"Bienvenue sur Beauty Salon, {tenant.name}",
        template="signup_welcome",
        context={
            "salon": tenant,
            "user": user,
            "hostname": hostname,
            "app_url": settings.APP_BASE_URL,
            "intro": (
                f"Votre salon {tenant.name} est créé. Voici où le retrouver."
            ),
            "details": grouper([
                {"label": "Mini-site", "value": hostname},
                {"label": "Espace professionnel", "value": settings.APP_BASE_URL},
                {"label": "Compte", "value": user.email, "strong": True},
            ]),
        },
        to=user.email,
    )


# ---------------------------------------------------------------------------
# Invitations d'equipe
# ---------------------------------------------------------------------------


def invite_member(*, tenant, email: str, role: str, invited_by=None) -> Invitation:
    email = email.strip().lower()

    already_member = Membership.objects.filter(
        tenant=tenant, user__email=email
    ).exists()
    if already_member:
        raise InvitationError("Cette personne fait déjà partie de l'équipe.")

    invitation, token = Invitation.issue(
        tenant=tenant, email=email, role=role, invited_by=invited_by
    )

    _send(
        subject=f"Rejoignez l'équipe de {tenant.name}",
        template="team_invitation",
        context={
            "salon": tenant,
            "invitation": invitation,
            "role": invitation.get_role_display(),
            "accept_url": f"{settings.APP_BASE_URL}/invitation?token={token}",
            "invited_by": invited_by,
            "intro": (
                f"{tenant.name} vous invite à rejoindre son équipe "
                "sur Beauty Salon."
            ),
            "details": grouper([
                {"label": "Salon", "value": tenant.name},
                {"label": "Rôle", "value": invitation.get_role_display(), "strong": True},
            ]
            + (
                [{"label": "Invitée par", "value": invited_by.email}]
                if invited_by
                else []
            )),
        },
        to=email,
    )
    return invitation


def find_invitation(token: str) -> Invitation:
    """Retrouve une invitation depuis son jeton.

    Passe par l'alias `admin` : au moment ou la personne clique sur le lien,
    aucun contexte tenant n'existe encore, et les politiques RLS masqueraient
    la ligne. C'est le meme chemin inter-tenants que celui de l'admin
    plateforme, utilise ici de facon deliberee et bornee.
    """
    if not token:
        raise InvitationError("Lien d'invitation invalide.")

    invitation = (
        Invitation.all_tenants.using(ADMIN_DB)
        .select_related("tenant")
        .filter(token_hash=Invitation.hash_token(token))
        .first()
    )
    if invitation is None:
        raise InvitationError("Lien d'invitation invalide.")
    if not invitation.is_pending:
        raise InvitationError("Cette invitation n'est plus valable.")
    return invitation


@transaction.atomic
def accept_invitation(
    *, token: str, password: str | None = None, display_name: str = ""
) -> tuple[User, Invitation]:
    invitation = find_invitation(token)

    user = User.objects.filter(email=invitation.email).first()
    if user is None:
        if not password:
            raise InvitationError("Un mot de passe est requis pour créer le compte.")
        user = User.objects.create_user(
            email=invitation.email,
            password=password,
            display_name=display_name.strip(),
        )

    membership, created = Membership.objects.get_or_create(
        tenant_id=invitation.tenant_id,
        user=user,
        defaults={"role": invitation.role, "status": Membership.Status.ACTIVE},
    )
    if not created:
        membership.status = Membership.Status.ACTIVE
        membership.save(update_fields=["status", "updated_at"])

    invitation.accepted_at = timezone.now()
    invitation.save(using=ADMIN_DB, update_fields=["accepted_at", "updated_at"])

    return user, invitation


# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------


def request_password_reset(email: str) -> None:
    """Envoie un lien de reinitialisation, s'il existe un compte actif.

    L'appelant repond toujours la meme chose, que le compte existe ou non :
    une reponse differenciee transformerait ce formulaire en annuaire des
    adresses inscrites.
    """
    user = User.objects.filter(email=email.strip().lower(), is_active=True).first()
    if user is None:
        logger.info("Reinitialisation demandee pour une adresse inconnue.")
        return

    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))

    _send(
        subject="Réinitialiser votre mot de passe Beauty Salon",
        template="password_reset",
        context={
            "user": user,
            "reset_url": f"{settings.APP_BASE_URL}/mot-de-passe/nouveau?uid={uid}&token={token}",
            "validity_hours": settings.PASSWORD_RESET_TIMEOUT // 3600,
            "intro": (
                "Vous avez demandé à réinitialiser le mot de passe de votre "
                "compte Beauty Salon."
            ),
            "validity_note": (
                f"Ce lien est valable {settings.PASSWORD_RESET_TIMEOUT // 3600} "
                "heures et ne fonctionne qu'une seule fois."
            ),
        },
        to=user.email,
    )


def _seed_owner_as_staff(tenant: Tenant, user: User, membership) -> None:
    """La proprietaire est prestataire des le depart.

    -----------------------------------------------------------------------
    Pourquoi ce n'est pas un confort
    -----------------------------------------------------------------------

    Sans au moins un prestataire, le moteur de creneaux ne propose rien : le
    mini-site s'ouvre sur « aucune disponibilite » et la reservation parait
    cassee. Or le cas de loin le plus frequent est une personne qui travaille
    seule - elle *est* le salon, et lui demander de se creer une fiche de
    prestataire pour se designer elle-meme est une etape qui n'a de sens que
    pour le logiciel.

    La fiche est rattachee a son compte (`membership`), ce qui n'est pas un
    detail : c'est ce rattachement qui fait qu'un prestataire ne voit que son
    propre agenda, et que le sien est bien le sien.

    Le nom vient du compte. S'il est vide - une inscription qui n'a rempli que
    l'adresse e-mail - on prend la partie avant l'arobase plutot que de
    laisser une fiche sans nom, qui s'afficherait telle quelle sur le
    mini-site.
    """
    from apps.staff.models import StaffMember

    StaffMember.objects.create(
        tenant=tenant,
        membership=membership,
        name=user.display_name.strip() or user.email.split("@")[0],
        active=True,
    )


def _seed_business_hours(tenant: Tenant) -> None:
    """Grille horaire de depart : mardi au samedi, avec coupure du midi.

    Sans horaires, le moteur de creneaux ne propose rien : le mini-site
    s'ouvre sur « aucune disponibilite », et la gerante conclut que la
    reservation ne marche pas. C'est le premier abandon du parcours.

    Ces valeurs sont un point de depart plausible pour un salon de beaute,
    pas une supposition sur *ce* salon : l'ecran Horaires les montre en toutes
    lettres des la premiere visite, et elles se corrigent en deux clics.
    """
    from datetime import time

    from apps.scheduling.models import BusinessHours

    ranges = ((time(9, 30), time(13, 0)), (time(14, 0), time(19, 0)))
    BusinessHours.objects.bulk_create(
        BusinessHours(
            tenant=tenant,
            staff_member=None,
            weekday=weekday,
            starts_at=start,
            ends_at=end,
        )
        # 1 = mardi, 5 = samedi. Lundi et dimanche restent fermes, ce qui est
        # l'usage le plus repandu dans le metier.
        for weekday in range(1, 6)
        for start, end in ranges
    )
