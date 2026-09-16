"""Champs de serialisation partages."""

from rest_framework import serializers


class TenantPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """Reference vers un objet du salon courant, resolue a chaque requete.

    `PrimaryKeyRelatedField(queryset=Model.objects.all())` ne fonctionne pas
    avec les managers tenant : l'expression est evaluee a l'import du module,
    hors contexte, donc TenantManager renvoie `.none()` et *toutes* les
    references deviennent invalides. Meme piege que pour les viewsets, en
    plus discret - l'erreur ressemble a une simple erreur de validation.
    """

    def __init__(self, model, **kwargs):
        self.model = model
        # Valeur d'attente : get_queryset() ci-dessous a toujours le dernier mot.
        kwargs.setdefault("queryset", model.objects.none())
        super().__init__(**kwargs)

    def get_queryset(self):
        return self.model.objects.all()
