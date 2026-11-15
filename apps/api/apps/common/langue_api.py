"""Les reponses de l'API dans la langue de la page qui les demande.

L'espace pro envoie la langue de sa page (`Accept-Language`), le mini-site
la passe en `?lang=`. Pour une requete d'API qui demande l'anglais, ce
middleware :

1. active l'anglais le temps de la requete — les messages de Django et de
   DRF (« This field is required. », regles de mot de passe, limitation de
   debit) sortent alors directement en anglais ;
2. traduit, a la sortie, les messages propres au produit (`detail`,
   `message`, erreurs de validation) avec `common.messages_en`.

Il se place juste apres `LocaleMiddleware`, donc autour de tous les autres :
les refus poses par un middleware (abonnement expire, salon introuvable)
passent par lui comme les reponses des vues.

L'administration n'est pas concernee : elle reste en francais, la langue de
l'equipe qui l'utilise. Seules les donnees de message sont touchees — un
nom de cliente ou une note qui ressemblerait a un message ne l'est pas,
parce que seules les cles de message sont relues.
"""

from __future__ import annotations

import json

from django.utils import translation

from apps.translations.langue import LANGUE_SOURCE, demandee

from .messages_en import traduire

PREFIXE_API = "/api/"
CLES_MESSAGE = ("detail", "message")


def _traduire_tout(valeur):
    """Chaque chaine, a toute profondeur."""
    if isinstance(valeur, str):
        return traduire(valeur)
    if isinstance(valeur, list):
        return [_traduire_tout(v) for v in valeur]
    if isinstance(valeur, dict):
        return {cle: _traduire_tout(v) for cle, v in valeur.items()}
    return valeur


def traduire_reponse(donnees, *, erreur: bool):
    """Les messages d'une reponse JSON, en anglais.

    - Une reponse qui porte `detail` ou `message` : seuls ceux-ci sont
      traduits (une erreur de validation y range ses champs). Le reste —
      un rendez-vous joint a un refus, par exemple — est de la donnee.
    - Une erreur sans ces cles est une erreur de validation brute
      ({champ: [messages]}) : tout y est message, sauf `code`.
    """
    if not isinstance(donnees, dict):
        return donnees
    if any(cle in donnees for cle in CLES_MESSAGE):
        return {
            cle: _traduire_tout(v) if cle in CLES_MESSAGE else v for cle, v in donnees.items()
        }
    if erreur:
        return {cle: v if cle == "code" else _traduire_tout(v) for cle, v in donnees.items()}
    return donnees


class LangueApiMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(PREFIXE_API):
            return self.get_response(request)

        langue = demandee(request)
        translation.activate(langue)
        request.LANGUAGE_CODE = langue
        response = self.get_response(request)

        if langue != LANGUE_SOURCE:
            self._traduire(response)
        return response

    @staticmethod
    def _traduire(response) -> None:
        if getattr(response, "streaming", False):
            return
        if "application/json" not in response.get("Content-Type", ""):
            return
        erreur = response.status_code >= 400
        contenu = response.content
        # Une reponse reussie sans message n'a rien a traduire : on ne
        # relit pas une liste de rendez-vous pour rien.
        if not erreur and b'"detail"' not in contenu and b'"message"' not in contenu:
            return
        try:
            donnees = json.loads(contenu)
        except ValueError:
            return
        traduites = traduire_reponse(donnees, erreur=erreur)
        if traduites == donnees:
            return
        response.content = json.dumps(traduites, ensure_ascii=False).encode("utf-8")
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
