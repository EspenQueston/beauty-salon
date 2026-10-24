"use client";

/**
 * Un lien interne qui reste dans la langue où l'on lit.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi `next/link` ne suffit pas
 * ---------------------------------------------------------------------------
 *
 * Le préfixe de langue ne vit que dans la barre d'adresse : `proxy.ts` le
 * retire avant de réécrire, et les pages ne le voient jamais. Un
 * `<Link href="/prestations">` écrit dans un composant envoie donc à
 * `/prestations`, c'est-à-dire au français — depuis une page anglaise, un lien
 * sur deux ramenait à la langue qu'on venait de quitter.
 *
 * Le proxy rattraperait le coup, parce que le cookie dit encore « anglais » :
 * il redirigerait vers `/en/prestations`. Mais une redirection par navigation,
 * sur un téléphone en 3G, c'est un aller-retour réseau complet avant que la
 * page commence à se charger — pour une information que le navigateur avait
 * déjà.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'il ne touche pas
 * ---------------------------------------------------------------------------
 *
 * Les ancres (`#tarifs`), les adresses complètes (`https://…`, `mailto:`) et
 * les liens vers un autre hôte de la plateforme — l'espace professionnel vit
 * sur `app.` et porte sa propre langue. Seul un chemin qui commence par une
 * barre oblique appartient au site courant.
 */

import NextLink from "next/link";
import { useLocale } from "next-intl";
import type { ComponentProps } from "react";

import { prefixe, type Langue } from "@/i18n/langues";

type Props = Omit<ComponentProps<typeof NextLink>, "href"> & { href: string };

export function Lien({ href, ...reste }: Props) {
  const langue = useLocale() as Langue;
  const cible = href.startsWith("/") ? `${prefixe(langue)}${href}` : href;
  return <NextLink href={cible} {...reste} />;
}
