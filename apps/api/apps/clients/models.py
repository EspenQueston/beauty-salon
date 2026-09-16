"""Comptes des clientes finales.

---------------------------------------------------------------------------
Pourquoi un compte au niveau plateforme, et pas par salon
---------------------------------------------------------------------------

Une cliente de Guangzhou frequente parfois deux salons : l'un pour les
tresses, l'autre pour les ongles. Lui demander deux comptes, deux mots de
passe et deux historiques serait absurde. Le compte vit donc au-dessus des
salons.

Cela ne casse pas l'isolation. Un salon ne voit toujours que *sa* fiche
cliente : c'est le compte qui, lui, sait a quels salons il est rattache, et
chaque lecture d'historique se fait dans le contexte du salon concerne, un
salon a la fois.

---------------------------------------------------------------------------
Pourquoi reutiliser `User` plutot qu'un modele separe
---------------------------------------------------------------------------

`User` porte deja l'e-mail, le telephone, le hachage du mot de passe, les
sessions, la reinitialisation par e-mail et les limitations de debit - tout
cela teste. Un second systeme d'authentification parallele aurait duplique
la surface la plus sensible du produit pour n'ajouter que des champs.

Ce qui distingue une cliente d'un membre d'equipe n'est donc pas son type,
c'est ce qu'elle possede : un `ClientProfile` et aucune `Membership`.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ClientProfile(models.Model):
    """Ce qu'on sait d'une cliente au niveau plateforme."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_profile",
        primary_key=True,
    )

    # WhatsApp en Afrique centrale, WeChat en Chine : ce sont les deux canaux
    # reels de la clientele visee, et rarement le meme numero que la ligne
    # principale.
    whatsapp = models.CharField(_("WhatsApp"), max_length=32, blank=True)
    wechat = models.CharField(_("WeChat"), max_length=64, blank=True)

    preferred_salon = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("salon favori"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("compte cliente")
        verbose_name_plural = _("comptes clientes")

    def __str__(self) -> str:
        return self.user.email


class ClientSalonLink(models.Model):
    """Rattachement d'un compte a la fiche cliente d'un salon.

    Cette table est volontairement **hors RLS** : c'est la seule facon de
    repondre a « a quels salons ce compte est-il rattache ? » sans lire les
    donnees d'un salon depuis le contexte d'un autre.

    Elle ne contient rien de sensible - un identifiant de salon, un
    identifiant de fiche - et sert d'index pour aller ensuite lire chaque
    historique **dans le contexte de son propre salon**. L'isolation est
    donc preservee : on ne fait jamais une requete qui traverse les salons,
    on en fait une par salon.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="salon_links",
    )
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="client_links"
    )
    # Identifiant nu, sans cle etrangere : la fiche vit derriere une
    # politique RLS, une contrainte referentielle depuis une table hors RLS
    # n'aurait pas de sens.
    customer_id = models.UUIDField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("rattachement à un salon")
        verbose_name_plural = _("rattachements aux salons")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "tenant"), name="one_link_per_client_and_salon"
            )
        ]
        indexes = [models.Index(fields=["user"])]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.tenant_id}"


class HiddenBooking(models.Model):
    """Une visite que la cliente a retiree de son historique.

    -----------------------------------------------------------------------
    Retirer, et non supprimer
    -----------------------------------------------------------------------

    Le rendez-vous appartient au salon : il porte son chiffre d'affaires, ses
    acomptes, ses lignes de recette. Le laisser effacer par la cliente
    reecrirait la comptabilite de quelqu'un d'autre.

    Ce que la cliente controle, c'est **sa propre vue**. La ligne disparait
    de son espace, le salon garde ses livres entiers. C'est aussi ce qui rend
    le geste sans danger : rien ne se perd, donc rien ne demande de
    confirmation angoissante.

    Hors RLS pour la meme raison que `ClientSalonLink` : la table est
    interrogee depuis le compte, qui traverse les salons, et elle ne contient
    qu'un couple d'identifiants.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hidden_bookings",
    )
    # Identifiant nu : le rendez-vous vit derriere une politique RLS.
    booking_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("visite masquée")
        verbose_name_plural = _("visites masquées")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "booking_id"), name="one_hidden_row_per_booking"
            )
        ]
        indexes = [models.Index(fields=["user"])]

    def __str__(self) -> str:
        return str(self.booking_id)
