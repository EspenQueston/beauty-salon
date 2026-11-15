"use client";

/**
 * Chargement d'une ressource du dashboard.
 *
 * Les mises a jour d'etat vivent dans les callbacks de la promesse, jamais
 * dans le corps de l'effet : React 19 signale ce dernier cas comme une
 * source de rendus en cascade. Le rechargement apres une ecriture passe par
 * un compteur plutot que par un appel imperatif.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { DE_FOND, dashboardFetch } from "@/lib/dashboard";

interface Options {
  /** Ne charge rien tant que la condition est fausse (permissions, onglet). */
  enabled?: boolean;
}

export function useResource<T>(
  path: string,
  tenantId: string,
  { enabled = true }: Options = {},
) {
  const t = useTranslations("pro.commun");
  const [data, setData] = useState<T | null>(null);
  const [echec, setEchec] = useState(false);
  // Le texte est calculé au rendu : il suit la langue sans relancer la requête.
  const error = echec ? t("chargementImpossible") : null;
  const [token, setToken] = useState(0);

  const reload = useCallback(() => setToken((value) => value + 1), []);
  // Le rechargement d'une relecture automatique : requête de fond (voir DE_FOND).
  const fond = useRef(false);
  const reloadDeFond = useCallback(() => {
    fond.current = true;
    setToken((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const init = fond.current ? DE_FOND : {};
    fond.current = false;
    dashboardFetch<T>(path, init, tenantId)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setEchec(false);
      })
      .catch(() => {
        if (!cancelled) setEchec(true);
      });

    return () => {
      cancelled = true;
    };
  }, [path, tenantId, token, enabled]);

  return { data, error, reload, reloadDeFond };
}

/** Reponse paginee de l'API, ou liste nue quand la pagination est desactivee. */
export type Page<T> = { count: number; results: T[] } | T[];

export function rows<T>(page: Page<T> | null): T[] {
  if (!page) return [];
  return Array.isArray(page) ? page : page.results;
}
