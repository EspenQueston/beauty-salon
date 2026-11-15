"""L'appel au modele de langue, et ce qu'on lui demande exactement.

---------------------------------------------------------------------------
Pourquoi un modele de langue plutot qu'un traducteur automatique
---------------------------------------------------------------------------

Le vocabulaire est celui du cheveu afro, et c'est precisement la ou une
traduction mot a mot se trompe. « Pose de gel » n'est pas « gel laying ».
« Depose » n'est pas « deposit » — c'est le retrait d'une pose precedente.
« Meches » designe tantot des extensions, tantot un balayage. Et une bonne
part du vocabulaire est **deja anglaise** : cornrows, Fulani braids, twist-out,
box braids. Les retraduire serait les abimer.

Un modele a qui l'on explique le metier garde ces mots-la et traduit le reste.

---------------------------------------------------------------------------
Ou vit la cle
---------------------------------------------------------------------------

Dans `apps/api/.env`, sous `OPENAI_API_KEY`, et nulle part ailleurs. Ce fichier
est ignore par git (`.gitignore:46`). La cle ne parait dans aucun fichier
versionne, dans aucun journal, et ne traverse jamais le navigateur : cet appel
part du serveur Django, pendant une tache de fond.

---------------------------------------------------------------------------
Ce qui protege la reponse
---------------------------------------------------------------------------

Le texte a traduire est ecrit par un salon, et un salon peut ecrire n'importe
quoi — y compris une phrase qui ressemble a une consigne. Trois choses font que
cela ne porte pas a consequence :

- le resultat n'est **que du texte**, range dans une colonne et rendu par
  React, qui l'echappe ;
- il s'affiche a la place du texte de ce meme salon, sur le mini-site de ce
  meme salon : dans le pire des cas, un salon abime sa propre page, ce qu'il
  peut deja faire en francais ;
- la reponse est **verifiee de forme** : un objet JSON dont les cles sont
  exactement celles demandees. Tout le reste est ecarte, et le champ garde
  alors son texte francais.

---------------------------------------------------------------------------
Sans cle
---------------------------------------------------------------------------

`disponible()` repond faux, rien n'est appele, et les mini-sites servent le
francais. C'est une degradation, pas une panne — et c'est ce qui permet aux
tests de tourner sans reseau, en posant un traducteur factice.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

LANGUES = {"fr": "francais", "en": "anglais"}

CONSIGNE = """\
Tu traduis le contenu du mini-site d'un salon de beaute vers l'{cible}.

Le metier : coiffure afro, tresses, perruques et tissages, soin du cheveu,
ongles, maquillage, barbier. Les salons sont au Congo-Brazzaville, en RDC et
dans la diaspora chinoise.

Regles :
1. Garde tels quels les termes de metier deja anglais ou intraduisibles :
   cornrows, box braids, Fulani braids, twist-out, knotless, closure, frontal,
   lace, brushing, balayage, baby hair.
2. Ne traduis jamais un nom propre : nom de salon, de personne, de marque, de
   quartier, de ville.
3. Garde le registre : ce sont des intitules de prestations et des textes de
   vitrine, pas de la documentation. Court reste court.
4. Garde la ponctuation et les retours a la ligne du texte source.
5. Si un texte est deja dans la langue cible, rends-le inchange.

Reponds uniquement par un objet JSON dont les cles sont exactement celles
recues, et les valeurs les traductions. Aucun commentaire, aucun texte autour.\
"""


@dataclass(frozen=True)
class Demande:
    """Un lot de textes a traduire, identifies par une cle stable."""

    cible: str
    textes: dict[str, str]


class Traducteur:
    """Le traducteur de production, adosse a l'API OpenAI."""

    #: Le modele est un reglage, pas une constante : il changera.
    modele = "gpt-4o-mini"

    def disponible(self) -> bool:
        return bool(getattr(settings, "OPENAI_API_KEY", ""))

    def traduire(self, demande: Demande) -> dict[str, str]:
        """Les textes traduits, par cle. Une cle absente n'a pas ete traduite.

        Ne leve jamais : un service de traduction indisponible doit laisser le
        mini-site en francais, pas le casser. L'appelant reconnait l'echec a
        l'absence de la cle.
        """
        if not self.disponible() or not demande.textes:
            return {}

        try:
            from openai import OpenAI
        except ImportError:  # pragma: no cover - depend de l'installation
            logger.warning("le paquet openai n'est pas installe : aucune traduction")
            return {}

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        consigne = CONSIGNE.format(cible=LANGUES.get(demande.cible, demande.cible))

        try:
            reponse = client.chat.completions.create(
                model=self.modele,
                # Le mode JSON du modele : il ne peut plus repondre autre chose
                # qu'un objet. La verification de forme reste, parce qu'un objet
                # valide peut encore porter des cles qu'on n'a pas demandees.
                response_format={"type": "json_object"},
                # Une traduction n'a pas a varier d'un appel a l'autre : la meme
                # prestation doit rendre le meme intitule.
                temperature=0,
                messages=[
                    {"role": "system", "content": consigne},
                    {
                        "role": "user",
                        "content": json.dumps(demande.textes, ensure_ascii=False),
                    },
                ],
            )
        except Exception:  # noqa: BLE001 - toute panne vaut « pas de traduction »
            logger.exception("traduction impossible")
            return {}

        brut = (reponse.choices[0].message.content or "").strip()
        return valider(brut, demande.textes)


def valider(brut: str, attendus: dict[str, str]) -> dict[str, str]:
    """Ne retient d'une reponse que ce qui a la forme demandee.

    Un modele peut encadrer son JSON de ``` ou d'une phrase. On tolere
    l'enveloppe, jamais autre chose : une cle inconnue, une valeur qui n'est pas
    une chaine, ou une chaine vide sont ecartees — un champ qui perd son texte
    est pire qu'un champ non traduit.
    """
    texte = brut.strip()
    if texte.startswith("```"):
        texte = texte.split("\n", 1)[-1]
        texte = texte.rsplit("```", 1)[0]

    debut, fin = texte.find("{"), texte.rfind("}")
    if debut < 0 or fin <= debut:
        logger.warning("reponse de traduction sans objet JSON")
        return {}

    try:
        decode = json.loads(texte[debut : fin + 1])
    except json.JSONDecodeError:
        logger.warning("reponse de traduction illisible")
        return {}

    if not isinstance(decode, dict):
        return {}

    return {
        cle: valeur.strip()
        for cle, valeur in decode.items()
        if cle in attendus and isinstance(valeur, str) and valeur.strip()
    }


class TraducteurFactice(Traducteur):
    """Le traducteur des tests : prefixe, pas de reseau, resultat previsible."""

    def __init__(self, prefixe: str = "[en] ") -> None:
        self.prefixe = prefixe

    def disponible(self) -> bool:
        return True

    def traduire(self, demande: Demande) -> dict[str, str]:
        return {cle: f"{self.prefixe}{texte}" for cle, texte in demande.textes.items()}
