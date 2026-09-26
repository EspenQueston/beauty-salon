"use client";

/**
 * Les prestations de l'accueil, filtrables par catégorie.
 *
 * ---------------------------------------------------------------------------
 * Ce qui change pour la visiteuse
 * ---------------------------------------------------------------------------
 *
 * Avant, chaque puce de catégorie ouvrait le haut de la page du catalogue :
 * on touchait « Ongles » et l'on tombait sur des tresses. Désormais, toucher
 * une catégorie remplace les quatre cartes par celles de cette catégorie,
 * sur place, et un lien mène à toutes ses prestations — la page du
 * catalogue s'ouvre alors déjà filtrée.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi les cartes arrivent toutes faites
 * ---------------------------------------------------------------------------
 *
 * Elles sont rendues par le serveur — prix, illustrations réparties sans
 * doublon, traductions — et passées ici en propriété. Ce composant ne fait
 * que choisir lesquelles montrer : il n'y a pas de seconde façon de
 * dessiner une carte, donc pas de seconde façon de se tromper de prix.
 */

import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { CategorieRail } from "./CategorieRail";
import type { CategorieFiltre } from "./catalogue";
import { MoreLink } from "./ui";

export type CarteRendue = { id: string; carte: ReactNode };

export function VitrinePrestations({
  categories,
  total,
  vedette,
  parCategorie,
}: {
  categories: CategorieFiltre[];
  total: number;
  /** Les cartes montrées tant qu'aucune catégorie n'est choisie. */
  vedette: CarteRendue[];
  /** Quatre cartes au plus par catégorie, rangées par slug. */
  parCategorie: Record<string, CarteRendue[]>;
}) {
  const t = useTranslations("salon.filtre");
  const [active, setActive] = useState<string | null>(null);

  const choisie = categories.find((categorie) => categorie.slug === active);
  const cartes = choisie ? (parCategorie[choisie.slug] ?? []) : vedette;

  return (
    <>
      {categories.length > 1 && (
        <div className="mb-5">
          <CategorieRail
            categories={categories}
            total={total}
            active={active}
            onChange={setActive}
          />
        </div>
      )}

      {/*
        La grille change de clé à chaque choix : ses cartes remontent en
        cascade, et le mouvement dit que le contenu a changé — sans lui, deux
        catégories aux photos semblables se remplaçaient sans qu'on le voie.
        Rien ne bouge au premier affichage : les cartes en vedette ont déjà
        leur propre apparition.
      */}
      <div
        key={active ?? "vedette"}
        className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-4"
      >
        {cartes.map(({ id, carte }, index) => (
          <div
            key={id}
            className={choisie ? "rise" : undefined}
            style={choisie ? { animationDelay: `${index * 60}ms` } : undefined}
          >
            {carte}
          </div>
        ))}
      </div>

      {choisie && (
        <div className="mt-5 flex justify-center">
          <MoreLink href={`/prestations?categorie=${encodeURIComponent(choisie.slug)}`}>
            {t("voirCategorie", { n: choisie.compte, categorie: choisie.nom })}
          </MoreLink>
        </div>
      )}
    </>
  );
}
