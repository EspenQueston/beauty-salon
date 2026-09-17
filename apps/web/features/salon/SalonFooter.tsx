/**
 * Pied de page du mini-site.
 *
 * Il répète les coordonnées plutôt que de renvoyer vers une page. Quelqu'un
 * qui a fini de lire est au bas de la page : lui demander de remonter pour
 * trouver un numéro, c'est perdre l'appel.
 *
 * ---------------------------------------------------------------------------
 * Le panneau
 * ---------------------------------------------------------------------------
 *
 * Le pied de page n'occupe plus toute la largeur de la fenêtre : c'est une
 * carte arrondie, détachée des bords, posée sur le fond de la page et
 * éclairée par en dessous d'un halo de la couleur du salon. La mention
 * légale, elle, sort de la carte et se centre en dessous.
 *
 * Ce n'est pas qu'une affaire de goût. Une bande pleine largeur se lit comme
 * la fin du document ; une carte se lit comme un dernier bloc de contenu —
 * et c'est exactement ce qu'elle contient, puisque les liens qui s'y
 * trouvent sont le seul moyen de repartir vers la réservation sans remonter.
 *
 * Le halo est composé en `color-mix` à partir de `--salon-primary` : il prend
 * donc la teinte choisie par le salon, et il fonctionne aussi bien sur la
 * surface claire que sur la sombre sans qu'on ait deux jeux de couleurs à
 * tenir.
 *
 * La mention de la plateforme reste discrète — c'est le salon qui reçoit,
 * pas nous.
 */

import Link from "next/link";

import { platformUrl } from "@/lib/site";
import type { PublicSalon } from "@/lib/types";
import { contactLinks, mapsHref, socialLinks, SERVICE_MODES } from "./contact";
import { SalonIcon } from "./icons";
import { SalonLogo } from "./SalonLogo";

interface Colonne {
  titre: string;
  liens: { href: string; label: string; external?: boolean }[];
}

export function SalonFooter({ salon }: { salon: PublicSalon }) {
  const contacts = contactLinks(salon);
  const socials = socialLinks(salon);
  const maps = mapsHref(salon);

  /*
    Les colonnes sont construites, pas écrites en dur.

    « Contact » n'existe que si le salon a laissé un numéro, et « À propos »
    que s'il a rédigé quelque chose. Un intitulé qui coiffe une liste vide
    donne l'impression d'un site à moitié installé — ce qui est justement
    l'état d'un salon dans ses premiers jours, au moment où il montre son
    site à ses clientes.
  */
  const colonnes: Colonne[] = [
    {
      titre: "Le salon",
      liens: [
        { href: "/prestations", label: "Prestations" },
        { href: "/realisations", label: "Réalisations" },
        { href: "/equipe", label: "L'équipe" },
      ],
    },
    {
      titre: "Pratique",
      liens: [
        ...(salon.about_content?.trim()
          ? [{ href: "/a-propos", label: "À propos" }]
          : []),
        { href: "/infos", label: "Infos pratiques" },
        { href: "/reserver", label: "Réserver" },
      ],
    },
  ];

  if (contacts.length > 0 || maps) {
    colonnes.push({
      titre: "Contact",
      liens: [
        ...contacts.map((contact) => ({
          href: contact.href,
          label: contact.value,
          external: contact.external,
        })),
        ...(maps ? [{ href: maps, label: "Itinéraire", external: true }] : []),
      ],
    });
  }

  // Deux classes littérales plutôt qu'une chaîne composée : Tailwind lit le
  // source, il ne voit pas les noms fabriqués à l'exécution.
  const grilleLiens = colonnes.length >= 3 ? "sm:grid-cols-3" : "sm:grid-cols-2";

  const sousTitre = [salon.city, SERVICE_MODES[salon.service_mode]]
    .filter(Boolean)
    .join(" · ");

  return (
    <footer className="mt-20 px-3 pb-8 sm:px-5 sm:pb-10">
      <div className="relative mx-auto max-w-6xl overflow-hidden rounded-3xl border border-[var(--site-line)] bg-[var(--site-surface)] px-5 py-10 sm:rounded-[2rem] sm:px-8 sm:py-12 lg:px-12">
        {/*
          Le halo, en deux foyers venus du bas.

          Un seul dégradé centré aurait fait une auréole symétrique, donc un
          motif ; deux foyers de tailles et d'intensités différentes font une
          lumière.
        */}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background: [
              "radial-gradient(75% 95% at 16% 112%, color-mix(in srgb, var(--salon-primary) 16%, transparent) 0%, transparent 62%)",
              "radial-gradient(55% 85% at 88% 118%, color-mix(in srgb, var(--salon-primary) 26%, transparent) 0%, transparent 60%)",
            ].join(", "),
          }}
        />

        <div className="relative grid gap-10 md:grid-cols-[minmax(0,1.05fr)_minmax(0,1.3fr)] md:gap-12 lg:gap-20">
          {/* ── L'enseigne ──────────────────────────────────────────── */}
          <div>
            <div className="flex items-center gap-3">
              <SalonLogo
                logo={salon.logo}
                name={salon.name}
                className="size-11 text-lg"
                rounded="rounded-full"
              />
              <div className="min-w-0">
                <p className="truncate text-lg font-semibold text-[var(--salon-ink)] sm:text-xl">
                  {salon.name}
                </p>
                {sousTitre && (
                  <p className="truncate text-xs text-[var(--site-subtle)] sm:text-sm">
                    {sousTitre}
                  </p>
                )}
              </div>
            </div>

            {salon.description && (
              <p className="mt-5 max-w-sm text-[0.82rem] leading-relaxed text-[var(--site-muted)] sm:text-sm">
                {salon.description}
              </p>
            )}

            {salon.address && (
              <p className="mt-4 flex max-w-sm items-start gap-2 text-[0.82rem] leading-relaxed text-[var(--site-muted)] sm:text-sm">
                <SalonIcon name="pin" className="mt-0.5 size-4 shrink-0" />
                <span>
                  {salon.address}
                  {salon.city && `, ${salon.city}`}
                </span>
              </p>
            )}

            {socials.length > 0 && (
              <ul className="mt-6 flex flex-wrap gap-2">
                {socials.map((social) => (
                  <li key={social.key}>
                    <a
                      href={social.href}
                      target="_blank"
                      rel="noreferrer noopener"
                      aria-label={social.label}
                      className="salon-social flex size-10 items-center justify-center rounded-xl"
                    >
                      <SalonIcon name={social.icon} className="size-4.5" />
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* ── Les colonnes de liens ───────────────────────────────── */}
          {/*
            Deux colonnes sur téléphone, trois dès 640 px. Empilées, les
            trois intitulés poussaient la mention légale à un écran et demi
            du dernier paragraphe de la page.
          */}
          <nav
            aria-label="Pied de page"
            className={`grid grid-cols-2 gap-x-6 gap-y-8 ${grilleLiens}`}
          >
            {colonnes.map((colonne) => (
              <div key={colonne.titre}>
                <h2 className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-[var(--salon-ink)]">
                  {colonne.titre}
                </h2>
                <ul className="mt-3.5 space-y-2.5 sm:mt-4 sm:space-y-3">
                  {colonne.liens.map((lien) => (
                    <li key={`${colonne.titre}-${lien.href}`}>
                      {lien.external ? (
                        <a
                          href={lien.href}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="inline-block text-[0.82rem] text-[var(--site-muted)] transition hover:translate-x-0.5 hover:text-[var(--salon-ink)] sm:text-[0.9rem]"
                        >
                          {lien.label}
                        </a>
                      ) : (
                        <Link
                          href={lien.href}
                          className="inline-block text-[0.82rem] text-[var(--site-muted)] transition hover:translate-x-0.5 hover:text-[var(--salon-ink)] sm:text-[0.9rem]"
                        >
                          {lien.label}
                        </Link>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>
      </div>

      {/* ── La mention légale, hors du panneau ─────────────────────── */}
      {/*
        `--site-muted` et non `--site-subtle` : sur la surface claire, la
        teinte discrète tombait à 3,17:1 — sous le seuil de lisibilité pour
        un texte de cette taille. La mention doit rester secondaire, pas
        devenir décorative.
      */}
      <div className="mt-6 flex flex-col items-center gap-1 text-center text-xs text-[var(--site-muted)] sm:flex-row sm:justify-center sm:gap-2 sm:text-[0.8rem]">
        <span>
          © {new Date().getFullYear()} {salon.name}. Tous droits réservés.
        </span>
        <span aria-hidden className="hidden opacity-45 sm:inline">
          ·
        </span>
        <a
          href={platformUrl}
          className="underline-offset-4 transition hover:text-[var(--site-muted)] hover:underline"
        >
          Propulsé par Beauty Salon
        </a>
      </div>
    </footer>
  );
}
