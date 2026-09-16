"use client";

/**
 * En-tête du site de la plateforme, en pastille flottante.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi elle flotte plutôt que de border le haut de page
 * ---------------------------------------------------------------------------
 *
 * Une barre pleine largeur coupe la page d'un trait horizontal, et ce trait
 * est la première chose qu'on voit — avant le titre. En pastille, la
 * navigation se pose *sur* la page sans la couper : le regard tombe
 * directement sur la promesse, et le menu reste à portée, reconnaissable à sa
 * forme plutôt qu'à sa bordure.
 *
 * Elle reste courte par choix : quatre entrées, dont deux mènent à l'action.
 * Une barre qui propose douze destinations ne dit plus laquelle compte.
 *
 * ---------------------------------------------------------------------------
 * Ce que le défilement change
 * ---------------------------------------------------------------------------
 *
 * Presque rien, et c'est voulu. La pastille a son propre fond dès le départ,
 * donc ses liens restent lisibles quel que soit ce qui passe dessous. On se
 * contente de renforcer l'ombre : elle se décolle un peu, ce qui suffit à
 * dire qu'on a quitté le haut de page.
 */

import { useEffect, useState } from "react";

import { appUrl } from "@/lib/site";
import { ThemeToggle } from "@/features/ui/ThemeToggle";

const LINKS = [
  { href: "#fonctionnalites", label: "Fonctionnalités" },
  { href: "#apercu", label: "Aperçu" },
  { href: "#etapes", label: "Comment ça marche" },
  { href: "#questions", label: "Questions" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className="fixed inset-x-0 top-0 z-40 px-3 pt-3 sm:px-4 sm:pt-4">
      <div
        className={`mx-auto max-w-5xl rounded-2xl border border-line bg-surface/85 backdrop-blur-xl transition-shadow duration-300 ${
          scrolled ? "shadow-float" : "shadow-card"
        }`}
      >
        <div className="flex items-center gap-4 px-3 py-2.5 sm:px-4">
          <a href="#haut" className="flex items-center gap-2.5">
            <span className="salon-gradient inline-flex size-8 items-center justify-center rounded-xl text-sm font-semibold text-white">
              BS
            </span>
            <span className="font-semibold tracking-tight text-ink">
              Beauty Salon
            </span>
          </a>

          <nav
            aria-label="Navigation principale"
            className="ml-auto hidden md:block"
          >
            <ul className="flex items-center gap-1">
              {LINKS.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    className="rounded-lg px-3 py-2 text-sm font-medium text-muted transition hover:bg-surface-hover hover:text-ink"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <ThemeToggle />

            <a
              href={appUrl}
              className="hidden rounded-lg px-3 py-2 text-sm font-medium text-muted transition hover:bg-surface-hover hover:text-ink sm:inline-flex"
            >
              Se connecter
            </a>

            <a
              href={`${appUrl}/inscription`}
              className="salon-gradient hidden rounded-xl px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:brightness-110 sm:inline-flex"
            >
              Créer mon salon
            </a>

            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              aria-expanded={open}
              aria-controls="menu-mobile"
              aria-label={open ? "Fermer le menu" : "Ouvrir le menu"}
              className="inline-flex size-9 items-center justify-center rounded-lg border border-line bg-surface text-muted transition hover:bg-surface-hover hover:text-ink md:hidden"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                aria-hidden
                className="size-5"
              >
                {open ? (
                  <path d="m6 6 12 12M18 6 6 18" strokeLinecap="round" />
                ) : (
                  <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Le tiroir se déplie dans la pastille : il en fait partie, au lieu
            de recouvrir le premier paragraphe qu'on venait de lire. */}
        <div
          id="menu-mobile"
          hidden={!open}
          className="border-t border-line px-3 py-3 md:hidden"
        >
          <ul className="grid grid-cols-2 gap-1">
            {LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className="block rounded-lg px-3 py-2.5 text-sm font-medium text-ink transition hover:bg-surface-hover"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>

          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3">
            <a
              href={`${appUrl}/inscription`}
              className="salon-gradient rounded-xl px-4 py-2.5 text-center text-sm font-semibold text-white"
            >
              Créer mon salon
            </a>
            <a
              href={appUrl}
              className="rounded-xl border border-line px-4 py-2.5 text-center text-sm font-medium text-ink"
            >
              Se connecter
            </a>
          </div>
        </div>
      </div>
    </header>
  );
}
