"use client";

/**
 * L'heure qu'il est dans les trois villes du pied de page.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi une horloge et pas trois noms
 * ---------------------------------------------------------------------------
 *
 * « Brazzaville · Kinshasa · Guangzhou » était une ligne morte : trois mots
 * qu'on lit une fois. Les mêmes trois villes avec leur heure disent quelque
 * chose de vrai et de vérifiable — qu'il est neuf heures du soir à Guangzhou
 * quand il est deux heures de l'après-midi à Brazzaville, donc que le produit
 * sert des salons qui ne travaillent pas aux mêmes heures.
 *
 * Rien n'est inventé : ce sont des fuseaux horaires, pas des chiffres d'usage.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi l'heure n'est pas rendue par le serveur
 * ---------------------------------------------------------------------------
 *
 * Le serveur rendrait l'heure de la construction de la page, le navigateur
 * l'heure réelle : React verrait deux textes différents pour le même nœud et
 * signalerait une erreur d'hydratation. Pire, une page mise en cache
 * afficherait pendant des heures une heure fausse.
 *
 * On rend donc des tirets, remplacés au montage. La ligne garde sa largeur
 * (`tabular-nums` + une largeur minimale), donc rien ne saute au moment où
 * les chiffres arrivent.
 */

import { useEffect, useState } from "react";

const VILLES = [
  { nom: "Brazzaville", zone: "Africa/Brazzaville" },
  { nom: "Kinshasa", zone: "Africa/Kinshasa" },
  { nom: "Guangzhou", zone: "Asia/Shanghai" },
] as const;

function lire(zone: string) {
  try {
    return new Intl.DateTimeFormat("fr-FR", {
      timeZone: zone,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date());
  } catch {
    // Un environnement sans base de fuseaux horaires complète lèverait ici.
    // Mieux vaut la ligne sans heure qu'un pied de page qui plante.
    return "--:--";
  }
}

export function Horloges() {
  const [heures, setHeures] = useState<string[]>(() =>
    VILLES.map(() => "--:--"),
  );

  useEffect(() => {
    const rafraichir = () => setHeures(VILLES.map((ville) => lire(ville.zone)));
    rafraichir();

    // Toutes les vingt secondes : l'affichage est à la minute, et une minute
    // d'intervalle ferait attendre jusqu'à soixante secondes le passage de
    // 13:59 à 14:00. Vingt secondes coûtent trois réveils par minute.
    const minuteur = window.setInterval(rafraichir, 20_000);
    return () => window.clearInterval(minuteur);
  }, []);

  return (
    <ul className="grid grid-cols-3 gap-2 sm:gap-3">
      {VILLES.map((ville, index) => (
        <li
          key={ville.nom}
          className="verre rounded-xl px-2.5 py-2 sm:px-3.5 sm:py-2.5"
        >
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="pouls size-1.5 shrink-0 rounded-full bg-[#d9628a]"
            />
            <span className="truncate text-[0.62rem] uppercase tracking-[0.1em] text-[var(--pied-doux)] sm:text-[0.68rem]">
              {ville.nom}
            </span>
          </span>
          <span
            className="tabular mt-1 block text-sm font-semibold text-[var(--pied-encre)] sm:text-base"
            /* L'heure change toute seule : on l'annonce poliment plutôt que
               d'interrompre la lecture d'un lecteur d'écran. */
            aria-live="off"
          >
            {heures[index]}
          </span>
        </li>
      ))}
    </ul>
  );
}
