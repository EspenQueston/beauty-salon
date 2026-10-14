"""Export Excel : deux feuilles, un seul fichier.

Un classeur plutot que deux fichiers CSV parce que c'est ce dont un salon a
besoin au moment ou il exporte : porter sa comptabilite a quelqu'un. Deux
fichiers separes se perdent, et un CSV s'ouvre de travers des qu'une
description contient une virgule ou un accent.

Les feuilles sont deliberement plates - une ligne, un mouvement, pas de
formule. Un tableur qu'on peut trier et filtrer sans rien comprendre au
fichier vaut mieux qu'un rapport elegant que personne n'ose modifier.

Le classeur parle la langue de la page qui l'a demande : titres, feuilles,
postes, moyens et libelles automatiques. Ce que le salon a saisi lui-meme
reste tel quel.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from apps.translations.langue import normaliser

from . import libelles
from .models import Transaction

HEADER_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
TOTAL_FONT = Font(bold=True)

#: Largeur de chaque colonne, dans l'ordre.
LARGEURS = (12, 34, 24, 26, 16, 14, 40)

MOTS = {
    "fr": {
        "colonnes": (
            "Date", "Libellé", "Poste", "Origine / bénéficiaire", "Moyen", "Montant", "Détail",
        ),
        "recettes": "Recettes",
        "depenses": "Dépenses",
        "synthese": "Synthèse",
        "resultat": "Résultat",
        "total": "Total",
        "export": "Export du {date}",
        "detail": "Le détail est dans les feuilles « Recettes » et « Dépenses ».",
    },
    "en": {
        "colonnes": (
            "Date", "Label", "Category", "Source / payee", "Method", "Amount", "Details",
        ),
        "recettes": "Income",
        "depenses": "Expenses",
        "synthese": "Summary",
        "resultat": "Profit",
        "total": "Total",
        "export": "Exported on {date}",
        "detail": "Details are in the \u201cIncome\u201d and \u201cExpenses\u201d sheets.",
    },
}

# La version francaise, pour qui lirait les colonnes sans langue.
COLUMNS = list(zip(MOTS["fr"]["colonnes"], LARGEURS, strict=True))


def build_workbook(queryset, currency: str, salon_name: str, langue: str = "fr") -> bytes:
    """Classeur a deux feuilles : recettes d'un cote, depenses de l'autre."""
    langue = normaliser(langue)
    mots = MOTS[langue]
    workbook = Workbook()
    workbook.remove(workbook.active)

    rows = list(queryset.order_by("occurred_on", "created_at"))

    _sheet(
        workbook,
        title=mots["recettes"],
        rows=[row for row in rows if row.kind == Transaction.Kind.INCOME],
        currency=currency,
        langue=langue,
    )
    _sheet(
        workbook,
        title=mots["depenses"],
        rows=[row for row in rows if row.kind == Transaction.Kind.EXPENSE],
        currency=currency,
        langue=langue,
    )
    _summary(workbook, rows=rows, currency=currency, salon_name=salon_name, langue=langue)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _sheet(
    workbook: Workbook, *, title: str, rows: list, currency: str, langue: str = "fr"
) -> None:
    mots = MOTS[langue]
    sheet = workbook.create_sheet(title=title)

    colonnes = zip(mots["colonnes"], LARGEURS, strict=True)
    for index, (label, width) in enumerate(colonnes, start=1):
        cell = sheet.cell(row=1, column=index, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
        sheet.column_dimensions[get_column_letter(index)].width = width

    for line, row in enumerate(rows, start=2):
        sheet.cell(row=line, column=1, value=row.occurred_on).number_format = (
            "DD/MM/YYYY"
        )
        sheet.cell(row=line, column=2, value=libelles.libelle(row, langue))
        # Des chaines, toujours : les libelles francais viennent de
        # `gettext_lazy`, et openpyxl ne sait pas serialiser ces objets de
        # traduction differee — il leve une erreur a l'ecriture.
        sheet.cell(row=line, column=3, value=libelles.poste(row, langue))
        sheet.cell(row=line, column=4, value=row.counterparty)
        sheet.cell(row=line, column=5, value=libelles.moyen(row, langue))
        # Le montant reste un nombre, jamais une chaine : c'est ce qui permet
        # de trier et d'additionner dans le tableur.
        amount = sheet.cell(row=line, column=6, value=float(row.amount))
        amount.number_format = f'#,##0.00 "{currency}"'
        sheet.cell(row=line, column=7, value=row.note)

    total_line = len(rows) + 2
    sheet.cell(row=total_line, column=5, value=mots["total"]).font = TOTAL_FONT
    total = sheet.cell(
        row=total_line,
        column=6,
        # Une formule plutot qu'une valeur figee : le total suit si
        # quelqu'un filtre ou corrige une ligne dans son tableur.
        value=f"=SUM(F2:F{max(total_line - 1, 2)})" if rows else 0,
    )
    total.font = TOTAL_FONT
    total.number_format = f'#,##0.00 "{currency}"'

    # Le filtre automatique rend la feuille utilisable sans rien savoir
    # d'Excel : trier par date ou par poste tient en un clic.
    if rows:
        sheet.auto_filter.ref = f"A1:G{len(rows) + 1}"
    sheet.freeze_panes = "A2"


def _summary(
    workbook: Workbook, *, rows: list, currency: str, salon_name: str, langue: str = "fr"
) -> None:
    mots = MOTS[langue]
    sheet = workbook.create_sheet(title=mots["synthese"], index=0)
    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 18

    income = sum(
        (row.amount for row in rows if row.kind == Transaction.Kind.INCOME),
        Decimal("0"),
    )
    expense = sum(
        (row.amount for row in rows if row.kind == Transaction.Kind.EXPENSE),
        Decimal("0"),
    )

    title = sheet.cell(row=1, column=1, value=str(salon_name))
    title.font = Font(bold=True, size=14)
    aujourd_hui = f"{date.today():%d/%m/%Y}"
    sheet.cell(row=2, column=1, value=mots["export"].format(date=aujourd_hui))

    lines = [
        (mots["recettes"], income),
        (mots["depenses"], expense),
        (mots["resultat"], income - expense),
    ]
    for offset, (label, value) in enumerate(lines, start=4):
        sheet.cell(row=offset, column=1, value=label).font = TOTAL_FONT
        cell = sheet.cell(row=offset, column=2, value=float(value))
        cell.number_format = f'#,##0.00 "{currency}"'
        cell.font = TOTAL_FONT

    sheet.cell(
        row=8,
        column=1,
        value=mots["detail"],
    )
