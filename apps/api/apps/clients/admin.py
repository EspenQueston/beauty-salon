"""Les comptes clientes, vus depuis le support plateforme.

---------------------------------------------------------------------------
Pourquoi cet ecran existait de facon urgente
---------------------------------------------------------------------------

Un compte cliente ne appartient a aucun salon : il les traverse. C'est ce
qui fait son interet — une cliente retrouve ses rendez-vous chez les trois
salons qu'elle frequente — et c'est ce qui le rendait introuvable.

Une cliente qui ecrit « supprimez mon compte » ne s'adresse pas a un salon,
elle s'adresse a la plateforme. Il n'existait aucun ecran pour la retrouver,
et donc aucune facon de repondre.

---------------------------------------------------------------------------
Ce que la suppression efface, et ce qu'elle laisse
---------------------------------------------------------------------------

Elle efface ce qui appartient a la plateforme : les preferences de contact,
le salon favori, les rattachements, les visites masquees.

Elle **ne touche pas** aux fiches clientes des salons. Celles-ci portent
l'historique des rendez-vous, les acomptes recus et les lignes de recette :
les effacer d'ici reecrirait la comptabilite de commercants qui n'ont rien
demande. Un salon qui doit purger sa propre fiche le fait depuis son espace,
ou la demande lui est transmise.

Le reste est en lecture seule, pour la meme raison que partout ailleurs
dans cette administration : on regarde, on explique, on ne corrige pas a la
place de quelqu'un d'autre.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.common.admin import AdminDatabaseMixin

from .models import ClientProfile, ClientSalonLink, HiddenBooking


@admin.register(ClientProfile)
class ClientProfileAdmin(AdminDatabaseMixin, admin.ModelAdmin):
    """Un compte cliente, et les salons qu'il traverse."""

    list_display = (
        "adresse",
        "nom",
        "telephone",
        "salon_favori",
        "nombre_de_salons",
        "created_at",
    )
    list_filter = ("preferred_salon", "created_at")
    search_fields = (
        "user__email",
        "user__display_name",
        "whatsapp",
        "wechat",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("user", "preferred_salon")

    fieldsets = (
        ("Le compte", {"fields": ("user", "created_at", "updated_at")}),
        (
            "Contact",
            {
                "fields": ("whatsapp", "wechat"),
                "description": (
                    "WhatsApp en Afrique centrale, WeChat en Chine : ce sont les "
                    "deux canaux réels de la clientèle visée, et rarement le même "
                    "numéro que la ligne principale."
                ),
            },
        ),
        (
            "Ses salons",
            {
                "fields": ("preferred_salon", "salons_rattaches", "visites_masquees"),
                "description": (
                    "Le rattachement est un index, pas une copie : il dit chez qui "
                    "la cliente a une fiche, sans jamais lire les données d'un "
                    "salon depuis le contexte d'un autre."
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        # Tout, sans exception. Énumérer à la main laisserait le prochain
        # champ ajouté au modèle modifiable par distraction.
        champs = [f.name for f in self.model._meta.fields]
        return (*champs, "salons_rattaches", "visites_masquees")

    def has_add_permission(self, request):
        """Un compte se crée depuis le mini-site d'un salon, jamais ici.

        Le créer de force donnerait un compte sans mot de passe choisi, sans
        salon d'origine, et sans que personne ne l'ait demandé.
        """
        return False

    def has_change_permission(self, request, obj=None):
        return False

    # La suppression, elle, reste ouverte : voir l'en-tête du module.
    # C'est le seul geste d'écriture de cet écran, et la seule raison
    # d'être de la page.

    @admin.display(description="Adresse", ordering="user__email")
    def adresse(self, profile):
        return profile.user.email

    @admin.display(description="Nom", ordering="user__display_name")
    def nom(self, profile):
        return profile.user.display_name or "—"

    @admin.display(description="Téléphone")
    def telephone(self, profile):
        """Les trois canaux d'un coup, et seulement ceux qui existent.

        Trois colonnes séparées donnaient deux tirets sur trois pour la
        plupart des lignes. Ici, ce qui s'affiche est ce qui est joignable.
        """
        canaux = []
        if profile.user.phone:
            canaux.append(profile.user.phone)
        if profile.whatsapp:
            canaux.append(f"WA {profile.whatsapp}")
        if profile.wechat:
            canaux.append(f"WeChat {profile.wechat}")
        return " · ".join(canaux) or "—"

    @admin.display(description="Salon favori", ordering="preferred_salon__name")
    def salon_favori(self, profile):
        return profile.preferred_salon.name if profile.preferred_salon else "—"

    @admin.display(description="Salons")
    def nombre_de_salons(self, profile):
        return ClientSalonLink.objects.filter(user_id=profile.user_id).count()

    @admin.display(description="Salons rattachés")
    def salons_rattaches(self, profile):
        """La liste, avec la date du rattachement.

        C'est la réponse à « chez qui cette cliente a-t-elle un dossier ? »,
        la question qui précède toujours une demande de suppression.
        """
        liens = (
            ClientSalonLink.objects.filter(user_id=profile.user_id)
            .select_related("tenant")
            .order_by("tenant__name")
        )
        if not liens:
            return mark_safe(
                '<span style="color:var(--bs-ink-muted)">aucun salon rattaché</span>'
            )

        lignes = "".join(
            format_html(
                "<li>{} <span style='color:var(--bs-ink-muted)'>— depuis le {}</span></li>",
                lien.tenant.name,
                lien.created_at.strftime("%d/%m/%Y"),
            )
            for lien in liens
        )
        return format_html("<ul style='margin:0;padding-left:1.1rem'>{}</ul>", lignes)

    @admin.display(description="Visites masquées")
    def visites_masquees(self, profile):
        """Retirées de *sa* vue, pas des livres du salon.

        Le chiffre sert à une seule chose : comprendre pourquoi une cliente
        dit ne pas retrouver un rendez-vous que le salon voit très bien.
        """
        total = HiddenBooking.objects.filter(user_id=profile.user_id).count()
        if total == 0:
            return mark_safe('<span style="color:var(--bs-ink-muted)">aucune</span>')
        return format_html(
            "{} visite{} retirée{} de son historique — le salon les garde entières",
            total,
            "s" if total > 1 else "",
            "s" if total > 1 else "",
        )
