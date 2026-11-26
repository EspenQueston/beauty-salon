"""Les traductions dans l'admin plateforme : les lire, et les corriger.

Une traduction corrigee ici passe en origine « salon » et n'est plus jamais
reecrite par la machine — c'est la regle posee dans `services.a_traduire`. Sans
cela, la correction d'une gerante disparaitrait au prochain rattrapage, et elle
n'aurait aucun moyen de comprendre pourquoi.
"""

from django.contrib import admin

from .models import Origin, Translation


@admin.register(Translation)
class TranslationAdmin(admin.ModelAdmin):
    list_display = ("model", "field", "language", "origin", "apercu", "updated_at")
    list_filter = ("language", "origin", "model")
    search_fields = ("text",)
    # Tout sauf le texte : changer la cible d'une traduction n'a pas de sens,
    # et changer l'empreinte la rendrait faussement a jour.
    readonly_fields = ("model", "object_id", "field", "language", "source_digest")

    @admin.display(description="texte")
    def apercu(self, objet: Translation) -> str:
        return objet.text[:80] + ("…" if len(objet.text) > 80 else "")

    def save_model(self, request, obj, form, change):
        if change and "text" in form.changed_data:
            obj.origin = Origin.SALON
        super().save_model(request, obj, form, change)
