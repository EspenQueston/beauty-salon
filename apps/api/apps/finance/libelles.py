"""Les libelles des comptes, dans la langue de qui les lit.

Les ecritures automatiques — un acompte encaisse, un deplacement, l'abonnement
a la plateforme — sont enregistrees avec un libelle francais compose au
moment de l'ecriture (« Acompte — Box braids »). Le livre de comptes ne se
reecrit pas : c'est a la lecture, ecran ou export Excel, que ces libelles
sont dits en anglais. Une ecriture saisie a la main reste telle que le salon
l'a ecrite, comme tout contenu qui lui appartient.
"""

from __future__ import annotations

from apps.translations.langue import normaliser

POSTES_EN = {
    "service": "Service",
    "product": "Product sale",
    "travel": "Travel",
    "tip": "Tip",
    "other_income": "Other income",
    "supplies": "Supplies and products",
    "rent": "Rent",
    "wages": "Wages",
    "utilities": "Water, electricity, internet",
    "transport": "Transport and travel",
    "marketing": "Advertising",
    "equipment": "Equipment",
    "taxes": "Taxes",
    "other_expense": "Other expense",
}

MOYENS_EN = {
    "cash": "Cash",
    "mobile_money": "Mobile Money",
    "transfer": "Bank transfer",
    "card": "Card",
    "wechat": "WeChat Pay",
    "alipay": "Alipay",
    "other": "Other",
}

#: Les debuts de libelle des ecritures automatiques (voir finance/services.py).
PREFIXES_EN = (
    ("Acompte — ", "Deposit — "),
    ("Déplacement — ", "Travel — "),
    ("Abonnement Beauty Salon", "Beauty Salon subscription"),
)
EXACTS_EN = {
    "Vente au comptoir": "Counter sale",
    "Prestation": "Service",
    "Acompte — prestation": "Deposit — service",
}


def _anglais(langue) -> bool:
    return normaliser(langue) == "en"


def libelle(transaction, langue) -> str:
    if not _anglais(langue) or transaction.source == "manual":
        return transaction.label
    if transaction.label in EXACTS_EN:
        return EXACTS_EN[transaction.label]
    for francais, anglais in PREFIXES_EN:
        if transaction.label.startswith(francais):
            return anglais + transaction.label[len(francais):]
    return transaction.label


def poste(transaction, langue) -> str:
    if _anglais(langue):
        return POSTES_EN.get(transaction.category, str(transaction.category_label))
    return str(transaction.category_label)


def moyen(transaction, langue) -> str:
    if _anglais(langue):
        return MOYENS_EN.get(transaction.method, transaction.method)
    return str(transaction.get_method_display())
