"use client";

/**
 * La bande défilante des prestations.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'elle remplace, et pourquoi
 * ---------------------------------------------------------------------------
 *
 * Sous le haut de page, il manquait une réponse à « qu'est-ce qu'on fait
 * ici ». Le catalogue y répond, mais deux écrans plus bas — et une visiteuse
 * arrivée d'un lien WhatsApp décide avant d'y arriver.
 *
 * Une bande qui défile sans fin donne cette réponse en un coup d'œil et sans
 * occuper de place : on lit trois noms au passage, et on sait. C'est aussi la
 * seule chose de la page qui bouge en permanence — une page où rien ne bouge
 * se lit comme une image.
 *
 * ---------------------------------------------------------------------------
 * Elle tourne même en « mouvement réduit », et pourquoi il a fallu un bouton
 * ---------------------------------------------------------------------------
 *
 * Un défilement horizontal continu est précisément le genre de mouvement que
 * `prefers-reduced-motion` sert à supprimer. La bande le respectait, et elle
 * restait donc figée pour qui a activé ce réglage — c'est un choix de
 * produit assumé de passer outre : c'est une bande d'enseigne, son mouvement
 * *est* son propos.
 *
 * Mais passer outre crée une obligation. Un contenu en mouvement qui dure
 * plus de cinq secondes doit pouvoir être arrêté (WCAG 2.2.2), et la pause
 * au survol ne suffisait pas : sur un écran tactile, il n'y a pas de survol.
 * D'où le bouton, qui est une vraie commande — visible, atteignable au
 * clavier, et qui dit son état.
 *
 * Le réglage n'est pas ignoré pour autant : il ralentit la bande de moitié.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi le contenu est doublé
 * ---------------------------------------------------------------------------
 *
 * Un défilement sans fin se fabrique en translatant une piste de exactement
 * la moitié de sa largeur, puis en recommençant. Pour que la coupure soit
 * invisible, la seconde moitié doit être la copie exacte de la première :
 * c'est pour cela que la liste est écrite deux fois. La copie est masquée aux
 * lecteurs d'écran, qui sinon énuméreraient tout en double.
 */

import { useState } from "react";

import type { PublicSalon } from "@/lib/types";
import { SalonIcon } from "./icons";

export function Marquee({ salon }: { salon: PublicSalon }) {
  const [arretee, setArretee] = useState(false);

  // Une prestation par catégorie d'abord, puis on complète : un salon dont la
  // première catégorie contient huit coiffures ne doit pas remplir la bande
  // de coiffures et taire ses ongles.
  const parCategorie = salon.categories
    .map((category) => category.services[0]?.name)
    .filter(Boolean) as string[];

  const reste = salon.categories
    .flatMap((category) => category.services.slice(1).map((s) => s.name))
    .filter((name) => !parCategorie.includes(name));

  const noms = [...parCategorie, ...reste].slice(0, 10);

  // Un salon sans aucune prestation n'a rien à faire défiler. C'est le seul
  // cas où la bande disparaît.
  if (noms.length === 0) return null;

  /*
    Les noms sont répétés jusqu'à remplir la piste.

    La bande s'effaçait en dessous de quatre prestations, au motif qu'elle se
    répéterait « trop vite pour ressembler à autre chose qu'un bug ». C'était
    traiter le symptôme : un salon qui débute avec trois prestations perdait
    la seule chose de sa page qui bouge en permanence — et il n'avait aucun
    moyen de comprendre pourquoi, ni que cela reviendrait à la quatrième.

    Le vrai défaut n'était pas la répétition : une enseigne lumineuse répète
    aussi. C'était une piste plus étroite que l'écran, qui laissait un trou
    puis un saut. En répétant la liste jusqu'à une dizaine d'éléments, la
    piste dépasse toujours l'écran, la boucle redevient invisible — et la
    vitesse cesse au passage de dépendre du nombre de prestations, puisque
    l'animation parcourt une largeur comparable dans tous les cas.
  */
  const CIBLE = 10;
  const copies = Math.max(1, Math.ceil(CIBLE / noms.length));
  const piste = Array.from({ length: copies }, () => noms).flat();

  return (
    <div className="marquee relative overflow-hidden border-y border-[var(--site-line)] bg-[var(--site-surface)]">
      {/* Les deux voiles latéraux : la bande se fond dans la page au lieu de
          s'y couper net, ce qui est ce qui distingue un défilé continu d'un
          tableau qui déborde. */}
      <span className="marquee-voile marquee-voile--gauche" />
      <span className="marquee-voile marquee-voile--droite" />

      <div
        className="marquee-piste py-3 sm:py-4"
        data-arretee={arretee ? "" : undefined}
        // La bande est décorative : les mêmes noms sont dans le catalogue,
        // juste en dessous, en tant que vrais liens.
        aria-hidden
      >
        {[0, 1].map((copie) => (
          <ul key={copie} className="marquee-groupe">
            {piste.map((nom, rang) => (
              <li
                key={`${copie}-${rang}-${nom}`}
                className="flex shrink-0 items-center gap-2.5 px-4 sm:gap-3 sm:px-6"
              >
                <SalonIcon
                  name="sparkle"
                  className="size-3.5 shrink-0 text-[var(--salon-ink)] sm:size-4"
                />
                <span className="whitespace-nowrap text-sm font-medium uppercase tracking-[0.06em] text-[var(--site-ink)] sm:text-base">
                  {nom}
                </span>
              </li>
            ))}
          </ul>
        ))}
      </div>

      {/*
        La commande d'arrêt.

        Discrète jusqu'au survol ou au focus — elle ne doit pas concurrencer
        les noms qui passent — mais toujours présente dans le document, donc
        atteignable au clavier et annoncée par un lecteur d'écran. Une
        commande qui n'apparaît qu'au survol n'existe pas sur un téléphone.
      */}
      <button
        type="button"
        onClick={() => setArretee((value) => !value)}
        aria-pressed={arretee}
        className="marquee-bouton absolute right-1.5 top-1/2 z-[2] flex size-7 -translate-y-1/2 items-center justify-center rounded-full border border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-muted)] transition hover:text-[var(--site-ink)] focus-visible:opacity-100"
      >
        <span className="sr-only">
          {arretee ? "Relancer le défilement" : "Arrêter le défilement"}
        </span>
        <svg
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden
          className="size-3"
        >
          {arretee ? (
            <path d="M8 5v14l11-7z" />
          ) : (
            <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" />
          )}
        </svg>
      </button>
    </div>
  );
}
