"use client";

/**
 * Clair / sombre sur le mini-site d'un salon.
 *
 * Le choix appartient à la visiteuse, pas au salon : c'est elle qui lit, et
 * souvent le soir, dans son lit, sur un téléphone. Le salon choisit ses
 * couleurs ; elle choisit la luminosité sur laquelle elles se posent.
 *
 * Le réglage est mémorisé **par salon** : une même personne peut préférer le
 * sombre chez l'un et le clair chez l'autre, selon la palette de chacun.
 *
 * Rien n'est écrit sur `<html>` — c'est le conteneur `.salon-site` qui porte
 * `data-mode`. Le mini-site ne doit pas dicter le thème du produit, et le
 * thème du produit n'a rien à dire sur la vitrine d'un commerce.
 */

import { useCallback, useSyncExternalStore } from "react";

import { SalonIcon } from "./icons";

type Mode = "light" | "dark";

const listeners = new Set<() => void>();

function storageKey(slug: string) {
  return `beauty-salon.mode.${slug}`;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function read(slug: string): Mode {
  try {
    const stored = localStorage.getItem(storageKey(slug));
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    /* stockage refusé : on retombe sur le réglage système */
  }
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  } catch {
    return "light";
  }
}

function apply(slug: string, mode: Mode) {
  const root = document.querySelector<HTMLElement>(".salon-site");
  if (root) root.dataset.mode = mode;
  try {
    localStorage.setItem(storageKey(slug), mode);
  } catch {
    /* le réglage vaut au moins pour cette page */
  }
  for (const listener of listeners) listener();
}

export function SiteModeToggle({
  slug,
  className = "",
}: {
  slug: string;
  className?: string;
}) {
  const mode = useSyncExternalStore(
    subscribe,
    useCallback(() => read(slug), [slug]),
    // Le serveur ne connaît pas la préférence : il rend le mode clair, que
    // le script d'amorçage corrige avant le premier pixel.
    () => "light" as Mode,
  );

  const next: Mode = mode === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={() => apply(slug, next)}
      aria-label={next === "dark" ? "Passer en mode sombre" : "Passer en mode clair"}
      title={next === "dark" ? "Mode sombre" : "Mode clair"}
      className={`inline-flex size-9 items-center justify-center rounded-lg border transition ${className}`}
    >
      {/* L'icône montre le mode *actuel*, pas la destination : c'est la
          convention que les gens connaissent, et l'infobulle dit le reste. */}
      <SalonIcon name={mode === "dark" ? "moon" : "sun"} className="size-[1.1rem]" />
    </button>
  );
}
