/**
 * L'abonnement, vu du tableau de bord : les formes de l'API et un signal.
 *
 * Le signal existe parce que deux endroits parlent de l'abonnement — la
 * bannière de la coquille et la page Abonnement — et qu'ils ne doivent
 * jamais se contredire. Quand l'un apprend quelque chose (un paiement
 * déclaré, une validation, un 402 renvoyé par une écriture), il le dit ;
 * l'autre relit le serveur plutôt que de deviner.
 */

import { ABONNEMENT_CHANGE } from "@/lib/dashboard";

export { ABONNEMENT_CHANGE };

export function signalerAbonnement(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(ABONNEMENT_CHANGE));
  }
}

export type RaisonAcces =
  | "sans_abonnement"
  | "essai"
  | "periode"
  | "grace"
  | "expire"
  | "suspendu"
  | "resilie";

export interface Acces {
  ouvert: boolean;
  raison: RaisonAcces;
  en_grace: boolean;
  fin_periode: string | null;
  jusqu_au: string | null;
}

/** Ce que gagnerait un salon au mensuel à passer à l'annuel, dans son groupe. */
export interface MonteeEnGamme {
  vers: "yearly" | "pro_yearly";
  devise: string;
  montant_annuel: string;
  economie: { montant: string; pourcentage: number };
}

export interface AccesSalon extends Acces {
  statut: string;
  statut_libelle: string;
  offre: string;
  offre_code: string;
  paiement_en_attente: boolean;
  peut_payer: boolean;
  montee_en_gamme: MonteeEnGamme | null;
  /** Le groupe qui ouvre les droits aujourd'hui ; null quand l'accès est fermé. */
  groupe: Groupe | null;
  fonctions: Fonctions;
  /** Pro se vend dans la devise du salon, et le salon n'y est pas encore. */
  pro_disponible: boolean;
}

// ---------------------------------------------------------------------------
// Standard et Pro
// ---------------------------------------------------------------------------

export type Groupe = "standard" | "pro";

export type FonctionPro =
  | "custom_domain"
  | "customization"
  | "whatsapp_assistant"
  | "platform_assistant"
  | "customer_assistant";

/** Les fonctions Pro ouvertes au salon, calculées par le serveur. */
export type Fonctions = Record<FonctionPro, boolean>;

/** Ce que chaque fonction Pro apporte, dit simplement. */
export const FONCTIONS_PRO: Record<FonctionPro, { nom: string; resume: string }> = {
  custom_domain: {
    nom: "Domaine personnalisé",
    resume: "Votre mini-site sur votre propre nom de domaine.",
  },
  customization: {
    nom: "Apparence avancée",
    resume: "Polices, menu, ordre des sections, accroche et bouton.",
  },
  whatsapp_assistant: {
    nom: "Assistant IA WhatsApp",
    resume: "Réponses automatiques à vos clientes sur votre numéro WhatsApp.",
  },
  platform_assistant: {
    nom: "Assistant IA de l'espace pro",
    resume: "Répond à vos questions sur votre agenda et votre salon.",
  },
  customer_assistant: {
    nom: "Assistant IA 24 h/24",
    resume: "Réponses automatiques à vos clientes sur le mini-site, jour et nuit.",
  },
};

export const GROUPES: Record<Groupe, string> = { standard: "Standard", pro: "Pro" };

/** Jours pleins restants avant `iso`, arrondis au jour entamé. */
export function joursAvant(iso: string | null, maintenant: number): number {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - maintenant) / 86_400_000));
}

export const dateLongue = new Intl.DateTimeFormat("fr-FR", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

/** Un montant, sans décimales inutiles : « 99 CNY », pas « 99,00 CNY ». */
export function montant(valeur: string | number, devise: string): string {
  const nombre = Number(valeur);
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: devise,
    minimumFractionDigits: Number.isInteger(nombre) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(nombre);
}
