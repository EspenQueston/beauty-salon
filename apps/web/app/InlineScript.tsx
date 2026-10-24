"use client";

/**
 * Script exécuté pendant l'analyse du HTML, avant le premier rendu.
 *
 * React avertit dès qu'un composant produit une balise `<script>` : celles
 * insérées après coup ne s'exécutent jamais côté client. Le motif documenté
 * par Next.js consiste donc à ne rendre un script *exécutable* que côté
 * serveur — côté client, `type="text/plain"` en fait un simple bloc de texte
 * inerte, et `suppressHydrationWarning` accepte cette différence.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi c'est un composant client
 * ---------------------------------------------------------------------------
 *
 * Sans `"use client"`, ce composant était un composant serveur : son `type`
 * était calculé une seule fois, sur le serveur, et figé à `text/javascript`
 * dans les données envoyées au navigateur. Le jour où React devait recréer
 * cette partie de la page côté client — rechargement à chaud en
 * développement, reprise après une erreur d'hydratation — il fabriquait un
 * `<script>` exécutable et levait « Encountered a script tag while rendering
 * React component ». En composant client, la condition est réévaluée dans le
 * navigateur : le rendu serveur reste exécutable, toute recréation est inerte.
 *
 * Voir `node_modules/next/dist/docs/01-app/02-guides/preventing-flash-before-hydration.md`.
 */
export function InlineScript({ html }: { html: string }) {
  return (
    <script
      type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
