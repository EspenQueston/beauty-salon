"""Ce qui se traduit, et ce qui ne se traduit pas.

---------------------------------------------------------------------------
La liste est courte, et les absences sont voulues
---------------------------------------------------------------------------

Ne figurent ici que les textes que le salon **redige** : un nom de prestation,
une description, une histoire, une politique. Tout le reste reste tel quel, et
chaque absence a sa raison :

- **Le nom d'une personne.** « Grace Mabiala » ne se traduit pas. Une machine
  a qui l'on donne un nom propre a traduire finit par en proposer une variante,
  et une prestataire dont le nom change d'une langue a l'autre n'est plus
  reconnaissable par sa cliente.
- **Les noms de lieux** — ville, adresse, quartiers desservis. « Pointe-Noire »
  reste « Pointe-Noire ». Un quartier traduit devient introuvable sur une carte.
- **Le nom du salon.** C'est la marque.
- **Les chiffres** : prix, durees, delais. Ils ne sont pas du texte.

---------------------------------------------------------------------------
Ajouter un champ
---------------------------------------------------------------------------

Une ligne ici suffit. Les salons existants sont rattrapes par la commande
`traduire_le_contenu`, et les suivants par le signal a l'enregistrement. Aucune
migration n'est necessaire : les traductions vivent dans leur propre table.
"""

from __future__ import annotations

# Etiquette de modele (`app_label.modelname`, en minuscules) → champs traduits.
TRADUISIBLES: dict[str, tuple[str, ...]] = {
    "salons.salonprofile": (
        "description",
        "about_title",
        "about_content",
        "cancellation_policy",
        "late_policy",
    ),
    "catalog.servicecategory": ("name",),
    "catalog.service": ("name", "description"),
    "catalog.serviceoption": ("name", "description"),
    # `specialty` et `bio` seulement : `name` est le nom d'une personne.
    "staff.staffmember": ("specialty", "bio"),
    "store.product": ("name", "description"),
    "store.requirement": ("label", "detail"),
    "payments.paymentchannel": ("instructions",),
}


def champs_de(objet) -> tuple[str, ...]:
    """Les champs traduisibles d'une instance, ou rien si elle n'en a pas."""
    return TRADUISIBLES.get(objet._meta.label_lower, ())


def etiquette(objet) -> str:
    """« catalog.service » — ce qui est stocke dans `Translation.model`."""
    return objet._meta.label_lower
