/**
 * Acces a l'API Django.
 *
 * Le salon vise n'est jamais dans l'URL : il est porte par l'en-tete
 * `X-Tenant-Host`, que le backend recoupe avec sa table de domaines. Ce
 * choix rend le frontend independant de la topologie reseau - un seul
 * point d'entree API, que l'on soit en local sur localhost ou derriere un
 * domaine personnalise en production.
 */

import { LANGUE_PAR_DEFAUT, type Langue } from "@/i18n/langues";
import type {
  BookingConfirmation,
  PublicReview,
  PublicSalon,
  Slot,
} from "./types";

// Cote serveur on parle a l'API en direct (pas de traversee du proxy) ;
// cote navigateur on passe par l'URL publique.
const SERVER_API = process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8001";

/**
 * En-tetes des appels faits par le serveur Next, et non par un navigateur.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi le serveur se presente
 * ---------------------------------------------------------------------------
 *
 * L'API limite le debit par adresse IP. Tout ce que le serveur Next demande
 * pour rendre une page part de la meme adresse — la sienne — quel que soit
 * le visiteur a l'origine du rendu. Sans distinction, tous les mini-sites se
 * partagent donc un seul compteur de lecture publique : au-dela de 120 rendus
 * par minute, plateforme entiere, les pages de salon tombaient en 429.
 *
 * Le jeton dit a l'API « c'est le serveur de rendu », qui n'est alors pas
 * compte. Le transmettre ne change pas la cle de cache de Next : il est le
 * meme pour toutes les requetes.
 *
 * Jamais `NEXT_PUBLIC_` : ce nom-la serait recopie dans le JavaScript envoye
 * au navigateur, et n'importe qui pourrait alors contourner la limite. Sous
 * ce nom, la valeur n'existe que dans le processus serveur ; dans le code qui
 * part vers le navigateur, elle vaut `undefined`.
 */
function serverHeaders(host: string): HeadersInit {
  const token = process.env.INTERNAL_API_TOKEN;
  return token
    ? { "X-Tenant-Host": host, "X-Internal-Token": token }
    : { "X-Tenant-Host": host };
}


const API_PORT = process.env.NEXT_PUBLIC_API_PORT ?? "8001";

/**
 * Base de l'API vue depuis le navigateur.
 *
 * En production, `NEXT_PUBLIC_API_URL` fait autorite. A defaut, l'API est
 * appelee sur *le meme hostname que la page*, seul le port change.
 *
 * Ce choix a deux vertus en developpement : le cookie de session peut rester
 * limite a l'hote (les cookies ignorent le port), ce qui evite les
 * comportements erratiques de `Domain=.localhost` ; et le salon se deduit
 * directement de l'en-tete Host recu par Django, sans dependre d'un
 * sous-domaine `api.` supplementaire.
 */
export function browserApi(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured) return configured;

  if (typeof window === "undefined") return SERVER_API;

  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:${API_PORT}`;
}

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly extra?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

/**
 * Contenu complet d'un mini-site, en une requete.
 *
 * La langue est un **parametre**, et non une valeur devinee ici.
 *
 * Ce module est importe par des composants client — le parcours de
 * reservation, l espace cliente. Y lire `next/root-params`, qui n existe que
 * sur le serveur, casse leur compilation entiere. C est `lib/salon-serveur.ts`
 * qui connait la langue du rendu et la passe ici.
 *
 * Elle entre dans la cle de cache de Next : deux langues, deux entrees.
 */
export async function fetchSalon(
  host: string,
  langue: Langue = LANGUE_PAR_DEFAUT,
): Promise<PublicSalon | null> {
  const response = await fetch(
    `${SERVER_API}/api/v1/public/salon?lang=${langue}`,
    {
    headers: serverHeaders(host),
    // Le contenu vitrine bouge rarement, et un cache court absorbe un pic de
    // trafic apres un post Instagram. Mais 60 s, c'est trop long pour la
    // gerante qui vient de changer ses couleurs et recharge sa page : elle
    // conclut que le reglage ne marche pas. Quinze secondes protegent
    // toujours du pic, sans donner cette impression.
    next: { revalidate: 15 },
    },
  );

  if (response.status === 404) return null;
  if (!response.ok) {
    throw new ApiRequestError(response.status, "fetch_failed", "Salon indisponible.");
  }
  return response.json();
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : null;
}

/**
 * Jeton CSRF, posé à la demande.
 *
 * Une visiteuse anonyme n'en a pas besoin et n'en reçoit pas : le cookie
 * n'est demandé qu'au moment de la première écriture, pas au chargement de
 * chaque page du mini-site.
 */
export async function csrfToken(): Promise<string> {
  const existing = readCookie("csrftoken");
  if (existing) return existing;

  await fetch(`${browserApi()}/api/v1/csrf`, { credentials: "include" });
  return readCookie("csrftoken") ?? "";
}

export async function browserRequest<T>(
  path: string,
  host: string,
  init: RequestInit = {},
): Promise<T> {
  /*
   * La session voyage avec la requête — et le jeton CSRF avec elle.
   *
   * Le mini-site est anonyme dans son immense majorité, et ces routes le
   * restent : elles répondent aussi bien sans compte. Mais quand une cliente
   * *est* connectée à son espace, le serveur doit le savoir, sinon sa
   * réservation est enregistrée sans jamais rejoindre son historique — et
   * elle croit que ça a échoué.
   *
   * Envoyer le cookie a une conséquence qu'on ne peut pas oublier : Django
   * n'exempte de CSRF que les requêtes *anonymes*. Dès qu'une session est
   * présente, une écriture sans jeton est rejetée. C'est le comportement
   * voulu, et c'est pourquoi le jeton part avec les écritures.
   */
  const method = (init.method ?? "GET").toUpperCase();
  const needsCsrf = !["GET", "HEAD", "OPTIONS", "TRACE"].includes(method);

  const response = await fetch(`${browserApi()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Host": host,
      ...(needsCsrf ? { "X-CSRFToken": await csrfToken() } : {}),
      ...(init.headers ?? {}),
    },
  });

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiRequestError(
      response.status,
      body?.code ?? "error",
      typeof body?.detail === "string" ? body.detail : "Une erreur est survenue.",
      body?.extra,
    );
  }
  return body as T;
}

export async function fetchAvailability(params: {
  host: string;
  serviceId: string;
  staffMemberId?: string;
  from: string;
  to: string;
  /** Options retenues : elles allongent la prestation, donc changent les créneaux. */
  optionIds?: string[];
}): Promise<Slot[]> {
  const query = new URLSearchParams({
    service: params.serviceId,
    date_from: params.from,
    date_to: params.to,
  });
  if (params.staffMemberId) query.set("staff_member", params.staffMemberId);
  // Répété plutôt que joint par des virgules : c'est ce que DRF lit comme
  // une liste, et le serveur recalcule la durée à partir de ces identifiants.
  for (const id of params.optionIds ?? []) query.append("options", id);

  const data = await browserRequest<{ slots: Slot[] }>(
    `/api/v1/public/availability?${query}`,
    params.host,
  );
  return data.slots;
}

export async function createBooking(params: {
  host: string;
  idempotencyKey: string;
  payload: Record<string, unknown>;
}): Promise<BookingConfirmation> {
  return browserRequest<BookingConfirmation>("/api/v1/public/bookings", params.host, {
    method: "POST",
    // Protege du double clic et des reseaux qui rejouent une requete :
    // deux envois identiques donnent une seule reservation.
    headers: { "Idempotency-Key": params.idempotencyKey },
    body: JSON.stringify(params.payload),
  });
}

// ---------------------------------------------------------------------------
// Avis clientes
// ---------------------------------------------------------------------------

export interface ReviewInvitation {
  salon_name: string;
  service_name: string;
  staff_member_name: string;
  starts_at: string;
  customer_name: string;
}

/** Contexte du rendez-vous a noter, verifie par la signature du jeton. */
export async function fetchReviewInvitation(
  host: string,
  token: string,
): Promise<ReviewInvitation> {
  return browserRequest<ReviewInvitation>(
    `/api/v1/public/reviews/invitation?token=${encodeURIComponent(token)}`,
    host,
  );
}

/**
 * Les cinq critères notés, dans l'ordre où la page les demande.
 *
 * Le nom des champs est celui du serveur : une table de correspondance
 * entre deux vocabulaires finit toujours par diverger d'un côté.
 */
export const REVIEW_CRITERIA = [
  { field: "rating_result", label: "Le résultat", hint: "La coiffure, le soin — ce pour quoi vous êtes venue." },
  { field: "rating_welcome", label: "L'accueil", hint: "L'écoute, les conseils, l'ambiance." },
  { field: "rating_punctuality", label: "La ponctualité", hint: "L'heure tenue, le temps d'attente." },
  { field: "rating_cleanliness", label: "La propreté du salon", hint: "Le matériel, les bacs, les lieux." },
  { field: "rating_value", label: "Le rapport qualité-prix", hint: "Ce que vous avez payé pour ce que vous avez eu." },
] as const;

export type ReviewCriterion = (typeof REVIEW_CRITERIA)[number]["field"];

export async function submitReview(params: {
  host: string;
  token: string;
  /** Une note par critère, ou `null` pour ceux laissés vides. */
  ratings: Record<ReviewCriterion, number | null>;
  comment: string;
}): Promise<{ id: string; rating: number }> {
  return browserRequest("/api/v1/public/reviews/create", params.host, {
    method: "POST",
    // La note d'ensemble n'est pas envoyée : le serveur la calcule à partir
    // des critères. L'envoyer d'ici permettrait à un avis de porter « 5 sur
    // 5 » au-dessus de cinq critères à 1.
    body: JSON.stringify({
      token: params.token,
      ...params.ratings,
      comment: params.comment,
    }),
  });
}

/**
 * Avis publies d'un salon, charges cote serveur avec la page.
 *
 * Meme duree de cache que la vitrine : un avis qui apparait quinze secondes
 * apres sa publication est acceptable, un aller-retour reseau de plus a
 * chaque visite ne l'est pas.
 */
export async function fetchReviews(
  host: string,
): Promise<{ average: number | null; count: number; results: PublicReview[] }> {
  const response = await fetch(`${SERVER_API}/api/v1/public/reviews`, {
    headers: serverHeaders(host),
    next: { revalidate: 15 },
  });

  // Un salon sans avis ne doit pas faire echouer le rendu de sa page.
  if (!response.ok) return { average: null, count: 0, results: [] };
  return response.json();
}

/**
 * Inscription en liste d'attente.
 *
 * Pas de cle d'idempotence ici, contrairement a la reservation : une double
 * inscription est benigne — le salon voit deux lignes identiques et en
 * classe une — la ou un double rendez-vous bloque deux creneaux.
 */
export async function joinWaitlist(params: {
  host: string;
  payload: Record<string, unknown>;
}): Promise<{ id: string; detail: string }> {
  return browserRequest("/api/v1/public/waitlist", params.host, {
    method: "POST",
    body: JSON.stringify(params.payload),
  });
}

/**
 * Envoi d'un formulaire multipart vers une route publique.
 *
 * `browserRequest` impose `Content-Type: application/json`, ce qui convient
 * à tout le reste mais casse un envoi de fichier : le navigateur doit poser
 * lui-même l'en-tête, avec la frontière multipart qu'il seul connaît.
 *
 * Le reste est identique — même en-tête de salon, même session, même jeton
 * CSRF — et c'est justement pour ne pas dupliquer *cela* que cette fonction
 * vit ici plutôt que dans le composant qui l'utilise.
 */
export async function postForm<T>(
  path: string,
  host: string,
  form: FormData,
): Promise<T> {
  const response = await fetch(`${browserApi()}${path}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "X-Tenant-Host": host,
      "X-CSRFToken": await csrfToken(),
    },
    body: form,
  });

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiRequestError(
      response.status,
      body?.code ?? "error",
      typeof body?.detail === "string" ? body.detail : "Envoi impossible.",
      body?.extra,
    );
  }
  return body as T;
}
