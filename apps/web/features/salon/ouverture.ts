/**
 * « C'est ouvert, là, maintenant ? »
 *
 * ---------------------------------------------------------------------------
 * Pourquoi cette question mérite son propre module
 * ---------------------------------------------------------------------------
 *
 * C'est la première question d'une visiteuse qui arrive d'un lien WhatsApp à
 * 21 h. La grille des horaires y répond — à condition de la trouver, de
 * repérer la bonne ligne, et de comparer deux nombres. Trois gestes pour une
 * réponse binaire, et elle est plus bas que le pli sur un téléphone.
 *
 * Une phrase la donne : « Ouvert · ferme à 22:00 ». C'est aussi la seule
 * chose de la page qui change d'une heure à l'autre — c'est elle qui fait la
 * différence entre une vitrine imprimée et un commerce qui vit.
 *
 * ---------------------------------------------------------------------------
 * Le fuseau du salon, jamais celui de la visiteuse
 * ---------------------------------------------------------------------------
 *
 * Un salon de Guangzhou consulté depuis Brazzaville est à sept heures
 * d'écart. Calculer « maintenant » avec l'horloge du navigateur — ou pire,
 * avec celle du serveur de rendu — annoncerait « fermé » en plein après-midi.
 * `Intl.DateTimeFormat` fait la conversion sans dépendre d'une bibliothèque
 * de fuseaux : les données sont déjà dans le moteur.
 *
 * C'est le même piège que le jour comptable des recettes, et il se corrige
 * de la même façon : on ne demande jamais l'heure à la machine qui affiche.
 */

import { shortTime } from "@/lib/format";
import type { PublicSalon } from "@/lib/types";
import { hoursByDay } from "./contact";

/**
 * Ce qu'il y a à dire, et non la phrase qui le dit.
 *
 * Ce module rendait « Ferme à 22:00 » tout formé. C'était pratique tant
 * qu'il n'y avait qu'une langue ; avec deux, la phrase française se
 * retrouvait sous un titre anglais, et rien dans le fichier ne le
 * signalait — le texte n'était pas écrit dans le composant qui l'affiche.
 *
 * Il rend maintenant une clé et ses variables. C'est le composant qui
 * demande la phrase au catalogue, dans la langue de la page.
 */
export type DetailOuverture =
  | { cle: "fermeA"; heure: string }
  | { cle: "ouvreA"; quand: string; heure: string };

export interface EtatOuverture {
  ouvert: boolean;
  /** `null` quand il n'y a rien à dire — un salon sans horaires publiés. */
  detail: DetailOuverture | null;
  /** Jour de la semaine **du salon**, lundi = 0. */
  jour: number;
}

/** Lundi = 0, comme les jours stockés côté API. */
const INDEX_JOUR: Record<string, number> = {
  Mon: 0,
  Tue: 1,
  Wed: 2,
  Thu: 3,
  Fri: 4,
  Sat: 5,
  Sun: 6,
};

/**
 * Jour et minute courants dans le fuseau du salon.
 *
 * `hourCycle: "h23"` et non `hour12: false` : ce dernier rend « 24:00 » à
 * minuit sur certains moteurs, ce qui place l'instant au lendemain une heure
 * durant.
 */
export function maintenantAuSalon(
  timeZone: string,
  now: Date,
): { jour: number; minutes: number } {
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: timeZone || "UTC",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(now);
  } catch {
    // Fuseau inconnu du moteur : mieux vaut une heure UTC qu'une page cassée.
    parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "UTC",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(now);
  }

  const lire = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";

  return {
    jour: INDEX_JOUR[lire("weekday")] ?? 0,
    minutes: Number(lire("hour")) * 60 + Number(lire("minute")),
  };
}

/** « 09:00:00 » → 540. */
function enMinutes(heure: string): number {
  const [h, m] = heure.split(":");
  return Number(h) * 60 + Number(m);
}

/**
 * Une plage couvre-t-elle cette minute ?
 *
 * Une fin antérieure au début décrit une plage qui passe minuit — 20:00 à
 * 02:00. Elle existe : un salon de tresses travaille tard la veille d'une
 * fête. La traiter comme une plage ordinaire la rendrait toujours fermée.
 */
function couvre(debut: number, fin: number, minutes: number): boolean {
  return fin > debut
    ? minutes >= debut && minutes < fin
    : minutes >= debut || minutes < fin;
}

export function etatOuverture(salon: PublicSalon, now: Date): EtatOuverture {
  const semaine = hoursByDay(salon.business_hours);
  const { jour, minutes } = maintenantAuSalon(salon.timezone, now);

  // Aucun horaire publié : on ne dit rien. Annoncer « fermé » à un salon qui
  // n'a pas encore rempli sa grille serait lui inventer une mauvaise nouvelle.
  if (salon.business_hours.length === 0) {
    return { ouvert: false, detail: null, jour };
  }

  for (const plage of semaine[jour].ranges) {
    if (couvre(enMinutes(plage.starts_at), enMinutes(plage.ends_at), minutes)) {
      return { ouvert: true, detail: { cle: "fermeA", heure: shortTime(plage.ends_at) }, jour };
    }
  }

  // La veille peut déborder sur ce matin : 20:00–02:00 un samedi laisse le
  // salon ouvert à 1 h du matin le dimanche.
  const veille = semaine[(jour + 6) % 7];
  for (const plage of veille.ranges) {
    const debut = enMinutes(plage.starts_at);
    const fin = enMinutes(plage.ends_at);
    if (fin <= debut && minutes < fin) {
      return { ouvert: true, detail: { cle: "fermeA", heure: shortTime(plage.ends_at) }, jour };
    }
  }

  // Sinon : la prochaine ouverture, au plus tard dans sept jours.
  for (let delta = 0; delta < 8; delta += 1) {
    const index = (jour + delta) % 7;
    for (const plage of semaine[index].ranges) {
      const debut = enMinutes(plage.starts_at);
      if (delta === 0 && debut <= minutes) continue;
      return {
        ouvert: false,
        detail: {
          cle: "ouvreA",
          quand: quand(delta, index),
          heure: shortTime(plage.starts_at),
        },
        jour,
      };
    }
  }

  return { ouvert: false, detail: null, jour };
}

/**
 * « aujourd'hui », « demain », puis le nom du jour — en clés.
 *
 * Au-delà de demain, le nom du jour est plus court à lire que « dans quatre
 * jours » et se replace tout seul dans une semaine.
 *
 * La clé d'un jour est son indice : c'est ce que le catalogue attend sous
 * `salon.jours`, et c'est ce qui évite d'avoir à traduire un nom de jour
 * déjà traduit ailleurs.
 */
function quand(delta: number, index: number): string {
  if (delta === 0) return "aujourdhui";
  if (delta === 1) return "demain";
  return String(index);
}

/** Les plages du jour, dans le fuseau du salon. Vide = fermé. */
export function horairesDuJour(
  salon: PublicSalon,
  now: Date,
): { starts_at: string; ends_at: string }[] {
  const { jour } = maintenantAuSalon(salon.timezone, now);
  return hoursByDay(salon.business_hours)[jour].ranges;
}
