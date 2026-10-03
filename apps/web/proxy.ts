/**
 * Aiguillage par sous-domaine et par langue (convention `proxy` de Next 16).
 *
 *   blondrose.localhost      ->  /fr/s/blondrose.localhost/...  (mini-site)
 *   blondrose.localhost/en   ->  /en/s/blondrose.localhost/...
 *   app.localhost            ->  /fr/dashboard/...              (espace pro)
 *   localhost                ->  /fr/...                        (plateforme)
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
 *
 * ---------------------------------------------------------------------------
 * La langue, et pourquoi elle est resolue ici
 * ---------------------------------------------------------------------------
 *
 * Tout `app/` vit sous `app/[locale]/`. Ce segment est donc un **parametre
 * racine** : `next/root-params` le sert a n'importe quel composant serveur,
 * et le rendu statique des pages qui en beneficient est conserve, une copie
 * par langue. C'est ce que permet de faire ce fichier, et lui seul : il est
 * le seul endroit qui voie a la fois l'URL publique, le cookie et l'en-tete
 * `Accept-Language`.
 *
 * Dans la barre d'adresse, le francais n'a pas de prefixe et l'anglais en a
 * un — voir `i18n/langues.ts` pour le pourquoi.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { ENTETE_CHEMIN } from "@/i18n/adresses";
import {
  COOKIE_LANGUE,
  LANGUE_PAR_DEFAUT,
  decouper,
  estLangue,
  langueDemandee,
  type Langue,
} from "@/i18n/langues";

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

  /*
    L'URL publique se lit en deux morceaux : la langue, et le reste.

    `decouper` renvoie `null` quand aucun prefixe n'est present — ce qui n'est
    pas la meme chose que « francais ». Sans prefixe, le choix n'a pas encore
    ete exprime dans l'adresse, et il reste le cookie puis le navigateur a
    consulter.
  */
  const { langue: explicite, reste } = decouper(request.nextUrl.pathname);

  const stocke = request.cookies.get(COOKIE_LANGUE)?.value;
  const langue: Langue =
    explicite ??
    (estLangue(stocke) ? stocke : null) ??
    langueDemandee(request.headers.get("accept-language")) ??
    LANGUE_PAR_DEFAUT;

  /*
    L'adresse doit dire la langue qu'elle sert.

    Quand la langue retenue n'est pas celle par defaut et que l'URL ne la
    porte pas, on redirige plutot que de reecrire : sans cela, la meme
    adresse servirait deux contenus differents selon le lecteur. Un lien
    partage ne voudrait plus rien dire, et un moteur d'indexation prendrait
    l'une des deux versions pour un doublon de l'autre.

    Redirection **temporaire** : elle depend du cookie et de l'en-tete du
    navigateur, jamais du chemin seul. Une 301 serait mise en cache et
    enfermerait la machine dans une langue.

    `hors-ligne` en est exempte : le service worker met cette page de cote a
    l'installation, et une reponse redirigee ne peut pas resservir a une
    navigation — la page de secours ne s'afficherait jamais.
  */
  const horsLigne = reste === "/hors-ligne";
  if (!explicite && langue !== LANGUE_PAR_DEFAUT && !horsLigne) {
    const cible = request.nextUrl.clone();
    cible.pathname = `/${langue}${reste === "/" ? "" : reste}`;
    const reponse = NextResponse.redirect(cible, 307);
    // Sans cela, un cache partage servirait a tout le monde la redirection
    // calculee pour le premier visiteur venu.
    reponse.headers.set("Vary", "Accept-Language, Cookie");
    return reponse;
  }

  /*
    Le chemin interne.

    `/s/...` et `/dashboard/...` peuvent arriver deja formes — on les atteint
    directement en developpement, et Next les reutilise tels quels. Il ne
    reste alors qu'a leur poser la langue devant.
  */
  let interne: string;
  if (horsLigne) {
    interne = "/hors-ligne";
  } else if (reste.startsWith("/s/") || reste.startsWith("/dashboard")) {
    interne = reste;
  } else if (!label || RESERVED.has(label)) {
    interne = reste;
  } else if (label === "app") {
    interne = `/dashboard${reste === "/" ? "" : reste}`;
  } else {
    interne = `/s/${hostname}${reste === "/" ? "" : reste}`;
  }

  const url = request.nextUrl.clone();
  url.pathname = `/${langue}${interne === "/" ? "" : interne}`;

  /*
    Le chemin public, transmis aux pages.

    Elles ne le connaissent pas autrement : elles reçoivent le chemin interne
    (`/fr/s/blondrose.com/prestations`) et n'ont aucun moyen de remonter à
    celui de la barre d'adresse (`/prestations`). Or c'est celui-là qu'il faut
    pour écrire la balise canonique et les `hreflang` — une page qui se
    déclare sous son adresse interne ne serait jamais indexée.

    Sans préfixe de langue : chaque page le remet elle-même pour désigner sa
    sœur dans l'autre langue.
  */
  const entetes = new Headers(request.headers);
  entetes.set(ENTETE_CHEMIN, reste);

  return NextResponse.rewrite(url, { request: { headers: entetes } });
}

export const config = {
  matcher: [
    /*
      Tout sauf les fichiers internes de Next et les assets statiques.

      Deux chemins sont exclus volontairement. Tous deux doivent être servis
      **à la racine de l'hôte**, sans réécriture :

        - `manifest.webmanifest` est unique et se façonne lui-même d'après
          l'en-tête `Host` ; réécrit vers `/s/<hôte>/…`, il n'existerait pas ;
        - `sw.js` : un service worker ne gouverne que les chemins situés sous
          le sien. Servi depuis `/s/<hôte>/sw.js`, il ne verrait rien du site.

      `hors-ligne`, lui, y est revenu. Il en était sorti parce que la
      réécriture l'envoyait vers `/s/<hôte>/hors-ligne`, qui n'existe pas ;
      depuis que toutes les routes vivent sous `[locale]`, il lui faut au
      contraire passer par ici pour recevoir sa langue. Le proxy le traite à
      part : jamais de redirection, seulement une réécriture.

      `notification-image/` non plus : c'est le système d'exploitation qui
      télécharge cette image, sans langue ni session. Réécrite vers
      `/fr/dashboard/notification-image/…`, elle n'existerait pas, et chaque
      notification arriverait sans son image.
    */
    "/((?!_next/static|_next/image|favicon.ico|manifest.webmanifest|sw.js|notification-image/|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|mp4|webm)$).*)",
  ],
};
