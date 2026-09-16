"use client";

/**
 * Appels API de l'espace cliente.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ce fichier existe à part
 * ---------------------------------------------------------------------------
 *
 * Ce helper vivait dans `ClientSpace.tsx`. Dès qu'un second composant de
 * l'espace a eu besoin d'écrire — l'annulation d'un rendez-vous — il ne
 * restait que deux issues : importer l'écran entier depuis l'un de ses
 * propres enfants, ce qui referme un cycle d'import, ou recopier la
 * fonction, ce qui garantit qu'une des deux copies oubliera un jour le jeton
 * CSRF.
 *
 * Même raison que `types.ts`, sorti du même fichier pour le même motif.
 *
 * ---------------------------------------------------------------------------
 * Les deux particularités
 * ---------------------------------------------------------------------------
 *
 *   - `X-Tenant-Host` : le navigateur est sur `blondrose.localhost:3100` mais
 *     l'API répond sur un autre port. Sans cet en-tête, le serveur ne sait
 *     pas de quel salon il s'agit et refuse la requête.
 *   - `credentials: "include"` : c'est le seul endroit du site public qui
 *     travaille avec une session. Le reste du mini-site est anonyme.
 */

import { browserApi, csrfToken } from "@/lib/api";

export async function api<T>(
  path: string,
  host: string,
  init?: RequestInit,
): Promise<T> {
  // `browserApi()` déduit l'hôte de l'API de celui de la page. C'est ce qui
  // garde le cookie de session valable : depuis `blondrose.localhost`, viser
  // `localhost` tout court en ferait une requête vers un autre hôte, et la
  // session ne suivrait pas.
  //
  // Django n'exempte de CSRF que les requêtes anonymes : ici tout est
  // authentifié, donc toute écriture porte son jeton.
  const method = (init?.method ?? "GET").toUpperCase();
  const needsCsrf = !["GET", "HEAD", "OPTIONS"].includes(method);

  const response = await fetch(`${browserApi()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Host": host,
      ...(needsCsrf ? { "X-CSRFToken": await csrfToken() } : {}),
      ...(init?.headers ?? {}),
    },
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(readError(body));
  }
  return body as T;
}

/**
 * Message lisible tiré d'une réponse d'erreur.
 *
 * DRF répond de deux façons selon l'erreur : `{detail: "…"}` pour un refus
 * global, `{detail: {email: ["…"]}}` pour une erreur de champ. Ne lire que
 * `detail` marchait dans le premier cas et affichait « [object Object] »
 * dans le second — précisément celui où le serveur avait pris la peine
 * d'expliquer ce qui n'allait pas.
 *
 * La recherche est récursive : les erreurs de champ peuvent elles-mêmes être
 * imbriquées, et un message perdu vaut un message absent.
 */
export function readError(body: unknown): string {
  const found = firstString(body, 0);
  return found
    ? humanDelay(found)
    : "Une erreur est survenue. Réessayez dans un instant.";
}

/**
 * « 3259 secondes » n'est pas une durée, c'est un nombre.
 *
 * La limitation de débit renvoie des secondes brutes. Personne ne convertit
 * mentalement, et le message donne l'impression d'un blocage arbitraire
 * alors qu'il dit « revenez dans une heure ».
 */
function humanDelay(message: string): string {
  return message.replace(/(\d+)\s*secondes?/g, (whole, raw) => {
    const seconds = Number(raw);
    if (seconds < 90) return whole;
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes} minutes`;
    const hours = Math.round(minutes / 60);
    return hours <= 1 ? "une heure" : `${hours} heures`;
  });
}

function firstString(value: unknown, depth: number): string | null {
  if (depth > 4) return null;
  if (typeof value === "string") return value.trim() || null;

  if (Array.isArray(value)) {
    for (const item of value) {
      const found = firstString(item, depth + 1);
      if (found) return found;
    }
    return null;
  }

  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    // `detail` d'abord : c'est le message que le serveur a écrit pour être
    // lu. `code` est un identifiant machine, jamais affichable.
    const ordered = [
      ...("detail" in record ? [record.detail] : []),
      ...Object.entries(record)
        .filter(([key]) => key !== "detail" && key !== "code")
        .map(([, item]) => item),
    ];
    for (const item of ordered) {
      const found = firstString(item, depth + 1);
      if (found) return found;
    }
  }

  return null;
}
