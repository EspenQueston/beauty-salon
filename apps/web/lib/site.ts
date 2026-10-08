/**
 * Adresses des différentes faces du produit.
 *
 * Elles vivent sur des hôtes distincts — `localhost` pour la plateforme,
 * `app.localhost` pour l'espace professionnel — et un lien de l'une vers
 * l'autre ne peut donc pas être relatif. Tout part de `PLATFORM_DOMAIN` :
 * le jour où un vrai domaine remplace `localhost`, rien d'autre ne bouge.
 */

export const PLATFORM_DOMAIN =
  process.env.NEXT_PUBLIC_PLATFORM_DOMAIN ?? "localhost";
const WEB_PORT = process.env.NEXT_PUBLIC_WEB_PORT ?? "3100";

/** Le port disparaît de lui-même en production, où il est implicite. */
function origin(host: string): string {
  const scheme = PLATFORM_DOMAIN === "localhost" ? "http" : "https";
  const port = WEB_PORT === "80" || WEB_PORT === "443" ? "" : `:${WEB_PORT}`;
  return `${scheme}://${host}${port}`;
}

/** Site public de la plateforme. */
export const platformUrl = origin(PLATFORM_DOMAIN);

/** Espace professionnel des salons. */
export const appUrl = origin(`app.${PLATFORM_DOMAIN}`);

/** Mini-site d'un salon. */
export function salonUrl(slug: string): string {
  return origin(`${slug}.${PLATFORM_DOMAIN}`);
}
