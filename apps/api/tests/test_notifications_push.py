"""Le systeme de notifications : qui est prevenu, et par quel chemin.

Ces tests couvrent trois choses que le reste de la suite ne verrait pas :

  - la regle de destination (la proprietaire et la gerante, pas l'equipe) ;
  - l'isolation : une notification appartient a un salon, et la couche
    PostgreSQL le tient meme si le filtre applicatif saute ;
  - le sort des abonnements push morts, qui sinon s'accumulent pour toujours.
"""

import socket
from datetime import timedelta

import pytest
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership
from apps.common.db import TENANT_GUC, tenant_context
from apps.notifications import evenements
from apps.notifications.models import (
    Genre,
    Notification,
    PlatformNotification,
    PushSubscription,
)
from apps.notifications.service import prevenir_salon
from conftest import as_tenant
from tests.factories import BookingFactory, MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"

# Une adresse de remise plausible. L'hote existe reellement : le garde SSRF
# resout le nom, et un domaine invente ferait echouer le test pour une
# mauvaise raison.
ENDPOINT = "https://fcm.googleapis.com/fcm/send/jeton-de-test-1"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def resolvant_vers(monkeypatch, ip: str) -> None:
    """Fait resoudre n'importe quel nom vers l'adresse donnee."""

    def faux(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 443))]

    monkeypatch.setattr(socket, "getaddrinfo", faux)


# ---------------------------------------------------------------------------
# Qui est prevenu
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_seuls_la_proprietaire_et_la_gerante_sont_prevenues(salon_a):
    """La regle de destination, prise a la lettre.

    Une prestataire qui recoit les acomptes de ses collegues coupe ses
    notifications au bout de trois jours — et manque ensuite celles qui la
    concernent. C'est la raison d'etre de ce filtre.
    """
    gerante = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=gerante, role=Membership.Role.MANAGER
    )
    prestataire = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=prestataire, role=Membership.Role.STAFF
    )
    accueil = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=accueil, role=Membership.Role.RECEPTIONIST
    )

    combien = prevenir_salon(
        salon_a.tenant.id, genre=Genre.RESERVATION, titre="Une cliente a réservé"
    )

    assert combien == 2
    with as_tenant(salon_a.tenant):
        prevenus = set(
            Notification.objects.values_list("recipient_id", flat=True)
        )
    assert prevenus == {salon_a.owner.id, gerante.id}
    assert prestataire.id not in prevenus
    assert accueil.id not in prevenus


@pytest.mark.django_db
def test_un_membre_desactive_n_est_plus_prevenu(salon_a):
    partie = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant,
        user=partie,
        role=Membership.Role.MANAGER,
        status=Membership.Status.DISABLED,
    )

    prevenir_salon(salon_a.tenant.id, genre=Genre.AVIS, titre="Nouvel avis")

    with as_tenant(salon_a.tenant):
        prevenus = set(Notification.objects.values_list("recipient_id", flat=True))
    assert prevenus == {salon_a.owner.id}


@pytest.mark.django_db
def test_un_salon_sans_encadrement_ne_fait_pas_echouer_l_evenement(salon_a):
    """Zero destinataire n'est pas une erreur.

    Un salon dont la gerante vient d'etre desactivee n'a personne a
    prevenir. Lever ici ferait echouer la reservation qui a declenche
    l'appel — une cliente perdrait son creneau.
    """
    Membership.objects.filter(tenant=salon_a.tenant).update(
        status=Membership.Status.DISABLED
    )

    assert prevenir_salon(salon_a.tenant.id, genre=Genre.AVIS, titre="Avis") == 0


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_notification_ne_traverse_pas_d_un_salon_a_l_autre(salon_a, salon_b):
    prevenir_salon(salon_a.tenant.id, genre=Genre.RESERVATION, titre="Chez A")

    with as_tenant(salon_b.tenant):
        assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_la_politique_postgresql_tient_sans_le_filtre_applicatif(salon_a, salon_b):
    """Le filet du dessous, teste sans passer par Django.

    `all_tenants` contourne volontairement le manager filtre. Ce qui doit
    rester vrai, c'est que la base elle-meme ne rend rien hors du bon
    contexte — sinon l'isolation ne tiendrait qu'a un gestionnaire Python.
    """
    prevenir_salon(salon_a.tenant.id, genre=Genre.RESERVATION, titre="Chez A")

    with tenant_context(salon_b.tenant.id), connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM notifications_notification")
        assert cursor.fetchone()[0] == 0

    # Hors contexte, rien non plus : l'echec est ferme, jamais ouvert.
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, '', true)", [TENANT_GUC])
        cursor.execute("SELECT count(*) FROM notifications_notification")
        assert cursor.fetchone()[0] == 0


@pytest.mark.django_db
def test_deux_gerantes_du_meme_salon_ont_chacune_sa_boite(api_client, salon_a):
    autre = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=autre, role=Membership.Role.MANAGER)
    prevenir_salon(salon_a.tenant.id, genre=Genre.RESERVATION, titre="Une demande")

    login(api_client, salon_a.owner)
    reponse = api_client.get(reverse("notifications"))

    assert reponse.status_code == 200
    assert reponse.data["non_lues"] == 1
    assert len(reponse.data["resultats"]) == 1


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_marquer_tout_lu_remet_le_compteur_a_zero(api_client, salon_a):
    for index in range(3):
        prevenir_salon(
            salon_a.tenant.id, genre=Genre.RESERVATION, titre=f"Demande {index}"
        )

    login(api_client, salon_a.owner)
    assert api_client.get(reverse("notifications")).data["non_lues"] == 3

    reponse = api_client.post(
        reverse("notifications"), {"toutes": True}, format="json"
    )
    assert reponse.data["marquees"] == 3
    assert api_client.get(reverse("notifications")).data["non_lues"] == 0


@pytest.mark.django_db
def test_relire_ne_recompte_pas(api_client, salon_a):
    """Ouvrir deux fois le panneau ne doit rien reecrire."""
    prevenir_salon(salon_a.tenant.id, genre=Genre.AVIS, titre="Avis")
    login(api_client, salon_a.owner)

    api_client.post(reverse("notifications"), {"toutes": True}, format="json")
    seconde = api_client.post(reverse("notifications"), {"toutes": True}, format="json")

    assert seconde.data["marquees"] == 0


@pytest.mark.django_db
def test_on_ne_peut_pas_marquer_lue_la_notification_d_une_autre(
    api_client, salon_a
):
    autre = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=autre, role=Membership.Role.MANAGER)
    prevenir_salon(salon_a.tenant.id, genre=Genre.RESERVATION, titre="Une demande")

    with as_tenant(salon_a.tenant):
        celle_de_l_autre = Notification.objects.get(recipient=autre)

    login(api_client, salon_a.owner)
    reponse = api_client.post(
        reverse("notifications"),
        {"ids": [str(celle_de_l_autre.id)]},
        format="json",
    )

    assert reponse.data["marquees"] == 0
    with as_tenant(salon_a.tenant):
        celle_de_l_autre.refresh_from_db()
    assert celle_de_l_autre.lu_le is None


# ---------------------------------------------------------------------------
# Abonnement d'un appareil
# ---------------------------------------------------------------------------


@override_settings(VAPID_PUBLIC_KEY="cle-publique", VAPID_PRIVATE_KEY="cle-privee")
@pytest.mark.django_db
def test_un_appareil_s_inscrit_et_se_retire(api_client, salon_a, monkeypatch):
    resolvant_vers(monkeypatch, "142.250.75.10")
    login(api_client, salon_a.owner)

    creation = api_client.post(
        reverse("push"),
        {
            "endpoint": ENDPOINT,
            "cle_p256dh": "BOaXY-cle-publique-du-navigateur",
            "cle_auth": "jeton-auth",
            "appareil": "Chrome sur Android",
        },
        format="json",
    )
    assert creation.status_code == 201
    assert PushSubscription.objects.filter(user=salon_a.owner).count() == 1

    retrait = api_client.delete(
        reverse("push"), {"endpoint": ENDPOINT}, format="json"
    )
    assert retrait.data["supprimes"] == 1
    assert PushSubscription.objects.count() == 0


@override_settings(VAPID_PUBLIC_KEY="cle-publique", VAPID_PRIVATE_KEY="cle-privee")
@pytest.mark.django_db
@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.20"]
)
def test_une_adresse_de_remise_interne_est_refusee(
    api_client, salon_a, monkeypatch, ip
):
    """Le champ decide ou le serveur ira poster : c'est une porte SSRF.

    169.254.169.254 est l'adresse des metadonnees cloud — celle qui rend les
    identifiants de la machine. La refuser n'est pas une precaution de
    principe.
    """
    resolvant_vers(monkeypatch, ip)
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        reverse("push"),
        {
            "endpoint": "https://interne.exemple/push/1",
            "cle_p256dh": "cle",
            "cle_auth": "auth",
        },
        format="json",
    )

    assert reponse.status_code == 400
    assert PushSubscription.objects.count() == 0


@override_settings(VAPID_PUBLIC_KEY="cle-publique", VAPID_PRIVATE_KEY="cle-privee")
@pytest.mark.django_db
def test_une_adresse_en_clair_est_refusee(api_client, salon_a):
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        reverse("push"),
        {
            "endpoint": "http://fcm.googleapis.com/fcm/send/x",
            "cle_p256dh": "cle",
            "cle_auth": "auth",
        },
        format="json",
    )

    assert reponse.status_code == 400


@override_settings(VAPID_PUBLIC_KEY="cle-publique", VAPID_PRIVATE_KEY="cle-privee")
@pytest.mark.django_db
def test_sur_un_poste_partage_le_dernier_arrive_reprend_l_appareil(
    api_client, salon_a, monkeypatch
):
    """Deux comptes, un seul navigateur.

    L'adresse de remise designe le navigateur, pas la personne. Si l'ancienne
    ligne survivait, la seconde recevrait les notifications de la premiere.
    """
    resolvant_vers(monkeypatch, "142.250.75.10")
    seconde = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=seconde, role=Membership.Role.MANAGER
    )

    corps = {
        "endpoint": ENDPOINT,
        "cle_p256dh": "cle",
        "cle_auth": "auth",
        "appareil": "Poste de l'accueil",
    }

    login(api_client, salon_a.owner)
    api_client.post(reverse("push"), corps, format="json")
    api_client.logout()

    login(api_client, seconde)
    api_client.post(reverse("push"), corps, format="json")

    assert PushSubscription.objects.count() == 1
    assert PushSubscription.objects.get().user_id == seconde.id


@override_settings(VAPID_PUBLIC_KEY="cle-publique", VAPID_PRIVATE_KEY="cle-privee")
@pytest.mark.django_db
def test_on_ne_peut_pas_retirer_l_appareil_de_quelqu_un_d_autre(
    api_client, salon_a, monkeypatch
):
    resolvant_vers(monkeypatch, "142.250.75.10")
    victime = UserFactory()
    PushSubscription.objects.create(
        user=victime, endpoint=ENDPOINT, cle_p256dh="cle", cle_auth="auth"
    )

    login(api_client, salon_a.owner)
    reponse = api_client.delete(
        reverse("push"), {"endpoint": ENDPOINT}, format="json"
    )

    assert reponse.data["supprimes"] == 0
    assert PushSubscription.objects.count() == 1


@override_settings(VAPID_PUBLIC_KEY="cle-publique", VAPID_PRIVATE_KEY="cle-privee")
@pytest.mark.django_db
def test_la_portee_plateforme_est_refusee_a_qui_n_est_pas_administrateur(
    api_client, salon_a, monkeypatch
):
    """Sinon une gerante recevrait les alertes de facturation de la plateforme."""
    resolvant_vers(monkeypatch, "142.250.75.10")
    login(api_client, salon_a.owner)

    reponse = api_client.post(
        reverse("push"),
        {
            "endpoint": ENDPOINT,
            "cle_p256dh": "cle",
            "cle_auth": "auth",
            "portee": "plateforme",
        },
        format="json",
    )

    assert reponse.status_code == 403
    assert PushSubscription.objects.count() == 0


@pytest.mark.django_db
def test_sans_cles_vapid_aucun_abonnement_n_est_propose(api_client, salon_a):
    """Une installation sans cles garde la cloche, et ne ment pas sur le push."""
    login(api_client, salon_a.owner)

    reponse = api_client.get(reverse("push"))
    assert reponse.data == {"actif": False, "cle": "", "appareils": []}

    boite = api_client.get(reverse("notifications"))
    assert boite.data["push_actif"] is False


# ---------------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------------


@override_settings(VAPID_PUBLIC_KEY="cle-publique", VAPID_PRIVATE_KEY="cle-privee")
@pytest.mark.django_db
def test_un_abonnement_abandonne_par_le_service_est_supprime(
    salon_a, monkeypatch
):
    """404 et 410 veulent dire « cette boite n'existe plus ».

    La garder ferait reessayer a chaque evenement, pour toujours.
    """
    from apps.notifications import push, tasks

    abonnement = PushSubscription.objects.create(
        user=salon_a.owner, endpoint=ENDPOINT, cle_p256dh="cle", cle_auth="auth"
    )
    monkeypatch.setattr(push, "envoyer", lambda *a, **k: False)

    tasks.pousser_notification(
        [str(salon_a.owner.id)], PushSubscription.Portee.SALON, {"titre": "x"}
    )

    assert not PushSubscription.objects.filter(pk=abonnement.pk).exists()


@override_settings(VAPID_PUBLIC_KEY="cle-publique", VAPID_PRIVATE_KEY="cle-privee")
@pytest.mark.django_db
def test_un_echec_passager_ne_rejoue_que_l_appareil_fautif(salon_a, monkeypatch):
    """Le coeur de la reprise.

    Sans ce ciblage, une gerante a trois appareils en verrait deux sonner
    une seconde fois parce que le troisieme a repondu 500. La seconde
    notification apprend qu'il ne faut pas les lire.
    """
    from apps.notifications import push, tasks

    bon = PushSubscription.objects.create(
        user=salon_a.owner, endpoint=ENDPOINT, cle_p256dh="c", cle_auth="a"
    )
    mauvais = PushSubscription.objects.create(
        user=salon_a.owner,
        endpoint=ENDPOINT.replace("-1", "-2"),
        cle_p256dh="c",
        cle_auth="a",
    )

    servis = []

    def envoyer(abonnement, charge):
        if abonnement.pk == mauvais.pk:
            raise RuntimeError("503 passager")
        servis.append(abonnement.pk)
        return True

    monkeypatch.setattr(push, "envoyer", envoyer)

    reprises = {}

    class Reprise(Exception):
        """Ce que Celery leverait. Nommee, pour que le test ne passe pas si
        c'est une *autre* erreur qui remonte — une faute de frappe dans la
        tache, par exemple."""

    def fausse_reprise(**kwargs):
        reprises.update(kwargs.get("kwargs", {}))
        return Reprise()

    monkeypatch.setattr(tasks.pousser_notification, "retry", fausse_reprise)

    with pytest.raises(Reprise):
        tasks.pousser_notification(
            [str(salon_a.owner.id)], PushSubscription.Portee.SALON, {"titre": "x"}
        )

    assert servis == [bon.pk]
    assert reprises["abonnements"] == [str(mauvais.pk)]

    mauvais.refresh_from_db()
    assert mauvais.echecs == 1
    bon.refresh_from_db()
    assert bon.echecs == 0
    assert bon.derniere_reussite is not None


@override_settings(VAPID_PUBLIC_KEY="cle-publique", VAPID_PRIVATE_KEY="cle-privee")
@pytest.mark.django_db
def test_on_ne_pousse_jamais_vers_la_mauvaise_portee(salon_a, monkeypatch):
    """L'administration et le tableau de bord sont deux sites distincts.

    Pousser une notification de salon vers l'abonnement de l'administration
    ferait sonner un appareil pour un lien `/agenda` qui n'existe pas sur cet
    hote.
    """
    from apps.notifications import push, tasks

    PushSubscription.objects.create(
        user=salon_a.owner,
        endpoint=ENDPOINT,
        cle_p256dh="c",
        cle_auth="a",
        portee=PushSubscription.Portee.PLATEFORME,
    )
    touches = []
    monkeypatch.setattr(
        push, "envoyer", lambda a, c: touches.append(a.pk) or True
    )

    tasks.pousser_notification(
        [str(salon_a.owner.id)], PushSubscription.Portee.SALON, {"titre": "x"}
    )

    assert touches == []


# ---------------------------------------------------------------------------
# Les evenements metier
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_annulation_par_le_salon_ne_previent_pas_le_salon(salon_a):
    """Repeter a quelqu'un ce qu'il vient de faire est la meilleure facon de
    lui faire couper ses notifications."""
    with as_tenant(salon_a.tenant):
        debut = timezone.now() + timedelta(days=2)
        booking = BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=debut,
            ends_at=debut + timedelta(minutes=120),
        )

    evenements.rendez_vous_annule(booking, par_le_salon=True)
    with as_tenant(salon_a.tenant):
        assert Notification.objects.count() == 0

    evenements.rendez_vous_annule(booking, par_le_salon=False)
    with as_tenant(salon_a.tenant):
        assert Notification.objects.count() == 1


@pytest.mark.django_db
def test_une_panne_de_notification_ne_fait_pas_echouer_l_evenement(
    salon_a, monkeypatch
):
    """Le garde-fou qui compte le plus.

    Ces fonctions sont appelees au milieu d'une reservation. Si l'une d'elles
    laissait remonter une exception, une cliente perdrait son creneau parce
    qu'une notification n'a pas pu etre ecrite.
    """
    from apps.notifications import evenements as module

    def casse(*args, **kwargs):
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(module, "prevenir_salon", casse)

    with as_tenant(salon_a.tenant):
        debut = timezone.now() + timedelta(days=2)
        booking = BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=debut,
            ends_at=debut + timedelta(minutes=120),
        )

    # Ne doit rien lever.
    module.nouvelle_reservation(booking)


@pytest.mark.django_db
def test_l_inscription_d_un_salon_previent_la_plateforme(salon_a):
    admin_plateforme = UserFactory(is_platform_admin=True)
    autre_admin = UserFactory(is_platform_admin=True, is_active=False)

    evenements.salon_inscrit(salon_a.tenant)

    destinataires = set(
        PlatformNotification.objects.values_list("recipient_id", flat=True)
    )
    assert admin_plateforme.id in destinataires
    assert autre_admin.id not in destinataires
    assert salon_a.owner.id not in destinataires

    ligne = PlatformNotification.objects.filter(recipient=admin_plateforme).first()
    assert ligne.tenant_id == salon_a.tenant.id


@pytest.mark.django_db
def test_la_boite_plateforme_est_fermee_aux_salons(api_client, salon_a):
    login(api_client, salon_a.owner)
    assert api_client.get(reverse("platform-notifications")).status_code == 403


# ---------------------------------------------------------------------------
# L'administration plateforme
# ---------------------------------------------------------------------------


@pytest.mark.django_db(databases=["default", "admin"], transaction=True)
class TestCoteAdministration:
    """La cloche de l'administration, et le service worker qui la sert."""

    @pytest.fixture
    def admin_connecte(self, client):
        UserFactory(
            email="supervision@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
            is_platform_admin=True,
        )
        client.login(username="supervision@example.com", password=PASSWORD)
        return client

    def test_le_service_worker_est_servi_a_la_racine(self, client):
        """Servi sous `/static/`, sa portée ne couvrirait pas l'administration."""
        reponse = client.get("/sw-admin.js")

        assert reponse.status_code == 200
        assert reponse["Content-Type"].startswith("text/javascript")
        assert reponse["Service-Worker-Allowed"] == "/"
        # Il n'a le droit de faire qu'une chose : afficher une notification.
        contenu = b"".join(reponse.streaming_content).decode("utf-8")
        assert "addEventListener(\"push\"" in contenu
        assert "addEventListener(\"fetch\"" not in contenu

    def test_la_cloche_apparait_pour_un_compte_plateforme(self, admin_connecte):
        reponse = admin_connecte.get(reverse("admin:index"))

        assert reponse.status_code == 200
        page = reponse.content.decode("utf-8")
        assert 'id="cloche-plateforme"' in page
        assert "notifications/cloche.js" in page

    def test_la_cloche_n_apparait_pas_pour_un_compte_sans_supervision(self, client):
        """`is_staff` ouvre l'administration ; il n'ouvre pas la supervision.

        Sans ce test, un compte technique du salon verrait une cloche dont
        l'API lui répondrait 403 en boucle.
        """
        UserFactory(
            email="technique@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
            is_platform_admin=False,
        )
        client.login(username="technique@example.com", password=PASSWORD)

        page = client.get(reverse("admin:index")).content.decode("utf-8")
        assert 'id="cloche-plateforme"' not in page

    def test_la_boite_plateforme_se_lit_et_se_marque(self, admin_connecte, tenant_a):
        evenements.salon_inscrit(tenant_a)

        boite = admin_connecte.get(reverse("platform-notifications")).json()
        assert boite["non_lues"] == 1
        assert boite["resultats"][0]["salon"] == tenant_a.name

        marque = admin_connecte.post(
            reverse("platform-notifications"),
            data={"toutes": True},
            content_type="application/json",
        ).json()
        assert marque["marquees"] == 1
        assert admin_connecte.get(reverse("platform-notifications")).json()["non_lues"] == 0


# ---------------------------------------------------------------------------
# Le chiffrement
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_message_pousse_est_dechiffrable_par_le_navigateur():
    """Le bout de chaine qu'aucun autre test ne verrait.

    Entre `prevenir_salon()` et la notification affichee sur un telephone, il
    y a une couche de chiffrement : le serveur chiffre avec les cles que le
    navigateur lui a confiees, et les serveurs de Google ne font que
    transporter. Si elle etait mal branchee, tout passerait — le serveur
    repondrait 201, les journaux seraient propres — et aucun telephone ne
    sonnerait jamais.

    Ce test joue le navigateur : il fabrique une paire de cles, laisse
    pywebpush chiffrer, puis dechiffre avec la cle privee. Il verifie du meme
    coup que les accents survivent, ce qui n'est pas acquis : le message
    traverse `json.dumps`, un encodage UTF-8 implicite, puis AES-GCM.
    """
    import base64
    import json

    import http_ece
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from pywebpush import WebPusher

    def sans_bourrage(octets: bytes) -> str:
        return base64.urlsafe_b64encode(octets).decode().rstrip("=")

    # Le navigateur fictif fabrique sa paire et son secret d'authentification.
    prive = ec.generate_private_key(ec.SECP256R1())
    publique = prive.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    auth = b"0123456789abcdef"

    abonnement = {
        "endpoint": ENDPOINT,
        "keys": {"p256dh": sans_bourrage(publique), "auth": sans_bourrage(auth)},
    }

    charge = {
        "genre": "acompte_a_verifier",
        "titre": "Acompte à vérifier",
        "corps": "Aïcha Mbemba — le 24/09 à 14:30",
        "lien": "/agenda",
    }
    message = json.dumps(charge, ensure_ascii=False)

    # `webpush()` encode une chaine en UTF-8 avant de chiffrer ; ici on
    # appelle la couche du dessous, qui exige deja des octets.
    chiffre = WebPusher(abonnement).encode(message.encode("utf-8"))

    clair = http_ece.decrypt(
        chiffre["body"],
        private_key=prive,
        auth_secret=auth,
        version="aes128gcm",
    )

    assert json.loads(clair.decode("utf-8")) == charge
