"""L'ecran de suppression definitive, commun aux salons et aux comptes.

Le bouton « Supprimer » de Django est retire sur ces deux ecrans (voir
`apps/common/suppression.py` pour la raison technique). A sa place, une page
a part, qui demande ce qu'on ne donne pas par inadvertance :

  - l'identifiant exact de ce qu'on supprime, retape a la main ;
  - un motif, ecrit dans le journal d'audit ;
  - le mot de passe de l'administrateur, et son code de double
    authentification s'il en a un : une session laissee ouverte sur un
    poste ne suffit pas ;
  - cinq essais au plus par quart d'heure.

Reserve aux superutilisateurs administrateurs de la plateforme.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .suppression import SuppressionRefusee

ESSAIS_MAX = 5
FENETRE_ESSAIS = 15 * 60


class ConfirmationForm(forms.Form):
    confirmation = forms.CharField(label="Retapez l'identifiant", max_length=254)
    motif = forms.CharField(
        label="Motif",
        widget=forms.Textarea(attrs={"rows": 3}),
        min_length=10,
        max_length=500,
        help_text="Obligatoire. Enregistré dans le journal d'audit.",
    )
    mot_de_passe = forms.CharField(
        label="Votre mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    code = forms.CharField(
        label="Code de double authentification",
        required=False,
        max_length=16,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )


class ConfirmationSalonForm(ConfirmationForm):
    avec_comptes = forms.BooleanField(
        label="Supprimer aussi les comptes qui n'appartiennent qu'à ce salon",
        required=False,
        help_text="Équipe et clientes sans autre salon. Jamais un compte d'administration.",
    )


def _peut_supprimer(user) -> bool:
    return bool(user.is_active and user.is_superuser and user.is_platform_admin)


def _a_un_appareil(user) -> bool:
    from django_otp import devices_for_user

    return any(True for _ in devices_for_user(user, confirmed=True))


def _code_valide(user, code: str) -> bool:
    from django_otp import devices_for_user

    code = (code or "").strip().replace(" ", "")
    return bool(code) and any(d.verify_token(code) for d in devices_for_user(user, confirmed=True))


class SuppressionDefinitiveMixin:
    """A melanger a un ModelAdmin. Les sous-classes definissent :

    - `suppression_formulaire` : la classe du formulaire ;
    - `suppression_identifiant(obj)` : ce qu'il faut retaper ;
    - `suppression_contexte(request, obj)` : l'inventaire et les obstacles ;
    - `suppression_executer(request, obj, donnees)` : la suppression.
    """

    suppression_formulaire = ConfirmationForm

    # La suppression de Django est retiree : une seule porte, celle-ci.
    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def get_urls(self):
        info = self.opts.app_label, self.opts.model_name
        return [
            path(
                "<path:object_id>/supprimer-definitivement/",
                self.admin_site.admin_view(self.vue_suppression),
                name="{}_{}_suppression".format(*info),
            ),
            *super().get_urls(),
        ]

    @property
    def _nom_url(self) -> str:
        return f"admin:{self.opts.app_label}_{self.opts.model_name}_suppression"

    def lien_suppression(self, obj):
        """Le lien, en bas de la fiche : visible, mais jamais a portee de clic distrait."""
        if obj is None or obj.pk is None:
            return "—"
        return format_html(
            '<a class="deletelink" href="{}">Supprimer définitivement…</a>',
            reverse(self._nom_url, args=[obj.pk]),
        )

    lien_suppression.short_description = "Zone sensible"

    def vue_suppression(self, request, object_id):
        if not _peut_supprimer(request.user):
            raise PermissionDenied
        obj = get_object_or_404(self.get_queryset(request), pk=object_id)
        contexte = self.suppression_contexte(request, obj)
        identifiant = self.suppression_identifiant(obj)
        double = _a_un_appareil(request.user)
        form = self.suppression_formulaire(request.POST or None)

        if request.method == "POST" and not contexte.get("obstacles"):
            cle = f"suppression:essais:{request.user.pk}"
            if (cache.get(cle) or 0) >= ESSAIS_MAX:
                form.add_error(None, "Trop d'essais. Réessayez dans un quart d'heure.")
            elif form.is_valid():
                erreurs = self._verifier(request, form.cleaned_data, identifiant, double)
                if erreurs:
                    cache.add(cle, 0, FENETRE_ESSAIS)
                    cache.incr(cle)
                    for erreur in erreurs:
                        form.add_error(None, erreur)
                else:
                    try:
                        bilan = self.suppression_executer(request, obj, form.cleaned_data)
                    except SuppressionRefusee as refus:
                        form.add_error(None, str(refus))
                    else:
                        cache.delete(cle)
                        self.message_user(request, bilan, messages.SUCCESS)
                        return HttpResponseRedirect(
                            reverse(
                                f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist"
                            )
                        )

        return TemplateResponse(
            request,
            "admin/suppression_definitive.html",
            {
                **self.admin_site.each_context(request),
                **contexte,
                "title": f"Supprimer définitivement « {obj} »",
                "objet": obj,
                "identifiant": identifiant,
                "form": form,
                "double_authentification": double,
                "opts": self.opts,
            },
        )

    @staticmethod
    def _verifier(request, donnees, identifiant: str, double: bool) -> list[str]:
        erreurs = []
        if donnees["confirmation"].strip().lower() != identifiant.lower():
            erreurs.append("L'identifiant retapé ne correspond pas.")
        if not request.user.check_password(donnees["mot_de_passe"]):
            erreurs.append("Mot de passe incorrect.")
        if double and not _code_valide(request.user, donnees.get("code", "")):
            erreurs.append("Code de double authentification incorrect ou expiré.")
        return erreurs
