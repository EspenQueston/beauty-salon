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
 * Le composant porte l'effet sur un conteneur ou une balise sémantique.
 */

import {
  useEffect,
  useRef,
  type CSSProperties,
  type ElementType,
  type ReactNode,
} from "react";

const waiting = new Set<HTMLElement>();
let sharedObserver: IntersectionObserver | null = null;
let startupTimeout: ReturnType<typeof setTimeout> | undefined;
let motionQuery: MediaQueryList | null = null;

/**
 * Arrivée en bas de page : tout ce qui attend encore apparaît.
 *
 * Le déclenchement attend qu'un bloc ait franchi le dernier dixième de
 * l'écran. Un petit bloc posé tout en bas de la page ne l'atteindrait jamais,
 * même la page parcourue jusqu'au bout — il resterait invisible.
 */
function onScroll() {
  const bas = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
  if (bas) failOpen();
}

function releaseObserver() {
  window.removeEventListener("scroll", onScroll);
  sharedObserver?.disconnect();
  sharedObserver = null;
  clearTimeout(startupTimeout);
  startupTimeout = undefined;
  motionQuery?.removeEventListener("change", onMotionChange);
  motionQuery = null;
}

function showImmediately(element: HTMLElement) {
  element.dataset.visible = "true";
  delete element.dataset.revealReady;
  waiting.delete(element);
  sharedObserver?.unobserve(element);
}

function failOpen() {
  for (const element of waiting) showImmediately(element);
  releaseObserver();
}

function onMotionChange(event: MediaQueryListEvent) {
  if (event.matches) failOpen();
}

function watch(element: HTMLElement) {
  if (!sharedObserver) {
    sharedObserver = new IntersectionObserver(entries => {
      if (entries.length) {
        clearTimeout(startupTimeout);
        startupTimeout = undefined;
      }
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        (entry.target as HTMLElement).dataset.visible = "true";
        sharedObserver?.unobserve(entry.target);
        waiting.delete(entry.target as HTMLElement);
      }
      if (!waiting.size) {
        releaseObserver();
      }
      // Le bloc apparaît quand il a franchi le dernier dixième de l'écran,
      // et non à son premier pixel : sinon une grande section s'animait tout
      // en bas, hors du regard, et l'effet passait inaperçu.
    }, { rootMargin: "0px 0px -10% 0px", threshold: 0.01 });
    motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    motionQuery.addEventListener("change", onMotionChange);
    window.addEventListener("scroll", onScroll, { passive: true });
    // A broken/polyfilled observer must never leave content hidden.
    startupTimeout = setTimeout(failOpen, 1500);
  }
  waiting.add(element);
  sharedObserver.observe(element);
  // Opt in only after observation succeeds. Server HTML is visible by default.
  element.dataset.revealReady = "true";
  return () => {
    sharedObserver?.unobserve(element);
    waiting.delete(element);
    delete element.dataset.revealReady;
    if (!waiting.size) {
      releaseObserver();
    }
  };
}

interface Props {
  children: ReactNode;
  /** Décalage en millisecondes : donne le rythme à une grille de cartes. */
  delay?: number;
  /** Homepage cascade index; timing is defined by --home-stagger in CSS. */
  order?: number;
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
  variant?: "rise" | "tilt" | "cinema" | "section";
  /** Inclinaison de départ, en degrés. Ignorée hors « tilt ». */
  angle?: number;
}

export function Reveal({
  children,
  delay = 0,
  order,
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
    if (element.dataset.visible === "true") return;

    // A hidden tab keeps its offscreen entrances for when it becomes visible.
    // Without IntersectionObserver, or with reduced motion, show immediately.
    if (
      typeof IntersectionObserver === "undefined" ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      element.dataset.visible = "true";
      return;
    }

    // Déjà à l'écran quand la page s'hydrate (le haut de page) : le contenu
    // est là depuis le HTML, on ne le cache pas pour le refaire apparaître.
    // Sur téléphone, ce masquage-réapparition arrivait après le chargement
    // des scripts — un éclair, et le plus grand élément de la page compté
    // comme affiché une seconde plus tard.
    const r = element.getBoundingClientRect();
    if (r.top < window.innerHeight && r.bottom > 0) {
      element.dataset.visible = "true";
      return;
    }

    try {
      return watch(element);
    } catch {
      // Failed observer setup leaves this block and all pending blocks readable.
      showImmediately(element);
      failOpen();
    }
  }, []);

  // L'angle voyage par variable CSS plutôt que par une classe par valeur :
  // six inclinaisons donneraient six classes qui ne servent qu'ici.
  const style: CSSProperties = {};
  if (delay) style.transitionDelay = `${delay}ms`;
  if (order !== undefined) {
    (style as Record<string, string>)["--reveal-order"] = String(Math.max(0, Math.min(order, 4)));
  }
  if (variant === "tilt" && angle !== undefined) {
    (style as Record<string, string>)["--angle"] = `${angle}deg`;
  }

  return (
    <Tag
      ref={ref}
      id={id}
      className={`${variant === "tilt" ? "tilt" : variant === "section" ? "reveal-section" : variant === "cinema" ? "reveal-cinema" : "reveal"} ${className}`}
      onFocusCapture={() => {
        if (ref.current) showImmediately(ref.current);
        if (!waiting.size) releaseObserver();
      }}
      style={Object.keys(style).length > 0 ? style : undefined}
    >
      {children}
    </Tag>
  );
}
