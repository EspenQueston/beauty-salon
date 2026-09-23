"""Servir un objet dans la langue demandee, sans requete supplementaire.

---------------------------------------------------------------------------
Une seule requete, quelle que soit la page
---------------------------------------------------------------------------

Le mini-site se charge en un appel — c'est la regle de `salons/serializers.py`,
et elle vaut pour les marches vises, ou le reseau se paie a la donnee. Aller
chercher la traduction de chaque champ au moment de le serialiser aurait ajoute
une requete par prestation.

La vue charge donc **toutes** les traductions du salon en une fois, les range
dans le contexte, et chaque serialiseur y puise. C'est une requete de plus par
page, pas une par champ.

---------------------------------------------------------------------------
Le francais reste le repli, toujours
---------------------------------------------------------------------------

Une traduction absente — jamais faite, service indisponible, texte modifie il y
a trente secondes — rend le texte francais. Jamais un blanc, jamais une cle.
Une cliente anglophone qui lit un nom de prestation en francais comprend
qu'elle lit du francais ; devant une case vide, elle croit la page cassee.
"""

from __future__ import annotations


class Traduit:
    """A poser sur un serialiseur dont certains champs se traduisent.

    `champs_traduits` enumere ce qui peut etre remplace. La liste est repetee
    ici, et non lue dans le registre : un serialiseur ne publie pas forcement
    tous les champs traduisibles de son modele, et remplacer un champ qu'il ne
    publie pas n'aurait aucun effet visible — mais masquerait une divergence.
    """

    champs_traduits: tuple[str, ...] = ()

    def to_representation(self, instance):
        donnees = super().to_representation(instance)

        table = self.context.get("traductions")
        if not table:
            return donnees

        etiquette = instance._meta.label_lower
        identifiant = str(instance.pk)
        for champ in self.champs_traduits:
            texte = table.get((etiquette, identifiant, champ))
            if texte:
                donnees[champ] = texte
        return donnees
