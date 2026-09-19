/**
 * Primitives visuelles du mini-site.
 *
 * Elles sont volontairement distinctes du kit de l'espace professionnel :
 * ce dernier suit la charte du produit, celui-ci suit les couleurs choisies
 * par le salon. Les mélanger reviendrait à laisser une cliente déduire de la
 * couleur d'un bouton qu'elle est dans un outil de gestion.
 */

import Link from "next/link";
import type { ReactNode } from "react";

import { SalonIcon, type SalonIconName } from "./icons";

export const SURFACE =
  "rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] " +
  "shadow-[0_1px_3px_rgb(23_23_28_/_0.05)]";

export function Card({
  children,
  className = "",
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <div className={`${SURFACE} ${padded ? "p-5" : ""} ${className}`}>{children}</div>
  );
}

/**
 * Titre de section avec surtitre et lien facultatif.
 *
 * Le surtitre porte l'intention (« Ce que nous faisons »), le titre porte le
 * nom (« Prestations »). Une cliente qui parcourt la page en diagonale lit le
 * second ; celle qui hésite lit le premier.
 */
export function SectionTitle({
  eyebrow,
  title,
  id,
  action,
  center = false,
}: {
  eyebrow?: string;
  title: string;
  id?: string;
  action?: ReactNode;
  center?: boolean;
}) {
  return (
    <div
      className={`mb-6 flex flex-wrap items-end gap-4 ${
        center ? "flex-col items-center text-center" : "justify-between"
      }`}
    >
      <div>
        {/*
          La barre oblique devant le surtitre.

          Ce n'est pas un ornement : elle aligne verticalement tous les
          surtitres de la page, si bien qu'en parcourant du regard on repère
          les débuts de section sans lire un mot. Un surtitre sans repère se
          confond avec le premier paragraphe de la section précédente.
        */}
        {eyebrow && (
          <p className="mb-2 flex items-center gap-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[var(--salon-ink)]">
            <span aria-hidden className="opacity-45">
              /
            </span>
            {eyebrow}
          </p>
        )}
        <h2
          id={id}
          className="salon-titre text-2xl font-semibold uppercase tracking-tight sm:text-4xl"
        >
          {title}
        </h2>
      </div>
      {action}
    </div>
  );
}

/** Lien « voir tout » : discret, mais toujours au même endroit. */
export function MoreLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="group inline-flex items-center gap-1.5 rounded-full border border-[var(--site-line)] bg-[var(--site-surface)] px-4 py-2 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]"
    >
      {children}
      <SalonIcon
        name="arrow"
        className="size-4 transition-transform group-hover:translate-x-0.5"
      />
    </Link>
  );
}

export function PrimaryLink({
  href,
  icon,
  children,
  className = "",
  external = false,
}: {
  href: string;
  icon?: SalonIconName;
  children: ReactNode;
  className?: string;
  external?: boolean;
}) {
  const content = (
    <>
      {icon && <SalonIcon name={icon} className="size-4" />}
      {children}
    </>
  );
  const style =
    "salon-gradient inline-flex items-center justify-center gap-2 rounded-full " +
    `px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:brightness-110 ${className}`;

  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer noopener" className={style}>
        {content}
      </a>
    );
  }
  return (
    <Link href={href} className={style}>
      {content}
    </Link>
  );
}

/**
 * Bouton clair posé sur un aplat de marque.
 *
 * Il existe parce que la version inverse ne s'obtient pas en ajoutant des
 * utilitaires à `PrimaryLink` : `.salon-gradient` est déclarée hors couche
 * CSS, et la CSS sans couche l'emporte sur `@layer utilities`. Un
 * `bg-white bg-none` n'annulait donc pas le dégradé, et le texte passé en
 * couleur de marque devenait invisible sur le fond de marque.
 */
export function InverseLink({
  href,
  icon,
  children,
  className = "",
}: {
  href: string;
  icon?: SalonIconName;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center justify-center gap-2 rounded-full bg-white px-7 py-3.5 text-sm font-semibold text-[var(--salon-ink-white)] shadow-lg transition hover:-translate-y-0.5 hover:shadow-xl ${className}`}
    >
      {icon && <SalonIcon name={icon} className="size-4" />}
      {children}
    </Link>
  );
}

export function GhostLink({
  href,
  icon,
  children,
  external = false,
  className = "",
}: {
  href: string;
  icon?: SalonIconName;
  children: ReactNode;
  external?: boolean;
  className?: string;
}) {
  const style =
    "inline-flex items-center justify-center gap-2 rounded-full border " +
    "border-[var(--site-line)] bg-[var(--site-surface)] px-5 py-3 text-sm " +
    `font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)] ${className}`;

  const content = (
    <>
      {icon && <SalonIcon name={icon} className="size-4" />}
      {children}
    </>
  );

  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer noopener" className={style}>
        {content}
      </a>
    );
  }
  return (
    <Link href={href} className={style}>
      {content}
    </Link>
  );
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent";
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
        tone === "accent"
          ? "bg-[var(--salon-accent)] text-[var(--salon-ink-accent)]"
          : "bg-black/[0.04] text-[var(--site-muted)]"
      }`}
    >
      {children}
    </span>
  );
}

/** Message d'absence : il dit quoi faire, pas seulement qu'il n'y a rien. */
export function EmptyNote({
  icon,
  title,
  children,
}: {
  icon: SalonIconName;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-[var(--site-line)] px-6 py-12 text-center">
      <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-[var(--salon-accent)] text-[var(--salon-ink-accent)]">
        <SalonIcon name={icon} className="size-6" />
      </span>
      <p className="mt-4 font-medium text-[var(--site-ink)]">{title}</p>
      {children && (
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-[var(--site-muted)]">
          {children}
        </p>
      )}
    </div>
  );
}
