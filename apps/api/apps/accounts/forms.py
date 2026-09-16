"""Formulaires d'administration.

Les formulaires par defaut de django.contrib.auth ciblent le modele User
historique et son champ `username` ; ils sont inutilisables tels quels avec
un modele personnalise identifie par e-mail.
"""

from django.contrib.auth.forms import BaseUserCreationForm
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm

from .models import User


class UserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("email", "display_name")


class UserChangeForm(BaseUserChangeForm):
    class Meta(BaseUserChangeForm.Meta):
        model = User
        fields = "__all__"
