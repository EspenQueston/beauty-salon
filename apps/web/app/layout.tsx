import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { InlineScript } from "./InlineScript";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Beauty Salon",
  description: "La plateforme de réservation des professionnels de la beauté.",
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
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
