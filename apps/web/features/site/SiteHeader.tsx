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
import { useTranslations } from "next-intl";

import { SelecteurLangue } from "@/features/ui/SelecteurLangue";
import { ThemeToggle } from "@/features/ui/ThemeToggle";

const LINKS = [
  /* Les libellés viennent du catalogue : seule l'ancre est écrite ici,
     parce qu'elle désigne un `id` du document et ne se traduit pas. */
  { href: "#fonctionnalites", cle: "fonctionnalites" },
  { href: "#film", cle: "film" },
  { href: "#apercu", cle: "apercu" },
  { href: "#etapes", cle: "etapes" },
  { href: "#questions", cle: "questions" },
];

export function SiteHeader() {
  const t = useTranslations("site");
  const c = useTranslations("commun");
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
            <span className="whitespace-nowrap font-semibold tracking-tight text-ink">
              Beauty Salon
            </span>
          </a>

          <nav
            aria-label={t("nav.principale")}
            className="ml-auto hidden md:block"
          >
            <ul className="flex items-center gap-1">
              {LINKS.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    className="whitespace-nowrap rounded-lg px-2.5 py-2 text-sm font-medium text-muted transition hover:bg-surface-hover hover:text-ink"
                  >
                    {t(`nav.${link.cle}`)}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <div className="ml-auto flex items-center gap-2 md:ml-0">
            {/* Sous 640 px la barre garde le logo, le thème, l'appel à
                l'action et le menu : la langue rejoint le menu. */}
            {/*
              `bg-salon` et non `salon-gradient` sur la pastille active.

              Mesuré : sur une pastille de 34 × 24 px, le dégradé à 135°
              parcourt presque toute sa course, et son extrémité claire —
              rgb(237, 209, 219) — ne donne que 1,42:1 au blanc posé dessus.
              Sur un bouton large le dégradé reste sombre sous le texte ; sur
              une pastille, non. L'aplat de marque donne 5,6:1 d'un bord à
              l'autre.
            */}
            <SelecteurLangue
              className="hidden border-line bg-surface sm:inline-flex"
              classeActive="bg-salon text-white"
              classeInactive="text-muted hover:text-ink"
            />
            <ThemeToggle />

            <a
              href={appUrl}
              className="hidden whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium text-muted transition hover:bg-surface-hover hover:text-ink lg:inline-flex"
            >
              {c("seConnecter")}
            </a>

            <a
              href={`${appUrl}/inscription`}
              className="salon-gradient hidden whitespace-nowrap rounded-xl px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:brightness-110 sm:inline-flex"
            >
              {c("creerSalon")}
            </a>

            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              aria-expanded={open}
              aria-controls="menu-mobile"
              aria-label={open ? c("fermerMenu") : c("ouvrirMenu")}
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
                  {t(`nav.${link.cle}`)}
                </a>
              </li>
            ))}
          </ul>

          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3">
            <a
              href={`${appUrl}/inscription`}
              className="salon-gradient rounded-xl px-4 py-2.5 text-center text-sm font-semibold text-white"
            >
              {c("creerSalon")}
            </a>
            <a
              href={appUrl}
              className="rounded-xl border border-line px-4 py-2.5 text-center text-sm font-medium text-ink"
            >
              {c("seConnecter")}
            </a>
          </div>

          {/* La langue n'est dans la barre qu'à partir de 640 px : sous
              cette largeur, c'est ici qu'on la trouve. */}
          <div className="mt-3 border-t border-line pt-3 sm:hidden">
            <SelecteurLangue
              large
              className="border-line bg-surface"
              classeActive="bg-salon text-white"
              classeInactive="text-muted"
            />
          </div>
        </div>
      </div>
    </header>
  );
}
