"use client";

/**
 * Apparition au défilement.
 *
 * Un seul `IntersectionObserver` pour toute la page plutôt qu'un par bloc :
 * sur un téléphone d'entrée de gamme, quinze observateurs coûtent plus cher
 * que l'effet ne rapporte. Chaque élément est cessé d'être observé dès qu'il
 * est apparu — l'animation ne se rejoue pas quand on remonte, ce qui serait
 * pénible à la lecture.
 *
 * Le composant ne rend aucun élément supplémentaire : il pose la classe sur
 * son enfant, donc la mise en page reste celle qu'on a écrite.
 */

import {
  useEffect,
  useRef,
  type CSSProperties,
  type ElementType,
  type ReactNode,
} from "react";

interface Props {
  children: ReactNode;
  /** Décalage en millisecondes : donne le rythme à une grille de cartes. */
  delay?: number;
  className?: string;
  as?: ElementType;
  /** Cible d'ancre : utile quand le bloc révélé est aussi une section. */
  id?: string;
  /**
   * Forme du mouvement.
   *
   *   « rise » : le bloc monte. Le cas courant.
   *   « tilt » : il arrive de biais et se redresse. Réservé aux empilements
   *              de cartes, où l'inclinaison raconte une pile qu'on défait —
   *              ailleurs, ce serait du mouvement pour du mouvement.
   */
  variant?: "rise" | "tilt";
  /** Inclinaison de départ, en degrés. Ignorée hors « tilt ». */
  angle?: number;
}

export function Reveal({
  children,
  delay = 0,
  className = "",
  as: Tag = "div",
  id,
  variant = "rise",
  angle,
}: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    // Deux cas où l'on renonce à l'animation et affiche tout de suite :
    //
    //   - pas d'IntersectionObserver ;
    //   - onglet ouvert en arrière-plan, qui ne compose pas la page et ne
    //     rend donc aucune entrée d'observation. Le contenu resterait
    //     invisible jusqu'à ce qu'on regarde l'onglet.
    //
    // Dans les deux cas personne ne voit le mouvement : mieux vaut une page
    // sans animation qu'une page vide.
    if (
      typeof IntersectionObserver === "undefined" ||
      document.visibilityState === "hidden"
    ) {
      element.dataset.visible = "true";
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          (entry.target as HTMLElement).dataset.visible = "true";
          observer.unobserve(entry.target);
        }
      },
      // La marge négative en bas déclenche l'apparition un peu avant que le
      // bloc n'atteigne le bord : il finit son mouvement au moment où le
      // regard l'atteint.
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // L'angle voyage par variable CSS plutôt que par une classe par valeur :
  // six inclinaisons donneraient six classes qui ne servent qu'ici.
  const style: CSSProperties = {};
  if (delay) style.transitionDelay = `${delay}ms`;
  if (variant === "tilt" && angle !== undefined) {
    (style as Record<string, string>)["--angle"] = `${angle}deg`;
  }

  return (
    <Tag
      ref={ref}
      id={id}
      className={`${variant === "tilt" ? "tilt" : "reveal"} ${className}`}
      style={Object.keys(style).length > 0 ? style : undefined}
    >
      {children}
    </Tag>
  );
}
