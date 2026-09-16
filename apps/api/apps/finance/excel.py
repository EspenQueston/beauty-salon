"""Export Excel : deux feuilles, un seul fichier.

Un classeur plutot que deux fichiers CSV parce que c'est ce dont un salon a
besoin au moment ou il exporte : porter sa comptabilite a quelqu'un. Deux
fichiers separes se perdent, et un CSV s'ouvre de travers des qu'une
description contient une virgule ou un accent.

Les feuilles sont deliberement plates - une ligne, un mouvement, pas de
formule. Un tableur qu'on peut trier et filtrer sans rien comprendre au
fichier vaut mieux qu'un rapport elegant que personne n'ose modifier.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Transaction

HEADER_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
TOTAL_FONT = Font(bold=True)

COLUMNS = [
    ("Date", 12),
    ("Libellé", 34),
    ("Poste", 24),
    ("Origine / bénéficiaire", 26),
    ("Moyen", 16),
    ("Montant", 14),
    ("Détail", 40),
]


def build_workbook(queryset, currency: str, salon_name: str) -> bytes:
    """Classeur a deux feuilles : recettes d'un cote, depenses de l'autre."""
    workbook = Workbook()
    workbook.remove(workbook.active)

    rows = list(queryset.order_by("occurred_on", "created_at"))

    _sheet(
        workbook,
        title="Recettes",
        rows=[row for row in rows if row.kind == Transaction.Kind.INCOME],
        currency=currency,
    )
    _sheet(
        workbook,
        title="Dépenses",
        rows=[row for row in rows if row.kind == Transaction.Kind.EXPENSE],
        currency=currency,
    )
    _summary(workbook, rows=rows, currency=currency, salon_name=salon_name)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _sheet(workbook: Workbook, *, title: str, rows: list, currency: str) -> None:
    sheet = workbook.create_sheet(title=title)

    for index, (label, width) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=index, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
        sheet.column_dimensions[get_column_letter(index)].width = width

    methods = dict(Transaction.Method.choices)

    for line, row in enumerate(rows, start=2):
        sheet.cell(row=line, column=1, value=row.occurred_on).number_format = (
            "DD/MM/YYYY"
        )
        sheet.cell(row=line, column=2, value=row.label)
        # `str()` n'est pas decoratif : les libelles viennent de
        # `gettext_lazy`, donc ce sont des objets de traduction differee.
        # openpyxl ne sait pas les serialiser et leve une erreur a l'ecriture.
        sheet.cell(row=line, column=3, value=str(row.category_label))
        sheet.cell(row=line, column=4, value=row.counterparty)
        sheet.cell(row=line, column=5, value=str(methods.get(row.method, row.method)))
        # Le montant reste un nombre, jamais une chaine : c'est ce qui permet
        # de trier et d'additionner dans le tableur.
        amount = sheet.cell(row=line, column=6, value=float(row.amount))
        amount.number_format = f'#,##0.00 "{currency}"'
        sheet.cell(row=line, column=7, value=row.note)

    total_line = len(rows) + 2
    sheet.cell(row=total_line, column=5, value="Total").font = TOTAL_FONT
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


def _summary(workbook: Workbook, *, rows: list, currency: str, salon_name: str) -> None:
    sheet = workbook.create_sheet(title="Synthèse", index=0)
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
    sheet.cell(row=2, column=1, value=f"Export du {date.today():%d/%m/%Y}")

    lines = [
        ("Recettes", income),
        ("Dépenses", expense),
        ("Résultat", income - expense),
    ]
    for offset, (label, value) in enumerate(lines, start=4):
        sheet.cell(row=offset, column=1, value=label).font = TOTAL_FONT
        cell = sheet.cell(row=offset, column=2, value=float(value))
        cell.number_format = f'#,##0.00 "{currency}"'
        cell.font = TOTAL_FONT

    sheet.cell(
        row=8,
        column=1,
        value="Le détail est dans les feuilles « Recettes » et « Dépenses ».",
    )
