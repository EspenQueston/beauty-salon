"use client";

/**
 * La commande qui arrête le fond animé de l'accueil.
 *
 * Elle couvre le ciel *et* le défilé de photos : c'est le mécanisme que
 * demande le critère WCAG 2.2.2 pour tout ce qui bouge plus de cinq secondes,
 * et le haut de page d'accueil n'en avait plus depuis le retrait des puces
 * (voir `HeroCarousel`).
 *
 * Discrète — elle ne doit pas concurrencer le bouton « Réserver » — mais
 * toujours présente dans le document, donc atteignable au clavier et annoncée
 * par un lecteur d'écran. Absente quand le système demande déjà moins
 * d'animations : il n'y a alors rien à arrêter.
 */

import { useTranslations } from "next-intl";

import { basculerPauseFond, useMouvementReduit, usePauseFond } from "./fondPause";

export function PauseFond({ className = "" }: { className?: string }) {
  const t = useTranslations("salon.hero");
  const pause = usePauseFond();
  const calme = useMouvementReduit();
  if (calme) return null;

  return (
    <button
      type="button"
      onClick={basculerPauseFond}
      aria-pressed={pause}
      title={pause ? t("reprendreFond") : t("pauseFond")}
      className={`pause-fond flex size-8 items-center justify-center rounded-full border border-white/25 bg-black/20 text-white backdrop-blur transition hover:bg-black/35 focus-visible:opacity-100 ${className}`}
    >
      <span className="sr-only">{pause ? t("reprendreFond") : t("pauseFond")}</span>
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className="size-3">
        {pause ? <path d="M8 5v14l11-7z" /> : <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" />}
      </svg>
    </button>
  );
}
