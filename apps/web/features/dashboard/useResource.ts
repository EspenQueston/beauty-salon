"use client";

/**
 * Chargement d'une ressource du dashboard.
 *
 * Les mises a jour d'etat vivent dans les callbacks de la promesse, jamais
 * dans le corps de l'effet : React 19 signale ce dernier cas comme une
 * source de rendus en cascade. Le rechargement apres une ecriture passe par
 * un compteur plutot que par un appel imperatif.
 */

import { useCallback, useEffect, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";

interface Options {
  /** Ne charge rien tant que la condition est fausse (permissions, onglet). */
  enabled?: boolean;
}

export function useResource<T>(
  path: string,
  tenantId: string,
  { enabled = true }: Options = {},
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState(0);

  const reload = useCallback(() => setToken((value) => value + 1), []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    dashboardFetch<T>(path, {}, tenantId)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch(() => {
        if (!cancelled) setError("Chargement impossible.");
      });

    return () => {
      cancelled = true;
    };
  }, [path, tenantId, token, enabled]);

  return { data, error, reload };
}

/** Reponse paginee de l'API, ou liste nue quand la pagination est desactivee. */
export type Page<T> = { count: number; results: T[] } | T[];

export function rows<T>(page: Page<T> | null): T[] {
  if (!page) return [];
  return Array.isArray(page) ? page : page.results;
}
