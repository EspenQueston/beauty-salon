import "server-only";

/**
 * Le contenu d'un salon, dans la langue de la page qu'on est en train de rendre.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un module a part
 * ---------------------------------------------------------------------------
 *
 * `lib/api.ts` est importe des deux cotes de la frontiere : le parcours de
 * reservation et l'espace cliente sont des composants client et s'en servent.
 * Y lire `next/root-params`, qui n'existe que sur le serveur, ne produit pas
 * une erreur a l'execution mais un echec de compilation de tout le module —
 * donc une page 500, pour toutes les pages qui en dependent.
 *
 * Ce fichier-ci porte `server-only` : l'importer depuis un composant client
 * echoue tout de suite, avec un message qui dit pourquoi, au lieu de casser
 * quelque chose trois modules plus loin.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi la langue ne se devine pas cote API
 * ---------------------------------------------------------------------------
 *
 * L'appel part du serveur Next vers Django : c'est un appel serveur a serveur,
 * et l'`Accept-Language` du navigateur n'y figure pas. Sans ce parametre, tout
 * mini-site serait servi en francais, y compris sous `/en`.
 *
 * `app/manifest.ts` continue d'appeler `fetchSalon` directement : c'est un
 * gestionnaire de route, ou `next/root-params` n'a pas cours, et un manifeste
 * n'a de toute facon pas de langue — il porte le nom du salon et ses couleurs.
 */

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { locale as segment } from "next/root-params";

import { ENTETE_CHEMIN } from "@/i18n/adresses";
import { estLangue, LANGUE_PAR_DEFAUT, prefixe, type Langue } from "@/i18n/langues";
import { fetchSalon as lireSalon, SalonDeplace } from "@/lib/api";
import type { PublicSalon } from "@/lib/types";

/** La langue du rendu en cours, lue au parametre racine. */
export async function langueDuRendu(): Promise<Langue> {
  const brut = await segment();
  return estLangue(brut) ? brut : LANGUE_PAR_DEFAUT;
}

export async function fetchSalon(host: string): Promise<PublicSalon | null> {
  const langue = await langueDuRendu();
  try {
    return await lireSalon(host, langue);
  } catch (erreur) {
    if (!(erreur instanceof SalonDeplace)) throw erreur;
    // Même page, même langue, à l'adresse que le salon garde sur la
    // plateforme. Un domaine personnalisé n'existe qu'en production : HTTPS.
    const chemin = (await headers()).get(ENTETE_CHEMIN) ?? "/";
    const sur = chemin.startsWith("/") && !chemin.startsWith("//") ? chemin : "/";
    redirect(`https://${erreur.canonique}${prefixe(langue)}${sur === "/" ? "/" : sur}`);
  }
}
