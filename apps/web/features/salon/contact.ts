/**
 * Coordonnées d'un salon, dérivées une seule fois.
 *
 * L'en-tête, le pied de page et la page « Infos pratiques » affichent les
 * mêmes liens ; les recalculer à trois endroits, c'est trois occasions de
 * les calculer différemment.
 */

import type { PublicSalon } from "@/lib/types";
import type { SalonIconName } from "./icons";

export interface ContactLink {
  key: string;
  label: string;
  value: string;
  href: string;
  icon: SalonIconName;
  external: boolean;
}

const NETWORKS: { key: string; label: string; icon: SalonIconName }[] = [
  { key: "instagram", label: "Instagram", icon: "instagram" },
  { key: "tiktok", label: "TikTok", icon: "tiktok" },
  { key: "facebook", label: "Facebook", icon: "facebook" },
];

/**
 * Les trois façons de recevoir, en **clés**.
 *
 * L'API rend `salon`, `home` ou `hybrid` ; ce sont ces mots-là qui
 * voyagent. Le libellé, lui, se traduit — il vit sous `salon.modes` dans
 * les catalogues, et le composant qui l'affiche va l'y chercher.
 */
export const SERVICE_MODES = ["salon", "home", "hybrid"] as const;

/**
 * L'adresse e-mail publiée par le salon, ou `null` s'il n'en a pas donné.
 *
 * À part des numéros : un e-mail ne s'« appelle » pas, et les écrans qui
 * n'offrent que des gestes immédiats (appeler, écrire sur WhatsApp) n'en
 * veulent pas.
 */
export function emailLink(salon: PublicSalon): ContactLink | null {
  const adresse = salon.contact_email?.trim();
  if (!adresse) return null;
  return {
    key: "email",
    label: "E-mail",
    value: adresse,
    href: `mailto:${adresse}`,
    icon: "mail",
    external: false,
  };
}

/**
 * Les coordonnées du pied de page : le téléphone, puis l'e-mail.
 *
 * WhatsApp n'y vient qu'en l'absence d'e-mail, et seulement si son numéro
 * n'est pas déjà celui du téléphone — le même numéro affiché deux fois
 * ressemblait à une erreur. WhatsApp reste à portée partout ailleurs (barre
 * de réservation, page Infos).
 */
export function footerContacts(salon: PublicSalon): ContactLink[] {
  const numeros = contactLinks(salon);
  const telephone = numeros.find((lien) => lien.key === "phone");
  const whatsapp = numeros.find((lien) => lien.key === "whatsapp");
  const email = emailLink(salon);
  const chiffres = (valeur: string) => valeur.replace(/[^0-9]/g, "");

  const second =
    email ??
    (whatsapp && (!telephone || chiffres(whatsapp.value) !== chiffres(telephone.value))
      ? whatsapp
      : null);

  return [telephone, second].filter((lien): lien is ContactLink => Boolean(lien));
}

/** Le numéro WhatsApp doit être réduit aux chiffres pour wa.me. */
export function whatsappHref(number: string): string | null {
  const digits = number.replace(/[^0-9]/g, "");
  return digits ? `https://wa.me/${digits}` : null;
}

/**
 * Lien d'itinéraire, le plus précis dont on dispose.
 *
 * Les coordonnées passent avant l'adresse : dans une bonne partie de
 * Brazzaville ou de Kinshasa, aucune adresse postale n'est indexée, et une
 * recherche textuelle y renvoie le centre-ville — c'est-à-dire une cliente
 * qui se perd, avec l'assurance d'avoir le bon lien.
 */
export function mapsHref(salon: PublicSalon): string | null {
  if (salon.latitude && salon.longitude) {
    const point = `${salon.latitude},${salon.longitude}`;
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(point)}`;
  }

  const query = [salon.address, salon.city].filter(Boolean).join(" ");
  if (!query) return null;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

/** Zones desservies, saisies en texte libre séparé par des virgules. */
export function serviceAreas(salon: PublicSalon): string[] {
  return salon.service_area
    .split(",")
    .map((area) => area.trim())
    .filter(Boolean);
}

export function contactLinks(salon: PublicSalon): ContactLink[] {
  const links: ContactLink[] = [];

  if (salon.phone) {
    links.push({
      key: "phone",
      label: "Téléphone",
      value: salon.phone,
      href: `tel:${salon.phone.replace(/\s/g, "")}`,
      icon: "phone",
      external: false,
    });
  }

  const whatsapp = whatsappHref(salon.whatsapp_number);
  if (whatsapp) {
    links.push({
      key: "whatsapp",
      label: "WhatsApp",
      value: salon.whatsapp_number,
      href: whatsapp,
      icon: "whatsapp",
      external: true,
    });
  }

  return links;
}

export function socialLinks(salon: PublicSalon): ContactLink[] {
  return NETWORKS.filter((network) => salon.social_links?.[network.key]).map(
    (network) => ({
      key: network.key,
      label: network.label,
      value: network.label,
      href: salon.social_links[network.key],
      icon: network.icon,
      external: true,
    }),
  );
}

/**
 * Horaires regroupés par jour.
 *
 * L'API renvoie une ligne par plage : un salon qui ferme le midi produit
 * deux lignes « Mardi ». Les afficher telles quelles donne une liste où le
 * même jour apparaît deux fois, ce qui se lit comme une erreur.
 */
export function hoursByDay(
  rows: PublicSalon["business_hours"],
): { weekday: number; ranges: { starts_at: string; ends_at: string }[] }[] {
  const grouped = new Map<number, { starts_at: string; ends_at: string }[]>();

  for (const row of rows) {
    const ranges = grouped.get(row.weekday) ?? [];
    ranges.push({ starts_at: row.starts_at, ends_at: row.ends_at });
    grouped.set(row.weekday, ranges);
  }

  return [0, 1, 2, 3, 4, 5, 6].map((weekday) => ({
    weekday,
    ranges: (grouped.get(weekday) ?? []).sort((a, b) =>
      a.starts_at.localeCompare(b.starts_at),
    ),
  }));
}

/** Lundi = 0, comme les jours stockés côté API. */
export function todayIndex(): number {
  return (new Date().getDay() + 6) % 7;
}
