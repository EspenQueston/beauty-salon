"""Le découpage des détails en rangées de deux.

Partagé par les notifications de rendez-vous et par les e-mails de compte :
les deux remplissent la même grille, et deux découpages divergeraient au
premier fait ajouté d'un seul côté.

Le calcul se fait ici plutôt que dans le gabarit parce qu'un gabarit qui
ouvrirait un `<tr>` au milieu d'une boucle, selon la parité et selon la
largeur du fait, produirait un tableau presque valide — que chaque client de
messagerie répare à sa façon. Ici, il se vérifie par un test.
"""

from __future__ import annotations


def grouper(faits: list[dict]) -> list[list[dict]]:
    """Deux faits par rangée, sauf ceux qui prennent la largeur entière.

    Un fait `wide` ferme la rangée en cours avant de prendre la sienne : sans
    cela il s'insérerait à côté d'un autre et le pousserait hors de la grille,
    ce qui se voit surtout dans Outlook, qui ne redresse rien.
    """
    rangees: list[list[dict]] = []
    courante: list[dict] = []

    for fait in faits:
        if fait.get("wide"):
            if courante:
                rangees.append(courante)
                courante = []
            rangees.append([fait])
            continue
        courante.append(fait)
        if len(courante) == 2:
            rangees.append(courante)
            courante = []

    if courante:
        rangees.append(courante)
    return rangees
