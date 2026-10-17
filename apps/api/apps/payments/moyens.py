"""Les moyens d'encaissement des acomptes, selon le pays du salon.

Le salon encaisse sur son propre compte : la plateforme n'est jamais sur le
chemin de l'argent. Encore faut-il que le moyen existe là où il exerce — un
salon de Brazzaville qui publierait un QR Alipay, ou un « Orange Money » que
personne n'a au Congo, enverrait ses clientes dans une impasse.

Les opérateurs par pays viennent du catalogue réel des réseaux Mobile Money
(SASPAY, `GET /networks/`, lu le 16/10/2026) et des pays KKIAPAY :

  - Mobile Money (MTN MoMo, M-Pesa, Moov, Wave… ; l'opérateur s'écrit dans
    les consignes) : partout en Afrique ;
  - Orange Money et Airtel Money : là où l'opérateur est présent ;
  - virement bancaire : partout en Afrique ;
  - WeChat Pay et Alipay : en Chine.

Le serveur applique cette liste à la création d'un moyen, et à ce que voit
la cliente : un moyen d'un autre pays (le salon a déménagé, par exemple)
n'est plus proposé, sans être effacé.
"""

from .models import PaymentChannel

K = PaymentChannel.Kind

ORANGE_MONEY = {"BF", "CD", "CI", "CM", "GN", "ML", "SN"}
AIRTEL_MONEY = {"CD", "CG", "GH", "KE", "MW", "NE", "NG", "RW", "TZ", "UG", "ZM"}


def moyens_du_pays(pays: str) -> list[str]:
    """Les moyens à proposer à un salon de `pays`, dans l'ordre d'affichage."""
    if pays == "CN":
        return [K.WECHAT, K.ALIPAY]
    moyens = [K.MOBILE_MONEY]
    if pays in ORANGE_MONEY:
        moyens.append(K.ORANGE_MONEY)
    if pays in AIRTEL_MONEY:
        moyens.append(K.AIRTEL_MONEY)
    moyens.append(K.BANK)
    return [str(m) for m in moyens]


def propose(kind: str, pays: str) -> bool:
    return kind in moyens_du_pays(pays)
