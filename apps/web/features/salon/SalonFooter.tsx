/**
 * Pied de page du mini-site.
 *
 * Il répète les coordonnées et les horaires plutôt que de renvoyer vers une
 * page. Quelqu'un qui a fini de lire est au bas de la page : lui demander de
 * remonter pour trouver un numéro, c'est perdre l'appel.
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

export function SalonFooter({ salon }: { salon: PublicSalon }) {
  const contacts = contactLinks(salon);
  const socials = socialLinks(salon);
  const maps = mapsHref(salon);

  return (
    <footer className="mt-20 border-t border-[var(--site-line)] bg-[var(--site-surface)]">
      <div className="mx-auto max-w-5xl px-4 py-14">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <div className="flex items-center gap-3">
              <SalonLogo
                logo={salon.logo}
                name={salon.name}
                className="size-11 text-base"
              />
              <div>
                <p className="font-semibold text-[var(--site-ink)]">{salon.name}</p>
                <p className="text-sm text-[var(--site-muted)]">
                  {[salon.city, SERVICE_MODES[salon.service_mode]]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </div>

            {salon.address && (
              <p className="mt-5 flex items-start gap-2 text-sm text-[var(--site-muted)]">
                <SalonIcon name="pin" className="mt-0.5 size-4 shrink-0" />
                <span>
                  {salon.address}
                  {salon.city && `, ${salon.city}`}
                  {maps && (
                    <>
                      {" — "}
                      <a
                        href={maps}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="font-medium text-[var(--salon-ink)] underline-offset-2 hover:underline"
                      >
                        itinéraire
                      </a>
                    </>
                  )}
                </span>
              </p>
            )}

            <ul className="mt-4 space-y-2">
              {contacts.map((contact) => (
                <li key={contact.key}>
                  <a
                    href={contact.href}
                    {...(contact.external
                      ? { target: "_blank", rel: "noreferrer noopener" }
                      : {})}
                    className="inline-flex items-center gap-2 text-sm text-[var(--site-muted)] transition hover:text-[var(--salon-ink)]"
                  >
                    <SalonIcon name={contact.icon} className="size-4" />
                    {contact.value}
                  </a>
                </li>
              ))}
            </ul>

            {socials.length > 0 && (
              <ul className="mt-5 flex flex-wrap gap-2">
                {socials.map((social) => (
                  <li key={social.key}>
                    <a
                      href={social.href}
                      target="_blank"
                      rel="noreferrer noopener"
                      aria-label={social.label}
                      className="flex size-10 items-center justify-center rounded-full border border-[var(--site-line)] text-[var(--site-muted)] transition hover:border-[var(--salon-primary)] hover:text-[var(--salon-ink)]"
                    >
                      <SalonIcon name={social.icon} className="size-4.5" />
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/*
            Les horaires ne sont plus répétés ici. Ils vivaient en double
            avec la page « Infos pratiques », et une grille de sept lignes
            au bas de chaque page poussait les liens hors de vue sur
            téléphone. Un seul endroit fait autorité.
          */}
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--site-subtle)]">
              Le salon
            </h2>
            <ul className="mt-3 space-y-2 text-sm">
              {[
                { href: "/prestations", label: "Prestations" },
                { href: "/realisations", label: "Réalisations" },
                { href: "/equipe", label: "L'équipe" },
              ].map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-[var(--site-muted)] underline-offset-4 transition hover:text-[var(--site-ink)] hover:underline"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--site-subtle)]">
              Pratique
            </h2>
            <ul className="mt-3 space-y-2 text-sm">
              {[
                ...(salon.about_content?.trim()
                  ? [{ href: "/a-propos", label: "À propos" }]
                  : []),
                { href: "/infos", label: "Infos pratiques" },
                { href: "/reserver", label: "Réserver" },
              ].map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-[var(--site-muted)] underline-offset-4 transition hover:text-[var(--site-ink)] hover:underline"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--site-line)] pt-6 text-sm text-[var(--site-subtle)]">
          <span>
            © {new Date().getFullYear()} {salon.name}
          </span>
          <a
            href={platformUrl}
            className="underline-offset-4 transition hover:text-[var(--site-muted)] hover:underline"
          >
            Propulsé par Beauty Salon
          </a>
        </div>
      </div>
    </footer>
  );
}
