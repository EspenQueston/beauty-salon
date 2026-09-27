"use client";

/**
 * Une fenêtre au-dessus de la page, qui ne la fait pas bouger.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'elle garantit
 * ---------------------------------------------------------------------------
 *
 *   - **La page reste où elle était.** Rendue dans `document.body` (portail),
 *     en position fixe : ouvrir, enregistrer ou fermer ne fait jamais
 *     défiler la liste en dessous. Le focus revient au bouton qui l'a
 *     ouverte, sans défilement (`preventScroll`).
 *   - **Le clavier y reste.** Le focus y entre à l'ouverture, Tab et
 *     Maj+Tab tournent à l'intérieur, Échap ferme.
 *   - **Rien ne se perd par accident.** Fermer (Échap, croix, clic à côté)
 *     une fenêtre modifiée demande confirmation dans la fenêtre même ; un
 *     enregistrement en cours ne se ferme pas.
 *   - **Téléphone d'abord.** Collée en bas de l'écran sur téléphone — les
 *     boutons tombent sous le pouce —, centrée ensuite. Son contenu défile
 *     à l'intérieur ; l'en-tête et le pied restent en place.
 */

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

const FOCUSABLES =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Modal({
  titre,
  sousTitre,
  onFermer,
  modifie = false,
  occupe = false,
  pied,
  children,
  largeur = "max-w-2xl",
  retour,
}: {
  titre: string;
  sousTitre?: ReactNode;
  /** Appelé quand la fermeture est acquise (confirmée si besoin). */
  onFermer: () => void;
  /** Des changements non enregistrés : fermer demande confirmation. */
  modifie?: boolean;
  /** Un enregistrement est en cours : la fenêtre ne se ferme pas. */
  occupe?: boolean;
  /** Les actions, collées au bas de la fenêtre. */
  pied?: ReactNode;
  children: ReactNode;
  largeur?: string;
  /**
   * Le bouton qui a ouvert la fenetre, s'il est connu. Plus sur que
   * `document.activeElement` : Safari ne donne pas le focus a un bouton
   * clique, et le focus reviendrait alors a la page entiere.
   */
  retour?: HTMLElement | null;
}) {
  const panneau = useRef<HTMLDivElement>(null);
  const corps = useRef<HTMLDivElement>(null);
  const origine = useRef<HTMLElement | null>(null);
  // Le champ en cours d'edition quand la confirmation s'est ouverte : il
  // retrouve le focus si l'on choisit de continuer.
  const enCours = useRef<HTMLElement | null>(null);
  const idTitre = useId();
  const [confirmer, setConfirmer] = useState(false);

  const demanderFermeture = useCallback(() => {
    if (occupe) return;
    if (modifie) {
      const actif = document.activeElement;
      enCours.current =
        actif instanceof HTMLElement && panneau.current?.contains(actif) ? actif : null;
      setConfirmer(true);
    } else onFermer();
  }, [occupe, modifie, onFermer]);

  const continuer = useCallback(() => {
    setConfirmer(false);
    // Apres le rendu : le bouton « Continuer » disparait, le focus ne doit
    // pas tomber sur la page.
    window.setTimeout(() => {
      const cible =
        enCours.current && enCours.current.isConnected ? enCours.current : panneau.current;
      cible?.focus({ preventScroll: true });
    });
  }, []);

  // Le bouton d'origine, retenu avant que le focus n'entre ici ; il le
  // retrouve à la fermeture, sans faire défiler la page.
  useEffect(() => {
    origine.current =
      retour ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    return () => {
      const cible = origine.current;
      if (cible && cible.isConnected && cible !== document.body) {
        cible.focus({ preventScroll: true });
      }
    };
    // Une seule fois : l'origine est celle du moment de l'ouverture.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Le focus entre dans la fenêtre : le champ marqué `data-autofocus`, sinon
  // le premier champ du contenu, sinon la fenêtre elle-même.
  useEffect(() => {
    const cible =
      corps.current?.querySelector<HTMLElement>("[data-autofocus]") ??
      corps.current?.querySelector<HTMLElement>("input, select, textarea") ??
      panneau.current;
    cible?.focus({ preventScroll: true });
  }, []);

  // La confirmation prend le focus : Entrée n'abandonne jamais par erreur,
  // c'est « Continuer » qui est sous le doigt.
  useEffect(() => {
    if (confirmer) {
      panneau.current?.querySelector<HTMLElement>("[data-continuer]")?.focus({ preventScroll: true });
    }
  }, [confirmer]);

  useEffect(() => {
    function auClavier(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        if (confirmer) continuer();
        else demanderFermeture();
        return;
      }
      if (event.key !== "Tab" || !panneau.current) return;
      const elements = Array.from(
        panneau.current.querySelectorAll<HTMLElement>(FOCUSABLES),
      ).filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (elements.length === 0) return;
      const premier = elements[0];
      const dernier = elements[elements.length - 1];
      const actif = document.activeElement;
      if (event.shiftKey && (actif === premier || !panneau.current.contains(actif))) {
        event.preventDefault();
        dernier.focus();
      } else if (!event.shiftKey && (actif === dernier || !panneau.current.contains(actif))) {
        event.preventDefault();
        premier.focus();
      }
    }
    document.addEventListener("keydown", auClavier, true);
    return () => document.removeEventListener("keydown", auClavier, true);
  }, [confirmer, demanderFermeture, continuer]);

  // Jamais rendue au serveur : elle ne s'ouvre qu'apres un geste.
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="modal-fond fixed inset-0 z-50 flex items-end justify-center bg-black/55 backdrop-blur-[2px] sm:items-center sm:p-4"
      // Au pointeur qui *commence* à côté : une sélection de texte partie
      // d'un champ et relâchée dehors ne ferme rien.
      onMouseDown={(event) => {
        if (event.target !== event.currentTarget) return;
        // Sans cela, le navigateur donne ensuite le focus a la page (clic
        // sur une zone non focalisable) : il quittait la fenetre, et
        // « Continuer » ne recevait jamais la touche Entree.
        event.preventDefault();
        demanderFermeture();
      }}
    >
      <div
        ref={panneau}
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitre}
        tabIndex={-1}
        className={`modal-panneau flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-3xl border border-line bg-surface shadow-float outline-none sm:max-h-[88dvh] sm:rounded-2xl ${largeur}`}
      >
        <div className="relative flex items-start gap-3 border-b border-line px-4 pb-3.5 pt-5 sm:px-6 sm:py-4">
          {/* La poignée : sur téléphone, on reconnaît une feuille qui glisse. */}
          <span aria-hidden className="absolute left-1/2 top-1.5 h-1 w-10 -translate-x-1/2 rounded-full bg-line-strong sm:hidden" />
          <div className="min-w-0 flex-1">
            <h2 id={idTitre} className="text-[15px] font-semibold leading-snug text-ink sm:text-lg">
              {titre}
            </h2>
            {sousTitre && (
              <p className="mt-0.5 truncate text-[12.5px] text-muted sm:text-sm">{sousTitre}</p>
            )}
          </div>
          <button
            type="button"
            onClick={demanderFermeture}
            disabled={occupe}
            aria-label="Fermer"
            className="-mr-1.5 flex size-9 shrink-0 items-center justify-center rounded-full text-muted transition hover:bg-surface-hover hover:text-ink disabled:opacity-40"
          >
            <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
              <path d="M6 6 18 18M18 6 6 18" />
            </svg>
          </button>
        </div>

        <div ref={corps} className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6 sm:py-5">
          {children}
        </div>

        {confirmer ? (
          <div
            role="alertdialog"
            aria-label="Modifications non enregistrées"
            className="flex flex-wrap items-center gap-2 border-t border-warning/40 bg-warning-bg px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6"
          >
            <p className="mr-auto min-w-0 text-[13px] font-medium text-warning sm:text-sm">
              Vos modifications ne sont pas enregistrées.
            </p>
            <button
              type="button"
              data-continuer
              onClick={continuer}
              className="rounded-lg border border-line bg-surface px-3.5 py-2 text-sm font-medium text-ink transition hover:bg-surface-hover"
            >
              Continuer
            </button>
            <button
              type="button"
              onClick={onFermer}
              className="rounded-lg bg-danger-bg px-3.5 py-2 text-sm font-medium text-danger transition hover:brightness-95"
            >
              Abandonner
            </button>
          </div>
        ) : (
          pied && (
            <div className="flex flex-wrap items-center gap-2 border-t border-line bg-surface px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6">
              {pied}
            </div>
          )
        )}
      </div>
    </div>,
    document.body,
  );
}
