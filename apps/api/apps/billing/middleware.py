"""L'abonnement, applique cote serveur.

---------------------------------------------------------------------------
Pourquoi un middleware et pas une permission par vue
---------------------------------------------------------------------------

Parce qu'une regle d'acces ne doit pas dependre de chaque vue qui s'en
souvient. Une permission DRF s'ajoute vue par vue ; la premiere vue d'ecriture
ajoutee demain sans elle rouvrirait le tableau de bord d'un salon qui ne paie
plus. Ici, toute ecriture sous `/api/v1/` passe par le meme controle, et ce
sont les exceptions qui sont listees — pas l'inverse.

---------------------------------------------------------------------------
Ce qui se ferme, ce qui reste ouvert
---------------------------------------------------------------------------

Quand l'acces est ferme (periode et grace de 3 jours echues, ou suspension) :

  - cote public, **seules les nouvelles demandes** sont refusees : une
    reservation, une inscription en liste d'attente. La cliente qui a deja
    reserve peut toujours payer son acompte, annuler ou laisser un avis — son
    rendez-vous existe, et elle n'y est pour rien ;
  - cote tableau de bord, toute ecriture est refusee, sauf ce qui sert a
    payer ou a rester joignable : l'abonnement lui-meme, la session, les
    notifications ;
  - les lectures passent toujours : le salon voit ses donnees, rien n'est
    cache ni efface.

Monte **apres** `TenantContextMiddleware`, donc dans le contexte du salon :
la lecture de l'abonnement y est soumise aux politiques RLS comme le reste.
"""

from __future__ import annotations

from django.http import JsonResponse

from .services import acces_du_salon

LECTURES = frozenset({"GET", "HEAD", "OPTIONS"})

# Les deux seules creations publiques : ce sont elles qui s'arretent.
CREATIONS_PUBLIQUES = frozenset({"/api/v1/public/bookings", "/api/v1/public/waitlist"})

# Ecritures du tableau de bord permises sans abonnement actif. Chaque entree
# couvre le chemin lui-meme et ce qui est sous lui, par segment entier :
# `/api/v1/subscription` n'ouvre pas une route future `/api/v1/subscriptions`.
PERMISES_SANS_ABONNEMENT = (
    "/api/v1/subscription",
    "/api/v1/auth",
    "/api/v1/notifications",
    "/api/v1/push",
    "/api/v1/csrf",
    "/api/v1/account",
)


def _permise(chemin: str) -> bool:
    return any(chemin == base or chemin.startswith(base + "/") for base in PERMISES_SANS_ABONNEMENT)


class AccesAbonnementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant_id = getattr(request, "tenant_id", None)
        if tenant_id and request.method not in LECTURES and request.path.startswith("/api/v1/"):
            refus = self._refus(request.path.rstrip("/"), tenant_id)
            if refus is not None:
                return refus
        return self.get_response(request)

    def _refus(self, chemin: str, tenant_id) -> JsonResponse | None:
        if chemin.startswith("/api/v1/public/"):
            if chemin not in CREATIONS_PUBLIQUES or acces_du_salon(tenant_id).ouvert:
                return None
            return JsonResponse(
                {
                    "detail": (
                        "Les réservations en ligne de ce salon sont momentanément "
                        "indisponibles. Contactez-le directement."
                    ),
                    "code": "reservations_indisponibles",
                },
                status=403,
            )

        if _permise(chemin):
            return None
        acces = acces_du_salon(tenant_id)
        if acces.ouvert:
            return None
        detail = (
            "Cet abonnement est suspendu. Contactez le support de la plateforme."
            if acces.raison == "suspendu"
            else (
                "Votre abonnement a expiré : le tableau de bord est en lecture "
                "seule. Réglez votre abonnement depuis la page Abonnement pour "
                "tout rouvrir."
            )
        )
        # 402 « paiement requis » : c'est exactement ce que dit la reponse, et
        # le frontend s'en sert pour proposer le lien vers la page Abonnement.
        return JsonResponse(
            {"detail": detail, "code": "abonnement_requis", "raison": acces.raison},
            status=402,
        )
