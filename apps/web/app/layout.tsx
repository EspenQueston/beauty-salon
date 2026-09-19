import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { InlineScript } from "./InlineScript";
import { ServiceWorker } from "./ServiceWorker";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Beauty Salon",
  description: "La plateforme de réservation des professionnels de la beauté.",
  // Installée sur l'écran d'accueil, l'application doit avoir une icône qui
  // ne soit pas une capture de la page. Les tailles couvrent Android (192,
  // 512), iOS (180) et le masque circulaire d'Android (`maskable`).
  icons: {
    icon: [
      { url: "/icones/192.png", sizes: "192x192", type: "image/png" },
      { url: "/icones/512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icones/apple-180.png", sizes: "180x180" }],
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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // suppressHydrationWarning : le script ci-dessous modifie <html> avant
    // que React n'hydrate. C'est le motif documenté pour éviter le
    // clignotement de thème.
    <html
      lang="fr"
      className={`${geistSans.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <InlineScript html={BOOT} />
      </head>
      <body className="flex min-h-full flex-col">
        {children}
        <ServiceWorker />
      </body>
    </html>
  );
}
