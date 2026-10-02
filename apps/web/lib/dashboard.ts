"use client";

/**
 * Client API de l'espace professionnel.
 *
 * L'authentification repose sur la session Django, portee par un cookie
 * HttpOnly pose sur le domaine parent (.PLATFORM_DOMAIN). Le navigateur
 * l'envoie donc aussi bien a app. qu'a api., sans qu'aucun jeton ne transite
 * par le JavaScript - c'est precisement l'interet de ce choix face a un
 * JWT stocke en localStorage.
 */

import { browserApi } from "./api";

export interface Membership {
  id: string;
  role: "owner" | "manager" | "receptionist" | "staff";
  status: string;
  tenant: {
    id: string;
    name: string;
    slug: string;
    status: string;
    timezone: string;
    currency: string;
  };
}

export interface SessionUser {
  id: string;
  email: string;
  display_name: string;
  is_platform_admin: boolean;
  /** L'adresse a été prouvée par un clic sur le lien reçu. */
  email_verified?: boolean;
  /** Double authentification active sur ce compte. */
  mfa_enabled?: boolean;
  /** Après une connexion par code de secours : combien il en reste. */
  codes_de_secours_restants?: number;
  memberships: Membership[];
}

export class DashboardError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    /**
     * Le corps de la réponse, tel quel.
     *
     * Un refus transporte parfois plus que sa phrase : l'enregistrement
     * d'une arrivée renvoie le rendez-vous fautif avec son « ce rendez-vous
     * est annulé », et savoir *lequel* est ce qui permet de trancher au
     * comptoir. Les appelants qui n'en ont pas besoin l'ignorent.
     */
    readonly body?: unknown,
  ) {
    super(message);
  }
}

/**
 * Événement de fenêtre : « l'abonnement a peut-être changé, relisez-le ».
 * Émis ici sur un 402, et par la page Abonnement après une déclaration.
 */
export const ABONNEMENT_CHANGE = "beauty-salon:abonnement";

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : null;
}

/** Pose le cookie CSRF avant la premiere ecriture. */
async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie("csrftoken");
  if (existing) return existing;

  await fetch(`${browserApi()}/api/v1/csrf`, { credentials: "include" });
  return readCookie("csrftoken") ?? "";
}

export async function dashboardFetch<T>(
  path: string,
  init: RequestInit = {},
  tenantId?: string,
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    ...((init.headers as Record<string, string>) ?? {}),
  };

  // Un envoi de fichier passe en multipart : c'est le navigateur qui doit
  // poser le Content-Type, parce que lui seul connait la frontiere du corps.
  if (!(init.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] ?? "application/json";
  }

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers["X-CSRFToken"] = await ensureCsrfToken();
  }
  // Necessaire uniquement si le compte gere plusieurs salons ; le backend
  // verifie de toute facon que le membership existe.
  if (tenantId) headers["X-Tenant-Id"] = tenantId;

  const response = await fetch(`${browserApi()}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // 402 : l'abonnement a expiré entre deux chargements. La bannière de la
    // coquille relit l'accès et le dit, quel que soit l'écran qui écrivait.
    if (response.status === 402 && typeof window !== "undefined") {
      window.dispatchEvent(new Event(ABONNEMENT_CHANGE));
    }
    throw new DashboardError(
      response.status,
      body?.code ?? "error",
      // Une erreur de validation DRF arrive en { champ: [messages] } sans
      // cle `detail`. Sans ce repli, l'utilisatrice lisait un « une erreur
      // est survenue » alors que le serveur nommait le champ fautif.
      formatDetail(body?.detail) ?? formatDetail(body) ?? "Une erreur est survenue.",
      body,
    );
  }
  return body as T;
}

/** Mot de passe juste, mais la double authentification attend un code. */
export interface CodeRequis {
  mfa_required: true;
  detail: string;
}

async function postAuth<T>(path: string, body: unknown): Promise<T> {
  const csrf = await ensureCsrfToken();
  const response = await fetch(`${browserApi()}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
    body: JSON.stringify(body),
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new DashboardError(
      response.status,
      data?.code ?? "error",
      data?.detail ?? "Connexion impossible.",
    );
  }
  return data as T;
}

export function login(email: string, password: string): Promise<SessionUser | CodeRequis> {
  return postAuth("/api/v1/auth/login", { email, password });
}

/** Le code de l'application d'authentification (ou un code de secours). */
export function verifierCodeConnexion(code: string): Promise<SessionUser> {
  return postAuth("/api/v1/auth/mfa/verify", { code });
}

export interface EtatMfa {
  enabled: boolean;
  codes_restants: number;
}

export const mfa = {
  etat: () => dashboardFetch<EtatMfa>("/api/v1/auth/mfa"),
  preparer: () =>
    dashboardFetch<{ qr_svg: string; secret: string }>("/api/v1/auth/mfa/setup", {
      method: "POST",
      body: "{}",
    }),
  confirmer: (code: string, password: string) =>
    dashboardFetch<{ enabled: true; codes: string[] }>("/api/v1/auth/mfa/confirm", {
      method: "POST",
      body: JSON.stringify({ code, password }),
    }),
  desactiver: (code: string, password: string) =>
    dashboardFetch<{ enabled: false }>("/api/v1/auth/mfa/disable", {
      method: "POST",
      body: JSON.stringify({ code, password }),
    }),
  nouveauxCodes: (password: string) =>
    dashboardFetch<{ codes: string[] }>("/api/v1/auth/mfa/recovery-codes", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
};

export async function logout(): Promise<void> {
  await dashboardFetch("/api/v1/auth/logout", { method: "POST" });
}

export async function fetchSession(): Promise<SessionUser | null> {
  try {
    return await dashboardFetch<SessionUser>("/api/v1/auth/session");
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Comptes : routes ouvertes, sans salon resolu
// ---------------------------------------------------------------------------

async function accountPost<T>(path: string, body: unknown): Promise<T> {
  const csrf = await ensureCsrfToken();
  const response = await fetch(`${browserApi()}/api/v1/account${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
    body: JSON.stringify(body),
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new DashboardError(
      response.status,
      data?.code ?? "error",
      formatDetail(data?.detail) ?? "Une erreur est survenue.",
    );
  }
  return data as T;
}

/** Les erreurs de validation DRF arrivent en objet { champ: [messages] }. */
function formatDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const messages = Object.entries(detail as Record<string, unknown>)
      // `code` est un identifiant machine ; l'afficher tel quel ne dirait
      // rien a personne.
      .filter(([key]) => key !== "code")
      .flatMap(([, value]) => (Array.isArray(value) ? value : [value]))
      .filter((value) => typeof value === "string" && value.length > 0);
    if (messages.length > 0) return String(messages[0]);
  }
  return null;
}

export interface SignupPayload {
  salon_name: string;
  slug: string;
  email: string;
  password: string;
  display_name?: string;
  phone?: string;
  country: string;
  timezone_name: string;
  currency: string;
  accepts_terms: boolean;
  /** Palette obligatoire choisie pendant l'inscription. */
  theme_config: Record<string, string>;
  /** Code du parrain, facultatif. Un code inconnu fait refuser l'inscription. */
  code_parrainage?: string;
}

/**
 * L'inscription n'ouvre pas de session : elle renvoie de quoi enchaîner sur
 * l'écran de connexion, pas un utilisateur authentifié.
 */
export interface SignupResult {
  email: string;
  tenant: {
    id: string;
    name: string;
    slug: string;
    status: string;
    hostname: string;
  };
}

export function signup(payload: SignupPayload): Promise<SignupResult> {
  return accountPost<SignupResult>("/signup", payload);
}

/** Le clic sur le lien de vérification d'adresse. */
export function verifierAdresse(token: string): Promise<{ detail: string; verified: boolean }> {
  return accountPost("/email/verify", { token });
}

/** Renvoyer le lien de vérification, depuis une session ouverte. */
export function renvoyerVerification(): Promise<{ detail: string; verified: boolean }> {
  return dashboardFetch("/api/v1/auth/email/verify/resend", { method: "POST", body: "{}" });
}

export interface CodeParrainageVerifie {
  valide: boolean;
  code?: string;
  type?: "salon" | "utilisateur";
  /** Nom du salon parrain ; vide pour une cliente, dont le nom reste privé. */
  salon?: string;
}

/** Un code de parrainage existe-t-il ? Rien d'autre n'en sort. */
export async function verifierCodeParrainage(code: string): Promise<CodeParrainageVerifie | null> {
  const response = await fetch(
    `${browserApi()}/api/v1/account/parrainage/${encodeURIComponent(code)}`,
  );
  if (!response.ok) return null;
  return response.json();
}

export async function checkSlug(
  slug: string,
): Promise<{ available: boolean; hostname: string }> {
  const response = await fetch(
    `${browserApi()}/api/v1/account/slug-availability?slug=${encodeURIComponent(slug)}`,
  );
  if (!response.ok) return { available: false, hostname: "" };
  return response.json();
}

export function requestPasswordReset(email: string): Promise<{ detail: string }> {
  return accountPost("/password/reset", { email });
}

export function confirmPasswordReset(payload: {
  uid: string;
  token: string;
  password: string;
}): Promise<{ detail: string }> {
  return accountPost("/password/reset/confirm", payload);
}

export function changePassword(payload: {
  current_password: string;
  new_password: string;
}): Promise<{ detail: string }> {
  return dashboardFetch("/api/v1/auth/password/change", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface InvitationPreview {
  email: string;
  role: string;
  role_display: string;
  salon_name: string;
  account_exists: boolean;
}

export async function fetchInvitation(token: string): Promise<InvitationPreview> {
  const response = await fetch(
    `${browserApi()}/api/v1/account/invitation?token=${encodeURIComponent(token)}`,
  );
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new DashboardError(
      response.status,
      data?.code ?? "error",
      formatDetail(data?.detail) ?? "Invitation introuvable.",
    );
  }
  return data as InvitationPreview;
}

export function acceptInvitation(payload: {
  token: string;
  password?: string;
  display_name?: string;
}): Promise<SessionUser> {
  return accountPost<SessionUser>("/invitation/accept", payload);
}
