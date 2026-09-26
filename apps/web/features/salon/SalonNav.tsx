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

import { Lien } from "@/features/ui/Lien";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { SalonIcon } from "./icons";
import { SalonLogo } from "./SalonLogo";
import { DeviseToggle } from "./Devise";
import { useTranslations } from "next-intl";

import { SelecteurLangue } from "@/features/ui/SelecteurLangue";
import { decouper } from "@/i18n/langues";
import { SiteModeToggle } from "./SiteMode";
import type { MediaAsset, RubriqueMenu, SiteConfig } from "@/lib/types";

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
  /** L'ordre et la visibilité des rubriques (offre Pro) ; l'ordre d'origine sinon. */
  menu?: SiteConfig["menu"] | null;
  /** Le libellé du bouton de réservation choisi par le salon (offre Pro). */
  bouton?: string;
}

const RUBRIQUES: Record<RubriqueMenu, { href: string; cle: string; montre: keyof Props["show"] | null }> = {
  prestations: { href: "/prestations", cle: "prestations", montre: "prestations" },
  realisations: { href: "/realisations", cle: "realisations", montre: "realisations" },
  equipe: { href: "/equipe", cle: "equipe", montre: "equipe" },
  "a-propos": { href: "/a-propos", cle: "aPropos", montre: "apropos" },
  infos: { href: "/infos", cle: "infos", montre: null },
};
const ORDRE: RubriqueMenu[] = ["prestations", "realisations", "equipe", "a-propos", "infos"];

export function SalonNav({ name, slug, logo, show, menu, bouton }: Props) {
  const t = useTranslations("salon");
  const c = useTranslations("commun");
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

  // Une rubrique n'apparaît que si le salon la montre *et* qu'elle a du
  // contenu : masquée ou vide, on ne propose pas de lien.
  const links = (menu ?? ORDRE.map((cle) => ({ cle, visible: true })))
    .filter((entree) => entree.visible && entree.cle in RUBRIQUES)
    .map((entree) => RUBRIQUES[entree.cle])
    .filter((rubrique) => rubrique.montre === null || show[rubrique.montre])
    .map(({ href, cle }) => ({ href, cle }));

  /*
    Le chemin est comparé **sans son préfixe de langue**.

    `usePathname` rend l'adresse du navigateur, donc `/en/prestations` en
    anglais, alors que les liens s'écrivent `/prestations` — c'est `Lien`
    qui leur pose le préfixe. Sans `decouper`, aucune section n'aurait
    jamais été marquée comme courante sur la version anglaise.
  */
  const chemin = decouper(pathname).reste;
  const isCurrent = (href: string) =>
    href === "/" ? chemin === "/" : chemin.startsWith(href);

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
  // `chemin` et non `pathname` : l'accueil anglais est `/en`, et le menu y
  // restait opaque — une bande sombre la ou le francais posait le menu sur
  // la photo.
  const overlay = chemin === "/" && !scrolled;
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
        <Lien href="/" className="flex min-w-0 items-center gap-2.5">
          <SalonLogo logo={logo} name={name} className="size-9 text-sm" />
          {/* Sur téléphone, les réglages de droite ne laissaient au nom que
              deux pixels : le logo suffit à l'œil, le nom reste lu par les
              lecteurs d'écran (le logo est décoratif). */}
          <span className={`sr-only truncate font-semibold tracking-tight sm:not-sr-only ${strong}`}>
            {name}
          </span>
        </Lien>

        <nav aria-label={t("sections")} className="ml-auto hidden lg:block">
          <ul className="flex items-center gap-1">
            {links.map((link) => (
              <li key={link.href}>
                <Lien
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
                  {t(link.cle)}
                  {isCurrent(link.href) && (
                    <span
                      className="absolute inset-x-3 -bottom-0.5 h-0.5 rounded-full"
                      style={{
                        background: overlay ? "#fff" : "var(--salon-primary)",
                      }}
                    />
                  )}
                </Lien>
              </li>
            ))}
          </ul>
        </nav>

        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          {/*
            Le choix de lecture des prix, à côté du clair/sombre.

            Les deux répondent à la même sorte de question — « comment je
            veux lire cette page » — et se rangent donc ensemble. Fermé, le
            bouton n'occupe que trois caractères : cette barre compte déjà
            quatre éléments sur téléphone.
          */}
          {/*
            La langue, hors de la barre sous 640 px.

            Elle y compterait un sixième élément à côté du logo, du nom du
            salon, des prix, du clair/sombre, du compte et du menu — sur un
            écran de 360 px, c'est le nom du salon qui se serait tronqué
            pour lui faire place. Elle passe alors dans le menu, en pleine
            largeur, où elle se touche mieux qu'une pastille de 32 px.
          */}
          <SelecteurLangue
            className={`hidden sm:inline-flex ${
              overlay
                ? "border-white/30 bg-white/10"
                : "border-[var(--site-line)] bg-[var(--site-surface)]"
            }`}
            classeActive={
              overlay
                ? "bg-white/25 text-white"
                : "bg-[var(--salon-primary)] text-white"
            }
            classeInactive={
              overlay
                ? "text-white/70 hover:text-white"
                : "text-[var(--site-muted)] hover:text-[var(--site-ink)]"
            }
          />
          <DeviseToggle />
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
          <Lien
            href="/compte"
            aria-label={t("monEspace")}
            title={t("monEspace")}
            className={`inline-flex size-9 items-center justify-center rounded-full border transition ${
              overlay
                ? "border-white/30 bg-white/10 text-white hover:bg-white/20"
                : "border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-muted)] hover:text-[var(--site-ink)]"
            }`}
          >
            <SalonIcon name="user" className="size-4" />
          </Lien>

          <Lien
            href="/reserver"
            className="salon-gradient hidden items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:brightness-110 sm:inline-flex"
          >
            <SalonIcon name="calendar" className="size-4" />
            {bouton || c("reserver")}
          </Lien>

          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-controls="menu-salon"
            aria-label={open ? c("fermerMenu") : c("ouvrirMenu")}
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
          {[{ href: "/", cle: "accueil" }, ...links].map((link) => (
            <li key={link.href}>
              <Lien
                href={link.href}
                aria-current={isCurrent(link.href) ? "page" : undefined}
                className={`block rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  isCurrent(link.href)
                    ? "bg-[var(--salon-accent)] text-[var(--salon-ink-accent)]"
                    : "text-[var(--site-ink)] hover:bg-black/[0.03]"
                }`}
              >
                {t(link.cle)}
              </Lien>
            </li>
          ))}
        </ul>

        {/* La langue, en pleine largeur : sous 640 px elle n'est nulle
            part ailleurs, et deux cibles de la moitié de l'écran se
            touchent sans viser. */}
        <div className="mt-3 border-t border-[var(--site-line)] pt-3 sm:hidden">
          <SelecteurLangue
            large
            className="border-[var(--site-line)] bg-[var(--site-surface)]"
            classeActive="bg-[var(--salon-primary)] text-white"
            classeInactive="text-[var(--site-muted)]"
          />
        </div>

        <Lien
          href="/reserver"
          className="salon-gradient mt-3 flex items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold text-white sm:hidden"
        >
          <SalonIcon name="calendar" className="size-4" />
          {bouton || t("reserverRdv")}
        </Lien>
      </div>
    </header>
  );
}
