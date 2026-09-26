/**
 * Bandeau de tête des pages intérieures du mini-site.
 *
 * ---------------------------------------------------------------------------
 * Le défilé n'est plus réservé à l'accueil
 * ---------------------------------------------------------------------------
 *
 * Ces pages recevaient un aplat de couleur figé, et l'accueil seul montrait
 * les prestations du salon en fond défilant. On passait donc d'un salon
 * vivant à un gabarit en un clic — précisément l'impression à éviter chez une
 * visiteuse qui est en train de se décider.
 *
 * Le même défilé les habille désormais toutes, tiré des mêmes prestations.
 * Ce n'est pas une option offerte à quelques salons : c'est le comportement
 * par défaut de chaque mini-site, y compris celui qui n'a pas encore
 * téléversé une seule photo — ses prestations reçoivent alors des
 * illustrations d'ambiance choisies d'après leur catégorie.
 *
 * ---------------------------------------------------------------------------
 * Le dégradé reste, et devient le voile
 * ---------------------------------------------------------------------------
 *
 * Il ne disparaît pas : il passe devant les photos. C'est lui qui garde le
 * titre lisible quelle que soit l'image, et c'est lui qui distingue les
 * pages entre elles — en arrivant sur « Réalisations » après « Prestations »,
 * on doit sentir qu'on a changé d'endroit sans avoir à lire le titre.
 *
 * Les cinq variantes partent toutes des deux couleurs du salon : c'est
 * l'angle et le mélange qui changent, pas la palette.
 *
 * L'opacité du voile est plus basse qu'un aplat plein — assez pour que la
 * photo se devine, assez pour que le texte tienne. Sous cette valeur, une
 * photo claire fait disparaître le titre blanc.
 */

import type { ReactNode } from "react";

import { HeroCarousel, type HeroSlide } from "./HeroCarousel";
import { SalonIcon, type SalonIconName } from "./icons";

export type HeroTone = "catalogue" | "galerie" | "equipe" | "infos" | "apropos";

const TONES: Record<HeroTone, string> = {
  apropos:
    "linear-gradient(200deg, color-mix(in srgb, var(--salon-primary) 88%, black) 0%, var(--salon-primary) 40%, color-mix(in srgb, var(--salon-accent) 70%, var(--salon-primary)) 100%)",
  catalogue:
    "linear-gradient(135deg, color-mix(in srgb, var(--salon-primary) 92%, black) 0%, var(--salon-primary) 55%, color-mix(in srgb, var(--salon-primary) 45%, var(--salon-accent)) 100%)",
  galerie:
    "linear-gradient(120deg, color-mix(in srgb, var(--salon-primary) 70%, black) 0%, color-mix(in srgb, var(--salon-primary) 88%, var(--salon-accent)) 60%, var(--salon-accent) 100%)",
  equipe:
    "linear-gradient(160deg, var(--salon-primary) 0%, color-mix(in srgb, var(--salon-primary) 60%, var(--salon-accent)) 70%, color-mix(in srgb, var(--salon-accent) 80%, white) 100%)",
  infos:
    "linear-gradient(105deg, color-mix(in srgb, var(--salon-primary) 82%, black) 0%, color-mix(in srgb, var(--salon-primary) 70%, var(--salon-accent)) 100%)",
};

export function PageHero({
  eyebrow,
  title,
  icon,
  tone,
  slides = [],
  children,
}: {
  eyebrow: string;
  title: string;
  icon: SalonIconName;
  tone: HeroTone;
  /**
   * Les prestations du salon, en fond défilant.
   *
   * Facultatif pour une seule raison : une page qui n'a pas le salon sous la
   * main doit pouvoir s'afficher. Toutes les pages du mini-site les passent.
   */
  slides?: HeroSlide[];
  children?: ReactNode;
}) {
  const withPhotos = slides.length > 0;

  return (
    <header className="relative isolate overflow-hidden text-white">
      {withPhotos && <HeroCarousel slides={slides} variant="bandeau" />}

      {/*
        Le dégradé de la page, posé *par-dessus* les photos.

        Sans photos il est le fond, opaque. Avec elles il devient le voile :
        assez dense pour que le titre blanc tienne sur n'importe quelle image,
        assez transparent pour qu'on reconnaisse ce qu'elle montre. C'est lui
        qui garde chaque page distincte des autres.
      */}
      <div
        aria-hidden
        className={`absolute inset-0 -z-10 ${withPhotos ? "opacity-[0.82]" : ""}`}
        style={{ background: TONES[tone] }}
      />

      {/* Deux halos très diffus : ils donnent du volume à un aplat sans
          rien coûter en téléchargement. */}
      <span
        aria-hidden
        className="pointer-events-none absolute -right-24 -top-32 -z-10 size-80 rounded-full bg-white/20 blur-3xl"
      />
      <span
        aria-hidden
        className="pointer-events-none absolute -bottom-40 -left-20 -z-10 size-80 rounded-full bg-black/20 blur-3xl"
      />

      {/* Comme sur l'accueil, la marge haute réserve la place du menu fixe. */}
      <div className="relative mx-auto max-w-5xl px-4 pb-20 pt-24 sm:pb-24 sm:pt-28">
        <span className="rise inline-flex size-12 items-center justify-center rounded-2xl bg-white/15 backdrop-blur">
          <SalonIcon name={icon} className="size-6" />
        </span>

        <p
          className="rise mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-white/75"
          style={{ animationDelay: "60ms" }}
        >
          {eyebrow}
        </p>

        <h1
          className="rise mt-2 text-3xl font-semibold tracking-tight sm:text-5xl"
          style={{ animationDelay: "120ms" }}
        >
          {title}
        </h1>

        {children && (
          <div className="rise mt-5" style={{ animationDelay: "180ms" }}>
            {children}
          </div>
        )}
      </div>

      <svg
        aria-hidden
        viewBox="0 0 1440 96"
        preserveAspectRatio="none"
        className="absolute inset-x-0 bottom-0 h-12 w-full sm:h-16"
      >
        <path
          d="M0 96V56c240 30 500 38 720 18s480-28 720-6v28z"
          fill="var(--site-ground)"
        />
      </svg>
    </header>
  );
}
