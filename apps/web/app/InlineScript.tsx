/**
 * Script exécuté pendant l'analyse du HTML, avant le premier rendu.
 *
 * React avertit dès qu'un composant produit une balise `<script>` : celles
 * insérées après coup ne s'exécutent jamais côté client. Le motif documenté
 * par Next.js consiste donc à ne rendre un script *exécutable* que côté
 * serveur — côté client, `type="text/plain"` en fait un simple bloc de texte
 * inerte, et `suppressHydrationWarning` accepte cette différence.
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
