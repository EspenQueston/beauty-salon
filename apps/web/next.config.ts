import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

/**
 * En-tetes de securite, poses sur toutes les reponses.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'ils remplacent
 * ---------------------------------------------------------------------------
 *
 * Rien. Le fichier etait vide, et Next n'ajoute aucun en-tete de securite de
 * lui-meme. Une page de mini-site pouvait donc etre encadree dans une iframe
 * par un site tiers, et le navigateur devinait le type des fichiers servis
 * au lieu de s'en tenir a celui qu'on declare.
 *
 * ---------------------------------------------------------------------------
 * La politique de contenu, et sa limite — a lire avant de la durcir
 * ---------------------------------------------------------------------------
 *
 * `script-src` accepte `'unsafe-inline'`, et ce n'est pas un oubli. Deux
 * scripts en ligne sont indispensables au produit : celui qui pose le theme
 * clair/sombre sur `<html>` avant le premier pixel — sans lui, la page
 * s'affiche en clair puis bascule, un eclair blanc en pleine nuit — et ceux
 * que Next injecte pour l'hydratation.
 *
 * Les supprimer demanderait un nonce par requete, donc un middleware qui
 * rend chaque page dynamique : on perdrait le rendu statique de la
 * plateforme pour un gain nul tant que la page n'affiche aucun HTML fourni
 * par un tiers. Elle n'en affiche aucun : tout texte de salon passe par
 * React, qui l'echappe.
 *
 * Les directives qui coutent le plus cher a un attaquant sont, elles, bien
 * en place : `frame-ancestors` interdit l'encadrement, `base-uri` empeche de
 * detourner toutes les URL relatives de la page, `object-src` ferme les
 * greffons, `form-action` interdit d'envoyer un formulaire ailleurs que chez
 * nous. Aucune ne depend d'un nonce.
 */
const EN_PRODUCTION = process.env.NODE_ENV === "production";

/*
  En developpement, l'API et les medias sont servis en clair.

  Les photos d'un salon arrivent de `http://127.0.0.1:8001/media/...` et
  l'API repond sur `http://<salon>.localhost:8001`. Une politique limitee a
  `https:` les bloque toutes : la premiere version de ce fichier a fait
  disparaitre chaque photo de salon de l'ecran de reservation, avec trente
  refus dans la console et aucun indice a l'ecran.

  Enumerer les hotes ne marche pas non plus — `http://localhost:*` ne couvre
  pas `http://blondrose.localhost:8001`, et le nombre de sous-domaines est
  celui du nombre de salons. En developpement on ouvre donc `http:` en
  entier ; en production il n'en reste rien.
*/
const CLAIR = EN_PRODUCTION ? "" : " http:";

const CSP = [
  "default-src 'self'",
  // 'unsafe-inline' : voir le commentaire ci-dessus. 'unsafe-eval' est
  // necessaire au rafraichissement a chaud de Next, et n'existe qu'en
  // developpement.
  `script-src 'self' 'unsafe-inline'${EN_PRODUCTION ? "" : " 'unsafe-eval'"}`,
  // Tailwind injecte ses styles en ligne, et les couleurs du salon sont
  // posees en variables CSS sur l'element racine.
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com data:",
  // `data:` et `blob:` servent aux apercus locaux avant televersement ;
  // `https:` couvre les medias du salon et les illustrations d'ambiance.
  `img-src 'self' data: blob: https:${CLAIR}`,
  `media-src 'self' blob: https:${CLAIR}`,
  `connect-src 'self' https:${CLAIR}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const HEADERS = [
  {
    // Redondant avec `frame-ancestors`, et conserve : les navigateurs plus
    // anciens ne lisent que celui-ci.
    key: "X-Frame-Options",
    value: "DENY",
  },
  {
    // Le navigateur s'en tient au type declare. Une image televersee par un
    // salon ne sera jamais interpretee comme une page.
    key: "X-Content-Type-Options",
    value: "nosniff",
  },
  {
    // L'adresse d'un mini-site ne suit pas les liens sortants : le nom du
    // salon n'a pas a figurer dans les journaux d'un tiers.
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin",
  },
  {
    /*
      Materiel : la camera reste autorisee, et elle seule.

      Ce n'est pas une precaution generique a recopier : l'enregistrement
      d'arrivee lit le QR de la cliente avec l'appareil photo du telephone.
      Poser `camera=()` comme le veut la recette habituelle desactiverait
      cette fonction sans qu'aucun message ne l'explique — la camera ne
      demarrerait simplement jamais.

      Le micro, la geolocalisation et le paiement, eux, ne servent nulle
      part.
    */
    key: "Permissions-Policy",
    value: "camera=(self), microphone=(), geolocation=(), payment=(), usb=()",
  },
  {
    key: "Content-Security-Policy",
    value: EN_PRODUCTION ? `${CSP}; upgrade-insecure-requests` : CSP,
  },
];

const nextConfig: NextConfig = {
  /*
    La pastille de developpement de Next, retiree.

    Elle ne parait qu'en `next dev` — jamais en production — mais elle se
    pose en bas a gauche, exactement la ou le mini-site met sa barre de
    reservation et la plateforme son bouton « remonter ». Elle masquait donc
    ce qu'on cherchait a regarder a chaque capture d'ecran.

    Les erreurs de compilation et d'execution continuent de s'afficher :
    c'est la pastille qui disparait, pas le rapport d'erreur.
  */
  devIndicators: false,
  // Le numero de version de Next dans chaque reponse ne sert qu'a celui qui
  // cherche une faille connue contre la version exacte qu'on execute.
  poweredByHeader: false,

  async headers() {
    return [{ source: "/:path*", headers: HEADERS }];
  },
};

/*
  Le greffon de next-intl relie `i18n/request.ts` au rendu serveur.

  Sans lui, `getTranslations` et `useTranslations` ne trouvent aucune
  configuration et levent des la premiere page : la resolution du fichier de
  requete se fait a la compilation, pas a l'execution.
*/
export default createNextIntlPlugin("./i18n/request.ts")(nextConfig);
