"use client";

/**
 * Retour en haut de page, et retour à l'accueil.
 *
 * Les deux vont ensemble : sur une page longue lue au pouce, remonter à la
 * main coûte une dizaine de gestes, et le lien du logo est justement en haut
 * — là où on n'est plus.
 *
 * Le bouton n'existe pas tant qu'on n'a pas descendu : au chargement, il
 * masquerait du contenu pour proposer une action sans objet.
 *
 * Il se place au-dessus de la barre de réservation quand celle-ci existe,
 * d'où le décalage vertical réglable.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { decouper } from "@/i18n/langues";
import { useEffect, useState } from "react";

interface Props {
  /**
   * Chemin de l'accueil. Le bouton « accueil » n'apparaît que si on n'y est
   * pas déjà — sinon il ne ferait rien.
   */
  home?: string;
  /** Marge basse, pour laisser passer une barre fixe. */
  offset?: string;
}

export function ScrollTop({ home = "/", offset = "6.5rem" }: Props) {
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 600);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function toTop() {
    // `smooth` est ignoré si la personne a demandé moins d'animations : le
    // navigateur applique alors un saut immédiat, ce qui reste correct.
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Comparé sans le préfixe de langue : `/en` est aussi l'accueil.
  const atHome = decouper(pathname).reste === home;

  return (
    <div
      aria-hidden={!visible}
      // La barre « Réserver » a grandi de la marge système : ce bouton, qui
      // se pose juste au-dessus, doit grandir d'autant. `env()` vaut 0 là où
      // il n'y a pas d'encoche, donc le décalage d'origine est conservé.
      style={{ bottom: `calc(${offset} + env(safe-area-inset-bottom))` }}
      className={`fixed right-4 z-30 flex flex-col items-center gap-2 transition-all duration-300 ${
        visible
          ? "translate-y-0 opacity-100"
          : "pointer-events-none translate-y-3 opacity-0"
      }`}
    >
      {!atHome && (
        <Link
          href={home}
          tabIndex={visible ? undefined : -1}
          aria-label="Retour à l'accueil"
          title="Retour à l'accueil"
          className="flex size-11 items-center justify-center rounded-full border border-[var(--site-line,rgb(0_0_0/0.1))] bg-[var(--site-surface,#fff)] text-[var(--site-muted,#5f5f6b)] shadow-lg transition hover:-translate-y-0.5 hover:text-[var(--salon-primary)]"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
            className="size-5"
          >
            <path d="M3.5 11.5 12 4l8.5 7.5" />
            <path d="M6 10.5V20h12v-9.5" />
            <path d="M10 20v-5h4v5" />
          </svg>
        </Link>
      )}

      <button
        type="button"
        onClick={toTop}
        tabIndex={visible ? undefined : -1}
        aria-label="Remonter en haut de la page"
        title="Remonter"
        className="flex size-11 items-center justify-center rounded-full border border-[var(--site-line,rgb(0_0_0/0.1))] bg-[var(--site-surface,#fff)] text-[var(--site-muted,#5f5f6b)] shadow-lg transition hover:-translate-y-0.5 hover:text-[var(--salon-primary)]"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
          className="size-5"
        >
          <path d="M12 19V5M6 11l6-6 6 6" />
        </svg>
      </button>
    </div>
  );
}
