"use client";

/**
 * La mise en avant des « coups de cœur » : une photo après l'autre avance
 * vers la visiteuse, reste un instant, puis reprend sa place — et la suivante
 * part seulement quand la précédente est revenue.
 *
 * ---------------------------------------------------------------------------
 * Ce que fait ce module, et ce qu'il ne fait pas
 * ---------------------------------------------------------------------------
 *
 *   - Il ne déplace rien : il pose `data-pop="on"` sur le cadre de la photo
 *     active ; le CSS (`.pop-carte` dans globals.css) fait le zoom, l'ombre et
 *     le premier plan. Le bandeau garde sa disposition, sa hauteur et son
 *     défilement au doigt : ce n'est pas un carrousel.
 *   - Il ne fait défiler personne : seules les photos *visibles* dans le
 *     bandeau passent à leur tour. Sur téléphone, celles qu'on n'a pas fait
 *     glisser attendent.
 *   - Il ne rend pas React à chaque pas : le rythme vit dans des minuteries et
 *     des attributs, seul le bouton pause est un état.
 *
 * Il s'arrête quand la galerie est survolée ou reçoit le focus, quand la
 * visionneuse est ouverte, hors écran, onglet masqué, et ne démarre pas du
 * tout sous `prefers-reduced-motion`. Sans JavaScript, rien ne bouge et
 * tout reste cliquable.
 */

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

/** Les réglages, au même endroit. Les durées sont en millisecondes. */
export const MISE_EN_AVANT = {
  /** Avancée vers la visiteuse. */
  zoomMs: 650,
  /** Temps passé au premier plan. */
  maintienMs: 1400,
  /** Retour à la place d'origine. */
  retourMs: 650,
  /** Pause entre le retour d'une photo et le départ de la suivante. */
  pauseMs: 450,
  /** Agrandissement, sur grand écran puis sur téléphone. */
  echelle: 1.06,
  echelleMobile: 1.035,
} as const;

/** Une photo qui passe sous ce seuil de visibilité dans le bandeau ne s'anime pas. */
const VISIBLE = 0.85;

/**
 * Les variables CSS du rythme, à poser sur le conteneur : le CSS lit les
 * mêmes durées que les minuteries, il n'y a qu'un endroit à changer.
 */
export function variablesMiseEnAvant(): Record<string, string> {
  return {
    "--pop-zoom": `${MISE_EN_AVANT.zoomMs}ms`,
    "--pop-retour": `${MISE_EN_AVANT.retourMs}ms`,
    "--pop-echelle": String(MISE_EN_AVANT.echelle),
    "--pop-echelle-mobile": String(MISE_EN_AVANT.echelleMobile),
  };
}

export function useMiseEnAvant(
  liste: RefObject<HTMLElement | null>,
  { enPause, nombre }: { enPause: boolean; nombre: number },
): { arretee: boolean; basculer: () => void } {
  const [arretee, setArretee] = useState(false);

  // Les raisons de s'arrêter, chacune tenue a jour par son evenement.
  const etat = useRef({
    aLEcran: false,
    onglet: true,
    survol: false,
    focus: false,
    exterieur: enPause,
    manuel: false,
  });
  const relancer = useRef<() => void>(() => {});

  useEffect(() => {
    etat.current.exterieur = enPause;
    relancer.current();
  }, [enPause]);

  useEffect(() => {
    etat.current.manuel = arretee;
    relancer.current();
  }, [arretee]);

  useEffect(() => {
    const racine = liste.current;
    if (!racine || nombre < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const cadres = () => [...racine.querySelectorAll<HTMLElement>("[data-pop-cadre]")];
    const visibles = new Set<Element>();
    let prochain = 0;
    let actif: HTMLElement | null = null;
    let minuterie: number | undefined;

    const enMarche = () => {
      const e = etat.current;
      return e.aLEcran && e.onglet && !e.survol && !e.focus && !e.exterieur && !e.manuel;
    };

    const attendre = (ms: number, suite: () => void) => {
      window.clearTimeout(minuterie);
      minuterie = window.setTimeout(suite, ms);
    };

    const rendre = () => {
      // Retour à la place d'origine : le CSS joue la transition de retour.
      actif?.removeAttribute("data-pop");
      actif = null;
    };

    const pas = () => {
      if (!enMarche()) return;
      const tous = cadres();
      if (tous.length === 0) return;
      // La prochaine photo visible et chargée, dans l'ordre d'affichage.
      let choisi: HTMLElement | null = null;
      for (let n = 0; n < tous.length; n += 1) {
        const rang = (prochain + n) % tous.length;
        const cadre = tous[rang];
        if (visibles.has(cadre) && !cadre.hasAttribute("data-pop-ko")) {
          choisi = cadre;
          prochain = rang + 1;
          break;
        }
      }
      if (!choisi) {
        attendre(MISE_EN_AVANT.pauseMs * 2, pas);
        return;
      }
      actif = choisi;
      choisi.setAttribute("data-pop", "on");
      attendre(MISE_EN_AVANT.zoomMs + MISE_EN_AVANT.maintienMs, () => {
        rendre();
        attendre(MISE_EN_AVANT.retourMs + MISE_EN_AVANT.pauseMs, pas);
      });
    };

    // Appelée à chaque changement d'une raison de s'arrêter.
    relancer.current = () => {
      window.clearTimeout(minuterie);
      if (!enMarche()) {
        rendre();
        return;
      }
      // Reprise : la photo éventuellement en cours finit son retour d'abord.
      const enCours = actif !== null;
      rendre();
      attendre((enCours ? MISE_EN_AVANT.retourMs : 0) + MISE_EN_AVANT.pauseMs, pas);
    };

    // Visibilité de chaque photo dans le bandeau qui défile.
    const dansLeBandeau = new IntersectionObserver(
      (entrees) => {
        for (const entree of entrees) {
          if (entree.intersectionRatio >= VISIBLE) visibles.add(entree.target);
          else visibles.delete(entree.target);
        }
      },
      { root: racine, threshold: [0, VISIBLE, 1] },
    );
    for (const cadre of cadres()) dansLeBandeau.observe(cadre);

    // La galerie à l'écran, ou non.
    const aLEcran = new IntersectionObserver(
      ([entree]) => {
        etat.current.aLEcran = entree.isIntersecting;
        relancer.current();
      },
      { threshold: 0.25 },
    );
    aLEcran.observe(racine);

    const surOnglet = () => {
      etat.current.onglet = document.visibilityState === "visible";
      relancer.current();
    };
    const surEntree = (evenement: PointerEvent) => {
      if (evenement.pointerType !== "mouse") return;
      etat.current.survol = true;
      relancer.current();
    };
    const surSortie = (evenement: PointerEvent) => {
      if (evenement.pointerType !== "mouse") return;
      etat.current.survol = false;
      relancer.current();
    };
    const surFocus = () => {
      etat.current.focus = true;
      relancer.current();
    };
    const surPerteFocus = (evenement: FocusEvent) => {
      if (racine.contains(evenement.relatedTarget as Node | null)) return;
      etat.current.focus = false;
      relancer.current();
    };
    // Une image qui ne charge pas sort de la séquence ; la galerie, elle, reste.
    const surErreur = (evenement: Event) => {
      const cadre = (evenement.target as HTMLElement | null)?.closest?.("[data-pop-cadre]");
      cadre?.setAttribute("data-pop-ko", "");
    };

    document.addEventListener("visibilitychange", surOnglet);
    racine.addEventListener("pointerenter", surEntree);
    racine.addEventListener("pointerleave", surSortie);
    racine.addEventListener("focusin", surFocus);
    racine.addEventListener("focusout", surPerteFocus);
    racine.addEventListener("error", surErreur, true);

    return () => {
      window.clearTimeout(minuterie);
      rendre();
      relancer.current = () => {};
      dansLeBandeau.disconnect();
      aLEcran.disconnect();
      document.removeEventListener("visibilitychange", surOnglet);
      racine.removeEventListener("pointerenter", surEntree);
      racine.removeEventListener("pointerleave", surSortie);
      racine.removeEventListener("focusin", surFocus);
      racine.removeEventListener("focusout", surPerteFocus);
      racine.removeEventListener("error", surErreur, true);
    };
  }, [liste, nombre]);

  const basculer = useCallback(() => setArretee((valeur) => !valeur), []);
  return { arretee, basculer };
}
