/**
 * Aiguillage par sous-domaine (convention `proxy` de Next.js 16).
 *
 *   blondrose.localhost  ->  /s/blondrose.localhost/...   (mini-site du salon)
 *   app.localhost        ->  /dashboard/...               (espace professionnel)
 *   localhost            ->  /...                         (site de la plateforme)
 *
 * Les navigateurs resolvent nativement n'importe quel sous-domaine de
 * .localhost vers la boucle locale (RFC 6761) : pas de DNS a configurer, pas
 * de fichier hosts a modifier, et le trafic ne traverse pas un eventuel
 * proxy local.
 *
 * Le hostname complet est conserve dans l'URL reecrite : c'est lui que les
 * composants serveur renvoient a l'API comme identifiant de salon. Aucun
 * identifiant technique n'apparait donc dans une URL publique.
 *
 * Le segment est `/s/` et non `/_sites/` : dans l'App Router, un dossier
 * prefixe d'un underscore est prive et ne produit aucune route - la
 * reecriture tomberait en 404.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PLATFORM_DOMAIN = process.env.NEXT_PUBLIC_PLATFORM_DOMAIN ?? "localhost";

/** Sous-domaines de la plateforme : ils n'appartiennent a aucun salon. */
const RESERVED = new Set(["www", "api", "admin", "static", "media", "mail"]);

/** Hotes qui designent la plateforme elle-meme, pas un salon. */
const PLATFORM_HOSTS = new Set([PLATFORM_DOMAIN, "127.0.0.1", "[::1]", "::1"]);

function subdomainOf(hostname: string): string | null {
  if (PLATFORM_HOSTS.has(hostname)) return null;
  if (!hostname.endsWith(`.${PLATFORM_DOMAIN}`)) {
    // Domaine personnalise (offre Pro) : le backend saura le resoudre.
    return hostname;
  }
  const prefix = hostname.slice(0, -(PLATFORM_DOMAIN.length + 1));
  return prefix || null;
}

export default function proxy(request: NextRequest) {
  const hostname = (request.headers.get("host") ?? "").split(":")[0].toLowerCase();
  const label = subdomainOf(hostname);
  const { pathname } = request.nextUrl;

  // Chemin deja reecrit (ou atteint directement) : on le sert tel quel.
  // Sans ce garde-fou, app.localhost/dashboard deviendrait /dashboard/dashboard.
  // Le contenu servi est le meme que sur le sous-domaine ; c'est la balise
  // canonique du mini-site, pas un 404, qui evite la duplication SEO.
  if (pathname.startsWith("/s/") || pathname.startsWith("/dashboard")) {
    return NextResponse.next();
  }

  if (!label || RESERVED.has(label)) {
    return NextResponse.next();
  }

  const url = request.nextUrl.clone();
  const suffix = pathname === "/" ? "" : pathname;

  url.pathname = label === "app" ? `/dashboard${suffix}` : `/s/${hostname}${suffix}`;
  return NextResponse.rewrite(url);
}

export const config = {
  matcher: [
    /*
      Tout sauf les fichiers internes de Next et les assets statiques.

      Trois chemins sont exclus volontairement. Tous doivent être servis **à
      la racine de l'hôte**, sans réécriture :

        - `manifest.webmanifest` est unique et se façonne lui-même d'après
          l'en-tête `Host` ; réécrit vers `/s/<hôte>/…`, il n'existerait pas ;
        - `sw.js` : un service worker ne gouverne que les chemins situés sous
          le sien. Servi depuis `/s/<hôte>/sw.js`, il ne verrait rien du site ;
        - `hors-ligne` est la page de secours du service worker. Réécrite, elle
          répondait 404 sur tous les sous-domaines — c'est-à-dire partout où
          elle sert.
    */
    "/((?!_next/static|_next/image|favicon.ico|manifest.webmanifest|sw.js|hors-ligne|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
