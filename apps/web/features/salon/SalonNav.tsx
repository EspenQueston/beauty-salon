"use client";

/**
 * Barre de navigation du mini-site.
 *
 * Le mini-site tenait sur une seule page tant qu'il était vide. Avec un
 * catalogue, une équipe et des réalisations, ce défilement devient un mur :
 * une cliente qui cherche un prix ne doit pas traverser la galerie pour
 * l'atteindre. D'où de vraies pages, et cette barre pour y aller.
 *
 * Elle reste toujours visible, et « Réserver » y reste toujours accessible :
 * c'est la seule action qui compte, et elle ne doit jamais être à plus d'un
 * geste.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { SalonIcon } from "./icons";
import { SalonLogo } from "./SalonLogo";
import { SiteModeToggle } from "./SiteMode";
import type { MediaAsset } from "@/lib/types";

interface Props {
  name: string;
  /** Identifiant du salon : le mode clair/sombre est mémorisé par salon. */
  slug: string;
  logo: MediaAsset | null;
  /** Sections réellement remplies : on ne propose pas une page vide. */
  show: {
    prestations: boolean;
    realisations: boolean;
    equipe: boolean;
    apropos: boolean;
  };
}

export function SalonNav({ name, slug, logo, show }: Props) {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);

  /**
   * Le tiroir ne doit pas survivre à un changement de page.
   *
   * La remise à zéro se fait pendant le rendu, pas dans un effet : c'est le
   * motif recommandé par React pour ajuster un état quand une entrée change,
   * et il évite le rendu supplémentaire — donc l'aperçu du menu resté ouvert
   * une image de trop après la navigation.
   */
  const [drawer, setDrawer] = useState({ open: false, path: pathname });
  if (drawer.path !== pathname) setDrawer({ open: false, path: pathname });

  const open = drawer.open;
  const setOpen = (value: boolean | ((current: boolean) => boolean)) =>
    setDrawer((current) => ({
      path: current.path,
      open: typeof value === "function" ? value(current.open) : value,
    }));

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const links = [
    show.prestations && { href: "/prestations", label: "Prestations" },
    show.realisations && { href: "/realisations", label: "Réalisations" },
    show.equipe && { href: "/equipe", label: "L'équipe" },
    show.apropos && { href: "/a-propos", label: "À propos" },
    { href: "/infos", label: "Infos" },
  ].filter(Boolean) as { href: string; label: string }[];

  const isCurrent = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  /*
   * Sur l'accueil, le menu se pose sur la photo du haut de page plutôt que
   * de la surmonter d'une bande claire. Il devient opaque au premier
   * défilement, faute de quoi ses liens deviendraient illisibles dès qu'ils
   * passent sur le contenu.
   *
   * `fixed` partout, et non `sticky` sur l'accueil seulement : un élément
   * collant reste dans le flux, donc le haut de page ne pourrait pas passer
   * dessous. Une position identique d'une page à l'autre évite aussi le
   * saut de mise en page à la navigation.
   */
  const overlay = pathname === "/" && !scrolled;
  const strong = overlay ? "text-white" : "text-[var(--site-ink)]";

  return (
    <header
      className={`fixed inset-x-0 top-0 z-40 transition-all duration-300 ${
        overlay
          ? "border-b border-transparent"
          : "border-b border-[var(--site-line)] bg-[var(--site-surface)]/90 backdrop-blur-md"
      }`}
    >
      <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
        <Link href="/" className="flex min-w-0 items-center gap-2.5">
          <SalonLogo logo={logo} name={name} className="size-9 text-sm" />
          <span className={`truncate font-semibold tracking-tight ${strong}`}>
            {name}
          </span>
        </Link>

        <nav aria-label="Sections du salon" className="ml-auto hidden lg:block">
          <ul className="flex items-center gap-1">
            {links.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={isCurrent(link.href) ? "page" : undefined}
                  className={`relative rounded-lg px-3 py-2 text-sm font-medium transition ${
                    isCurrent(link.href)
                      ? overlay
                        ? "text-white"
                        : "text-[var(--salon-ink)]"
                      : overlay
                        ? "text-white/80 hover:bg-white/15 hover:text-white"
                        : "text-[var(--site-muted)] hover:text-[var(--site-ink)]"
                  }`}
                >
                  {link.label}
                  {isCurrent(link.href) && (
                    <span
                      className="absolute inset-x-3 -bottom-0.5 h-0.5 rounded-full"
                      style={{
                        background: overlay ? "#fff" : "var(--salon-primary)",
                      }}
                    />
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <SiteModeToggle
            slug={slug}
            className={
              overlay
                ? "border-white/30 bg-white/10 text-white hover:bg-white/20"
                : "border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-muted)] hover:text-[var(--site-ink)]"
            }
          />

          {/*
            L'espace cliente : une icône, pas un mot.

            Il n'entre pas dans la liste des sections du salon — ce n'est
            pas une page du salon, c'est la porte du compte — et il ne doit
            surtout pas concurrencer « Réserver », qui reste la seule action
            que la page cherche à obtenir.
          */}
          <Link
            href="/compte"
            aria-label="Mon espace"
            title="Mon espace"
            className={`inline-flex size-9 items-center justify-center rounded-full border transition ${
              overlay
                ? "border-white/30 bg-white/10 text-white hover:bg-white/20"
                : "border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-muted)] hover:text-[var(--site-ink)]"
            }`}
          >
            <SalonIcon name="user" className="size-4" />
          </Link>

          <Link
            href="/reserver"
            className="salon-gradient hidden items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:brightness-110 sm:inline-flex"
          >
            <SalonIcon name="calendar" className="size-4" />
            Réserver
          </Link>

          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-controls="menu-salon"
            aria-label={open ? "Fermer le menu" : "Ouvrir le menu"}
            className={`inline-flex size-9 items-center justify-center rounded-lg border transition lg:hidden ${
              overlay
                ? "border-white/30 bg-white/10 text-white hover:bg-white/20"
                : "border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-muted)] hover:text-[var(--site-ink)]"
            }`}
          >
            <SalonIcon name={open ? "close" : "menu"} className="size-5" />
          </button>
        </div>
      </div>

      {/* Le tiroir pousse la page au lieu de la recouvrir : on ne perd pas
          le paragraphe qu'on était en train de lire. */}
      <div
        id="menu-salon"
        hidden={!open}
        className="border-t border-[var(--site-line)] bg-[var(--site-surface)] px-4 py-3 lg:hidden"
      >
        <ul className="space-y-1">
          {[{ href: "/", label: "Accueil" }, ...links].map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                aria-current={isCurrent(link.href) ? "page" : undefined}
                className={`block rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  isCurrent(link.href)
                    ? "bg-[var(--salon-accent)] text-[var(--salon-ink)]"
                    : "text-[var(--site-ink)] hover:bg-black/[0.03]"
                }`}
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>

        <Link
          href="/reserver"
          className="salon-gradient mt-3 flex items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold text-white sm:hidden"
        >
          <SalonIcon name="calendar" className="size-4" />
          Réserver un rendez-vous
        </Link>
      </div>
    </header>
  );
}
