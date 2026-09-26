/**
 * Un seul manifeste, trois visages.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi il est dynamique
 * ---------------------------------------------------------------------------
 *
 * Trois sortes d'hôtes servent trois applications différentes, et une cliente
 * qui installe le site de son salon doit voir « blondrose » sur son écran
 * d'accueil — pas « Beauty Salon ». Un manifeste statique en aurait fait une
 * icône générique pour tous les salons de la plateforme.
 *
 *   blondrose.localhost  →  le mini-site du salon, à son nom et à ses couleurs
 *   app.localhost        →  l'espace professionnel
 *   localhost            →  la plateforme
 *
 * Lire l'en-tête `Host` rend cette route dynamique, ce qui est voulu : elle
 * ne peut pas être calculée une fois pour toutes puisqu'elle dépend du salon.
 *
 * ---------------------------------------------------------------------------
 * Les icônes
 * ---------------------------------------------------------------------------
 *
 * Celles de la plateforme sont dans `public/icones/`. Le symbole neuf a une
 * marge transparente pour éviter le rognage des lanceurs Android.
 *
 * Quand le salon a chargé un logo, il passe **en premier** — c'est le sien
 * qu'on veut voir. Les icônes de la plateforme restent derrière : un logo
 * carré de 200 px ne fait pas une bonne icône de 512, et un navigateur qui
 * ne sait pas quoi faire du premier prend le suivant.
 */

import type { MetadataRoute } from "next";
import { headers } from "next/headers";

import { fetchSalon } from "@/lib/api";

const PLATFORM_DOMAIN = process.env.NEXT_PUBLIC_PLATFORM_DOMAIN ?? "localhost";
const RESERVED = new Set(["www", "api", "admin", "static", "media", "mail"]);

/** Les icônes de la plateforme, servies depuis `public/`. */
const ICONES: NonNullable<MetadataRoute.Manifest["icons"]> = [
  { src: "/icones/beauty-salon-symbol.png", sizes: "1254x1254", type: "image/png", purpose: "any" },
];

export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const entetes = await headers();
  const host = (entetes.get("host") ?? "").toLowerCase();
  const hostname = host.split(":")[0];

  const label = sousDomaine(hostname);

  if (label === "app") return espacePro();
  if (label && !RESERVED.has(label)) return miniSite(host);
  return plateforme();
}

function sousDomaine(hostname: string): string | null {
  if (hostname === PLATFORM_DOMAIN || hostname === "127.0.0.1") return null;
  if (!hostname.endsWith(`.${PLATFORM_DOMAIN}`)) return hostname;
  return hostname.slice(0, -(PLATFORM_DOMAIN.length + 1)) || null;
}

/**
 * Le mini-site d'un salon, à son nom et à ses couleurs.
 *
 * `display: "standalone"` et non `"fullscreen"` : une cliente garde l'heure
 * et sa batterie sous les yeux pendant qu'elle choisit un créneau, et le
 * plein écran total fait chercher comment sortir.
 */
async function miniSite(host: string): Promise<MetadataRoute.Manifest> {
  const salon = await fetchSalon(host).catch(() => null);

  if (!salon) return plateforme();

  const primaire = salon.theme_config?.primary || "#b4436c";
  const surface = salon.theme_config?.surface || "#faf7f8";

  return {
    // `id` fige l'identité de l'application installée. Sans lui, changer
    // `start_url` un jour ferait apparaître une seconde icône au lieu de
    // mettre la première à jour.
    id: `/?salon=${salon.slug}`,
    name: salon.city ? `${salon.name} — ${salon.city}` : salon.name,
    // Douze caractères environ : au-delà, un écran d'accueil tronque.
    short_name: salon.name.slice(0, 18),
    description:
      salon.description ||
      `Prenez rendez-vous chez ${salon.name}, en quelques gestes.`,
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: surface,
    theme_color: primaire,
    lang: "fr",
    dir: "ltr",
    categories: ["lifestyle", "shopping"],
    icons: salon.logo
      ? [
          { src: salon.logo.url, sizes: "any", type: "image/png", purpose: "any" },
          ...ICONES,
        ]
      : ICONES,
    /*
      Les raccourcis du menu long-appui.

      Deux, pas six : ce sont les deux gestes qui amènent quelqu'un à
      rouvrir l'application — prendre un rendez-vous, ou vérifier celui
      qu'on a déjà. Une liste plus longue se lit moins vite qu'un écran
      d'accueil.
    */
    shortcuts: [
      {
        name: "Réserver un rendez-vous",
        short_name: "Réserver",
        url: "/reserver",
      },
      {
        name: "Mes rendez-vous",
        short_name: "Mes RDV",
        url: "/compte",
      },
    ],
  };
}

/** L'espace professionnel : l'outil que la gérante ouvre tous les matins. */
function espacePro(): MetadataRoute.Manifest {
  return {
    id: "/dashboard",
    name: "Beauty Salon — Espace professionnel",
    short_name: "Mon salon",
    description:
      "Votre agenda, vos clientes et vos comptes, depuis votre téléphone.",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0e0e12",
    theme_color: "#b4436c",
    lang: "fr",
    dir: "ltr",
    categories: ["business", "productivity"],
    icons: ICONES,
    shortcuts: [
      { name: "Agenda du jour", short_name: "Agenda", url: "/dashboard/agenda" },
      { name: "Mes prestations", short_name: "Prestations", url: "/dashboard/prestations" },
    ],
  };
}

function plateforme(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Beauty Salon",
    short_name: "Beauty Salon",
    description:
      "La plateforme de réservation des professionnels de la beauté.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#fbfbfd",
    theme_color: "#b4436c",
    lang: "fr",
    dir: "ltr",
    icons: ICONES,
  };
}
