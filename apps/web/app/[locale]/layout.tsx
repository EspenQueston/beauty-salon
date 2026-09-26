import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import { locale as segment } from "next/root-params";
import { NextIntlClientProvider } from "next-intl";
import { getTranslations } from "next-intl/server";

import { estLangue, LANGUE_PAR_DEFAUT, LANGUES } from "@/i18n/langues";

import "../globals.css";
import { InlineScript } from "../InlineScript";
import { ServiceWorker } from "../ServiceWorker";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

/**
 * Une page par langue, engendrée à l'avance.
 *
 * Sans cette liste, `[locale]` serait un segment purement dynamique et
 * toutes les pages aujourd'hui pré-rendues — la page d'accueil de la
 * plateforme et les dix-huit écrans de l'espace professionnel — passeraient
 * au rendu à la demande. On perdrait le HTML servi depuis le cache pour la
 * seule raison qu'un segment a été ajouté au-dessus d'elles.
 */
export function generateStaticParams() {
  return LANGUES.map((locale) => ({ locale }));
}

/* Le titre et la mention d'ouverture suivent la langue de l'adresse : une
   page anglaise dont l'onglet est en français se remarque tout de suite. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("plateforme");
  return {
    ...metadata,
    title: t("nom"),
    description: t("promesse"),
  };
}

const metadata: Metadata = {
  // Installée sur l'écran d'accueil, l'application doit avoir une icône qui
  // ne soit pas une capture de la page. Les tailles couvrent Android (192,
  // 512), iOS (180) et le masque circulaire d'Android (`maskable`).
  icons: {
    icon: [
      { url: "/icones/beauty-salon-symbol.png", sizes: "1254x1254", type: "image/png" },
    ],
    apple: [{ url: "/icones/beauty-salon-symbol.png", sizes: "1254x1254" }],
  },
  appleWebApp: {
    // iOS ignore le manifeste : ces trois balises sont sa seule façon de
    // savoir qu'une page veut s'ouvrir en plein écran, sans la barre
    // d'adresse de Safari.
    capable: true,
    title: "Beauty Salon",
    statusBarStyle: "black-translucent",
  },
};

/**
 * Ce qu'un téléphone doit savoir avant de peindre la première image.
 *
 * ---------------------------------------------------------------------------
 * `viewportFit: "cover"`, et pourquoi il ne suffit pas
 * ---------------------------------------------------------------------------
 *
 * Il autorise la page à s'étendre sous l'encoche et sous la barre d'accueil.
 * Sans lui, un téléphone récent laisse deux bandes vides. Avec lui seul, en
 * revanche, la barre « Réserver » collée en bas passe *sous* l'indicateur
 * d'accueil de l'iPhone : le bouton est là, on le voit, et le pouce touche la
 * barre système. D'où les `env(safe-area-inset-*)` posées dans `globals.css`
 * sur tout ce qui est fixé aux bords.
 *
 * ---------------------------------------------------------------------------
 * Le zoom reste autorisé
 * ---------------------------------------------------------------------------
 *
 * `maximumScale: 1` et `userScalable: false` reviennent souvent dans les
 * recettes de PWA, pour « faire plus natif ». Ils enlèvent surtout la seule
 * façon qu'a une personne presbyte de lire un tarif sur un téléphone
 * d'entrée de gamme — et une bonne part de la clientèle visée l'est. On ne
 * les pose pas.
 *
 * La couleur de barre suit le thème : une barre système claire au-dessus
 * d'une page sombre est la marque d'une application web mal finie.
 */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0f0f13" },
  ],
};

/**
 * Deux choses à régler avant le premier pixel.
 *
 * `data-theme` : lu depuis localStorage et posé sur <html> tout de suite. Le
 * faire dans un effet React laisserait la page s'afficher en clair puis
 * basculer en sombre — un éclair blanc en pleine nuit.
 *
 * `data-js` : dit aux feuilles de style que le JavaScript tourne. Les blocs
 * à révéler ne partent invisibles que dans ce cas ; sans script, ils
 * s'affichent normalement au lieu de rester cachés pour toujours.
 *
 * Un attribut plutôt qu'une classe : React compare le `className` rendu par
 * le serveur avec celui du DOM à l'hydratation, et une classe ajoutée par ce
 * script provoquerait un avertissement de non-correspondance.
 */
const BOOT = `(function(){try{var r=document.documentElement;r.setAttribute("data-js","");var t=localStorage.getItem("beauty-salon-theme");if(t==="light"||t==="dark")r.setAttribute("data-theme",t)}catch(e){}})()`;

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  /*
   * La langue, lue au paramètre racine.
   *
   * `[locale]` se trouve au-dessus de cette mise en page : Next en fait un
   * paramètre racine, que `next/root-params` sert à n'importe quel composant
   * serveur sans le faire descendre de props en props.
   *
   * Le repli n'est pas théorique. Ce segment attrape aussi les adresses
   * inconnues — `/robots.txt`, une faute de frappe — et `lang="robots.txt"`
   * serait servi tel quel à un lecteur d'écran.
   */
  const brut = await segment();
  const langue = estLangue(brut) ? brut : LANGUE_PAR_DEFAUT;

  return (
    // suppressHydrationWarning : le script ci-dessous modifie <html> avant
    // que React n'hydrate. C'est le motif documenté pour éviter le
    // clignotement de thème.
    <html
      lang={langue}
      className={`${geistSans.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <InlineScript html={BOOT} />
      </head>
      <body className="flex min-h-full flex-col">
        {/*
          Les messages traversent la frontière serveur/client ici.

          Sans ce fournisseur, tout composant marqué `use client` — la barre
          du mini-site, le parcours de réservation, le sélecteur de devise —
          lèverait au premier `useTranslations`. Il est posé à la racine
          parce que ces composants sont dispersés dans les trois surfaces.
        */}
        <NextIntlClientProvider>{children}</NextIntlClientProvider>
        <ServiceWorker />
      </body>
    </html>
  );
}
