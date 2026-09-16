"""Noms lisibles pour les deux applications de django-otp.

Telles quelles, elles s'affichent « Otp_Totp » et « Otp_Static » dans
l'administration — deux intitulés que personne ne relie à la double
authentification. On ne peut pas modifier un paquet installé, mais on peut
lui substituer une configuration : c'est la façon prévue par Django, et elle
survit aux mises à jour de la dépendance.

Ces classes sont référencées depuis `INSTALLED_APPS`.
"""

from django_otp.plugins.otp_static.apps import DefaultConfig as StaticDefault
from django_otp.plugins.otp_totp.apps import DefaultConfig as TOTPDefault


class TOTPConfig(TOTPDefault):
    verbose_name = "Double authentification"


class StaticTokenConfig(StaticDefault):
    verbose_name = "Codes de secours"
