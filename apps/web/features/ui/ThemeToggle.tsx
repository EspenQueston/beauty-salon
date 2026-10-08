"use client";

/**
 * Bascule clair / sombre.
 *
 * Trois états, pas deux : **Système**, **Clair**, **Sombre**. Sans le
 * premier, on force un choix à quelqu'un qui a déjà réglé son téléphone en
 * sombre le soir — et on le lui force pour toujours.
 *
 * Le choix est écrit dans `localStorage` et posé sur `<html>` en
 * `data-theme` ; c'est ce que lisent les feuilles de style. Le script inline
 * du layout racine l'applique avant le premier rendu, donc aucune page ne
 * clignote en blanc avant de passer au sombre.
 */

import { useSyncExternalStore } from "react";

export type ThemeChoice = "system" | "light" | "dark";

export const THEME_KEY = "beauty-salon-theme";

const ORDER: ThemeChoice[] = ["system", "light", "dark"];

const LABELS: Record<ThemeChoice, string> = {
  system: "Thème du système",
  light: "Thème clair",
  dark: "Thème sombre",
};

// ---------------------------------------------------------------------------
// Le thème est un état externe à React : il vit dans localStorage et sur
// l'élément <html>. On l'expose donc comme tel plutôt que via useState — un
// useEffect qui lit le stockage provoquerait un second rendu à chaque montage.
// ---------------------------------------------------------------------------

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  // `storage` ne se déclenche que dans les *autres* onglets : deux onglets
  // ouverts restent d'accord sur le thème choisi.
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function snapshot(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark" || stored === "system")
      return stored;
  } catch {
    // Navigation privée, stockage refusé : on retombe sur le système.
  }
  return "system";
}

/** Le serveur ne connaît pas le choix : il rend l'état neutre. */
const serverSnapshot = (): ThemeChoice => "system";

/**
 * Le même choix, exposé aux autres surfaces qui le proposent.
 *
 * Le widget de réglages porte lui aussi une bascule clair/sombre. Elle doit
 * lire et écrire *ce* magasin, sinon les deux commandes se contrediraient :
 * on basculerait dans le panneau et le bouton de la barre du haut
 * continuerait d'afficher l'ancien état.
 */
export function useThemeChoice(): ThemeChoice {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}

export function setTheme(value: ThemeChoice) {
  choose(value);
}

function choose(value: ThemeChoice) {
  const root = document.documentElement;
  if (value === "system") {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = value;
  }
  try {
    localStorage.setItem(THEME_KEY, value);
  } catch {
    // Le thème vaut au moins pour cette page, et c'est déjà mieux que rien.
  }
  for (const listener of listeners) listener();
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const choice = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  const label = LABELS[choice];

  return (
    <button
      type="button"
      onClick={() => choose(ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length])}
      title={label}
      aria-label={`${label} — changer`}
      className={`inline-flex size-9 items-center justify-center rounded-lg border border-line bg-surface text-muted transition hover:bg-surface-hover hover:text-ink ${className}`}
    >
      {choice === "light" ? (
        <SunIcon />
      ) : choice === "dark" ? (
        <MoonIcon />
      ) : (
        <SystemIcon />
      )}
    </button>
  );
}

function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      aria-hidden
      className="size-[1.15rem]"
    >
      <circle cx="12" cy="12" r="4" />
      <path
        d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      aria-hidden
      className="size-[1.15rem]"
    >
      <path
        d="M20 14.5A8.2 8.2 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SystemIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      aria-hidden
      className="size-[1.15rem]"
    >
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <path d="M8 21h8M12 17v4" strokeLinecap="round" />
    </svg>
  );
}
