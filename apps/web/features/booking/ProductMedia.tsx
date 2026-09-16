/**
 * La vignette d'un article : sa photo, sa vidéo, ou une image d'ambiance.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un composant partagé
 * ---------------------------------------------------------------------------
 *
 * Le même article s'affiche à deux endroits — dans le parcours de
 * réservation, où la cliente décide, et dans la boutique du panneau salon,
 * où le gérant gère son stock. Deux rendus séparés auraient divergé au
 * premier changement : la vidéo marcherait d'un côté, pas de l'autre.
 *
 * ---------------------------------------------------------------------------
 * Les trois cas
 * ---------------------------------------------------------------------------
 *
 *   - **Vidéo** : `<video>`, muette, en boucle, sans commande. Elle tourne
 *     toute seule parce qu'elle sert d'illustration, pas de contenu — et
 *     `playsInline` évite que Safari mobile la passe en plein écran au
 *     premier contact.
 *   - **Photo** : `<img>`, en chargement différé.
 *   - **Rien** : une image d'ambiance choisie d'après le nom de l'article.
 *     Une carte vide se lit comme un article indisponible, ou comme un site
 *     inachevé ; mieux vaut une photo qui ressemble à ce qu'elle désigne.
 *
 * L'image de repli porte un `alt` vide et `aria-hidden` : elle n'est pas la
 * photo de l'article, et l'annoncer comme telle induirait en erreur qui ne
 * la voit pas.
 */

import { productIllustrationUrl } from "@/lib/illustrations";

export function ProductMedia({
  id,
  name,
  url,
  type,
  fallback,
  className = "",
  width = 400,
}: {
  id: string;
  name: string;
  /**
   * Image de repli imposée par la liste, quand il y en a une.
   *
   * Seule la liste sait quelles images ses voisins ont déjà prises : deux
   * articles côte à côte tombaient sinon régulièrement sur la même photo,
   * ce qui se lit comme un bug d'affichage.
   */
  fallback?: string;
  /** URL du média téléversé par le salon. Vide s'il n'en a pas mis. */
  url: string;
  /** Type MIME du média. Vide quand `url` l'est. */
  type: string;
  className?: string;
  width?: number;
}) {
  if (url && type.startsWith("video/")) {
    return (
      <video
        src={url}
        muted
        loop
        autoPlay
        playsInline
        preload="metadata"
        aria-label={name}
        className={className}
      />
    );
  }

  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt={name} loading="lazy" className={className} />;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={fallback ?? productIllustrationUrl(name, id, { width })}
      alt=""
      aria-hidden
      loading="lazy"
      className={className}
    />
  );
}
