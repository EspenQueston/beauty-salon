"""Le formulaire de connexion de l'administration plateforme, freine.

Le formulaire de Django n'a aucune limite de tentatives. La double
authentification tient la porte apres le mot de passe, mais un mot de passe
devine reste un secret perdu (souvent reutilise ailleurs). On applique donc
les memes freins que la connexion de l'API (voir `securite.py`) : par
adresse visee et par IP, sans dire si le compte existe.
"""

from functools import wraps

from django.contrib import messages
from django.http import HttpResponseRedirect
from rest_framework.throttling import BaseThrottle

from . import journal, securite


def freiner(vue_de_connexion):
    @wraps(vue_de_connexion)
    def connexion(request, extra_context=None):
        if request.method != "POST":
            return vue_de_connexion(request, extra_context)

        email = (request.POST.get("username") or "").strip().lower()
        ip = BaseThrottle().get_ident(request) or ""
        if securite.connexion_bloquee(email, ip):
            messages.error(
                request,
                "Trop de tentatives de connexion. Patientez quelques minutes avant de réessayer.",
            )
            return HttpResponseRedirect(request.get_full_path())

        reponse = vue_de_connexion(request, extra_context)
        if request.user.is_authenticated:
            securite.noter_succes(email)
            journal.consigner(
                "AUTH_LOGIN_SUCCEEDED", request=request, user=request.user, espace="admin"
            )
        else:
            if securite.noter_echec(email, ip):
                journal.consigner(
                    "AUTH_ACCOUNT_LOCKED", request=request, email=email, espace="admin"
                )
                journal.alerter_plateforme(
                    "Administration : connexions suspendues",
                    f"{email} : mots de passe faux en série sur l'administration.",
                )
            journal.consigner("AUTH_LOGIN_FAILED", request=request, email=email, espace="admin")
        return reponse

    return connexion
