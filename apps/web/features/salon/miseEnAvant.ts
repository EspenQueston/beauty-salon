"use client";

/**
 * La mise en avant des « coups de cœur » : une photo zoome nettement, reste
 * un instant au premier plan, revient à sa place ; puis le bandeau glisse
 * jusqu'à la photo suivante, qui fait de même — et ainsi de suite, en boucle.
 *
 * ---------------------------------------------------------------------------
 * Ce que fait ce module, et ce qu'il ne fait pas
 * ---------------------------------------------------------------------------
 *
 *   - Le zoom : il pose `data-pop="on"` sur le cadre de la photo active ; le
 *     CSS (`.pop-carte` dans globals.css) fait l'agrandissement, l'ombre et
 *     le premier plan. Une transformation : ni les voisines ni la hauteur du
 *     bandeau ne bougent.
 *   - Le défilement : seul le *bandeau* glisse (son `scrollLeft`), jamais la
 *     page. Une photo déjà entièrement visible ne fait pas bouger le bandeau.
 *     Après la dernière, il revient à la première.
 *   - Il ne rend pas React à chaque pas : le rythme vit dans des minuteries et
 *     des attributs, seul le bouton pause est un état.
 *
 * Il s'arrête quand la galerie est survolée, touchée ou reçoit le focus,
 * quand la visionneuse est ouverte, hors écran, onglet masqué, et ne démarre
 * pas du tout sous `prefers-reduced-motion`. Sans JavaScript, rien ne bouge
 * et tout reste cliquable.
 */

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

/** Les réglages, au même endroit. Les durées sont en millisecondes. */
export const MISE_EN_AVANT = {
  /** Avancée vers la visiteuse. */
  zoomMs: 500,
  /** Temps passé au premier plan, zoomée. */
  maintienMs: 1100,
  /** Retour à la place d'origine. */
  retourMs: 500,
  /** Glissement du bandeau jusqu'à la photo suivante. */
  defilementMs: 700,
  /** Courte pause avant le zoom suivant. */
  pauseMs: 250,
  /** Agrandissement, sur grand écran puis sur téléphone. */
  echelle: 1.11,
  echelleMobile: 1.09,
  /** Reprise après que la visiteuse a touché le bandeau du doigt. */
  repriseApresToucherMs: 3000,
} as const;

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

  // Les raisons de s'arrêter, chacune tenue à jour par son événement.
  const etat = useRef({
    aLEcran: false,
    onglet: true,
    survol: false,
    focus: false,
    toucher: false,
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
    let prochain = 0;
    let actif: HTMLElement | null = null;
    let minuterie: number | undefined;
    let finToucher: number | undefined;

    const enMarche = () => {
      const e = etat.current;
      return (
        e.aLEcran && e.onglet && !e.survol && !e.focus && !e.toucher && !e.exterieur && !e.manuel
      );
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

    /** Fait glisser le bandeau jusqu'au cadre ; rend vrai s'il a fallu bouger. */
    const amener = (cadre: HTMLElement): boolean => {
      const article = cadre.parentElement ?? cadre;
      const gauche = parseFloat(getComputedStyle(racine).paddingLeft) || 0;
      const debut = article.offsetLeft - racine.offsetLeft;
      const fin = debut + article.offsetWidth;
      const vueDebut = racine.scrollLeft + gauche;
      const vueFin = racine.scrollLeft + racine.clientWidth - gauche;
      if (debut >= vueDebut - 1 && fin <= vueFin + 1) return false;
      racine.scrollTo({ left: Math.max(0, debut - gauche), behavior: "smooth" });
      return true;
    };

    const zoomer = (cadre: HTMLElement) => {
      if (!enMarche()) return;
      actif = cadre;
      cadre.setAttribute("data-pop", "on");
      attendre(MISE_EN_AVANT.zoomMs + MISE_EN_AVANT.maintienMs, () => {
        rendre();
        attendre(MISE_EN_AVANT.retourMs, pas);
      });
    };

    const pas = () => {
      if (!enMarche()) return;
      const tous = cadres();
      if (tous.length === 0) return;
      // La prochaine photo chargée, dans l'ordre d'affichage.
      let choisi: HTMLElement | null = null;
      for (let n = 0; n < tous.length; n += 1) {
        const rang = (prochain + n) % tous.length;
        if (!tous[rang].hasAttribute("data-pop-ko")) {
          choisi = tous[rang];
          prochain = rang + 1;
          break;
        }
      }
      if (!choisi) return;
      const cible = choisi;
      const glisse = amener(cible);
      attendre(
        (glisse ? MISE_EN_AVANT.defilementMs : 0) + MISE_EN_AVANT.pauseMs,
        () => zoomer(cible),
      );
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
    // Le doigt sur le bandeau : la visiteuse fait défiler elle-même, on se
    // tait, et on reprend quelques secondes après qu'elle a lâché.
    const surToucher = (evenement: PointerEvent) => {
      if (evenement.pointerType === "mouse") return;
      window.clearTimeout(finToucher);
      etat.current.toucher = true;
      relancer.current();
    };
    const surLacher = (evenement: PointerEvent) => {
      if (evenement.pointerType === "mouse") return;
      window.clearTimeout(finToucher);
      finToucher = window.setTimeout(() => {
        etat.current.toucher = false;
        relancer.current();
      }, MISE_EN_AVANT.repriseApresToucherMs);
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
    racine.addEventListener("pointerdown", surToucher);
    racine.addEventListener("pointerup", surLacher);
    racine.addEventListener("pointercancel", surLacher);
    racine.addEventListener("focusin", surFocus);
    racine.addEventListener("focusout", surPerteFocus);
    racine.addEventListener("error", surErreur, true);

    return () => {
      window.clearTimeout(minuterie);
      window.clearTimeout(finToucher);
      rendre();
      relancer.current = () => {};
      aLEcran.disconnect();
      document.removeEventListener("visibilitychange", surOnglet);
      racine.removeEventListener("pointerenter", surEntree);
      racine.removeEventListener("pointerleave", surSortie);
      racine.removeEventListener("pointerdown", surToucher);
      racine.removeEventListener("pointerup", surLacher);
      racine.removeEventListener("pointercancel", surLacher);
      racine.removeEventListener("focusin", surFocus);
      racine.removeEventListener("focusout", surPerteFocus);
      racine.removeEventListener("error", surErreur, true);
    };
  }, [liste, nombre]);

  const basculer = useCallback(() => setArretee((valeur) => !valeur), []);
  return { arretee, basculer };
}
