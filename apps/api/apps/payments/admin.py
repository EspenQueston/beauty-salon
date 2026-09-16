"""Encaissement, vu depuis le support plateforme.

---------------------------------------------------------------------------
Les deux questions auxquelles ces ecrans repondent
---------------------------------------------------------------------------

Ce ne sont pas des questions inventees : ce sont les deux tickets qui
arrivent vraiment quand un salon ecrit a la plateforme.

  1. « Mes clientes n'arrivent pas a payer. »  -> PaymentChannelAdmin
     Presque toujours la meme cause : aucun QR televerse, ou le moyen a ete
     desactive sans qu'on s'en souvienne. Sans cet ecran, il fallait demander
     au salon de faire une capture de son propre tableau de bord.

  2. « Elle dit avoir paye, je n'ai rien recu. »  -> DepositProofAdmin
     La reponse tient en deux faits : la preuve est-elle arrivee, et
     qu'en a fait le salon ? Le reste - qui a raison sur le virement - ne se
     tranche pas ici, et ne doit pas l'etre.

---------------------------------------------------------------------------
Tout est en lecture seule, et c'est le point
---------------------------------------------------------------------------

Un acompte porte le chiffre d'affaires d'un salon, ses ecritures comptables
et son engagement envers une cliente. Une correction faite ici passerait
sous ses yeux sans laisser de trace dans son agenda, et ses comptes ne
tomberaient plus juste. Le geste correct est toujours de lui dire quoi
faire, jamais de le faire a sa place - c'est la regle deja posee par
`BookingAdmin`, et elle vaut ici avec plus de force encore.

---------------------------------------------------------------------------
Aucune image de preuve n'est affichee. C'est deliberé.
---------------------------------------------------------------------------

Une capture de paiement porte le nom de la cliente, l'heure du virement et
parfois le solde de son compte. Aujourd'hui, un administrateur plateforme ne
peut pas la voir : la route qui sert les medias prives exige un membership
sur le salon, et un compte plateforme n'en a aucun.

Cet ecran ne change rien a cet etat. Il montre **si** une capture existe -
l'information utile au support - jamais son contenu. Ouvrir l'image
demanderait de percer l'isolation pour les comptes plateforme : ca se
decide, ca se journalise, et ca ne se fait pas en passant.
"""

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.common.admin import TenantScopedAdmin

from .models import DepositProof, PaymentChannel

# Au-dela, une preuve en attente n'est plus une file : c'est un oubli.
ATTENTE_LONGUE = timezone.timedelta(hours=24)


class LectureSeule:
    """Ni creation, ni modification, ni suppression.

    La suppression est fermee aussi, et pas seulement par prudence : les
    lignes de recette pointent vers ces objets, et une preuve effacee
    laisserait un versement accepte sans rien qui l'explique.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentChannel)
class PaymentChannelAdmin(LectureSeule, TenantScopedAdmin):
    """Les moyens de paiement declares par chaque salon."""

    list_display = (
        "tenant",
        "kind",
        "etat",
        "account_name",
        "position",
    )
    list_filter = ("kind", "active", "tenant")
    search_fields = ("tenant__name", "account_name", "instructions")
    ordering = ("tenant__name", "position")
    list_select_related = ("tenant", "qr_image")

    @admin.display(description="État", ordering="active")
    def etat(self, channel):
        """Utilisable, et sinon **pourquoi**.

        Un booleen « actif » ne suffit pas : un moyen actif sans QR
        televerse est tout aussi inutilisable, et c'est le cas le plus
        frequent. Dire laquelle des deux causes s'applique evite un
        aller-retour avec le salon.
        """
        if channel.usable:
            return mark_safe('<span style="color:var(--bs-ok)">● Utilisable</span>')

        raison = "désactivé" if not channel.active else "aucun QR téléversé"
        return format_html('<span style="color:var(--bs-bad)">● Indisponible — {}</span>', raison)


@admin.register(DepositProof)
class DepositProofAdmin(LectureSeule, TenantScopedAdmin):
    """Les preuves de versement envoyees par les clientes.

    L'ecran est construit autour d'une seule colonne utile : **depuis
    combien de temps la preuve attend**. Une preuve envoyee il y a vingt
    minutes est une file d'attente normale ; la meme preuve trois jours plus
    tard est une cliente qui n'a pas de reponse et un creneau qui va se
    liberer tout seul. Sans cette colonne, il fallait soustraire deux dates
    de tete, ligne par ligne.
    """

    list_display = (
        "submitted_at",
        "tenant",
        "cliente",
        "status",
        "channel",
        "reference",
        "delai",
        "piece_jointe",
    )
    list_filter = ("status", "channel", "tenant")
    search_fields = (
        "tenant__name",
        "reference",
        "booking__customer__full_name",
        "booking__customer__email",
        "booking__customer__phone",
    )
    date_hierarchy = "submitted_at"
    ordering = ("-submitted_at",)
    list_select_related = ("tenant", "booking", "booking__customer", "reviewed_by")

    fieldsets = (
        (
            "Le versement",
            {
                "fields": (
                    "tenant",
                    "booking",
                    "status",
                    "channel",
                    "reference",
                    "note",
                )
            },
        ),
        (
            "Ce qu'en a fait le salon",
            {
                "fields": (
                    "submitted_at",
                    "reviewed_at",
                    "reviewed_by",
                    "rejection_reason",
                    "delai",
                )
            },
        ),
        (
            "La capture",
            {
                "fields": ("piece_jointe",),
                "description": (
                    "Le contenu de l'image n'est pas affiché ici, et ce n'est pas "
                    "un oubli : une capture de paiement porte le nom de la cliente "
                    "et parfois le solde de son compte. Seul le salon concerné y "
                    "accède, depuis son propre espace."
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        # Tout, sans exception. Enumerer a la main laisserait le prochain
        # champ ajoute au modele modifiable par distraction.
        champs = [f.name for f in self.model._meta.fields]
        return (*champs, "delai", "piece_jointe")

    @admin.display(description="Cliente")
    def cliente(self, proof):
        customer = getattr(proof.booking, "customer", None)
        return customer.full_name if customer else "—"

    @admin.display(description="Délai")
    def delai(self, proof):
        """Le temps que le salon a mis — ou qu'il fait attendre.

        Deux lectures dans une seule colonne, et l'oeil les distingue a la
        couleur : une reponse deja donnee est un fait passe, une attente en
        cours est une action a demander.
        """
        if proof.reviewed_at:
            ecoule = proof.reviewed_at - proof.submitted_at
            return format_html(
                '<span style="color:var(--bs-ink-muted)">répondu en {}</span>', _duree(ecoule)
            )

        attente = timezone.now() - proof.submitted_at
        # Les jetons de l'habillage, pas des hexadécimaux : `platform.css`
        # les redéfinit en mode sombre, un rouge foncé écrit en dur y serait
        # illisible.
        couleur = (
            "var(--bs-bad)" if attente > ATTENTE_LONGUE else "var(--bs-warn)"
        )
        return format_html(
            '<span style="color:{}">attend depuis {}</span>', couleur, _duree(attente)
        )

    @admin.display(description="Capture")
    def piece_jointe(self, proof):
        """Si une image existe, et rien de plus.

        Pas d'aperçu, pas de lien : l'information utile au support est
        « la cliente a-t-elle joint quelque chose », pas ce qu'on y voit.
        """
        if not proof.image_id:
            return mark_safe(
                '<span style="color:var(--bs-warn)">aucune capture jointe</span>'
            )
        return mark_safe(
            '<span style="color:var(--bs-ink-muted)">capture jointe — '
            "consultable par le salon uniquement</span>"
        )


def _duree(ecart) -> str:
    """« 3 j », « 5 h », « 40 min ». Jamais « 259200 secondes »."""
    minutes = int(ecart.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    heures = minutes // 60
    if heures < 48:
        return f"{heures} h"
    return f"{heures // 24} j"
