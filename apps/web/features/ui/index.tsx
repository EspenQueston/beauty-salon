"use client";

/**
 * Kit d'interface du produit.
 *
 * Toutes les surfaces de l'espace professionnel passent par ces composants.
 * L'intérêt n'est pas d'économiser des lignes : c'est qu'un bouton
 * destructeur, un champ en erreur ou un état vide se présentent de la même
 * façon d'un écran à l'autre, donc se reconnaissent sans être lus.
 */

import type { ButtonHTMLAttributes, ReactNode } from "react";

// ---------------------------------------------------------------------------
// Surfaces
// ---------------------------------------------------------------------------

export function Card({
  children,
  className = "",
  padded = true,
  id,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  /** Ancre, pour qu'une barre de sections puisse y renvoyer. */
  id?: string;
}) {
  return (
    <div
      id={id}
      // `scroll-mt` réserve la hauteur de la barre collante : sans lui, une
      // ancre place le titre de la carte *sous* la barre.
      className={`scroll-mt-24 rounded-2xl border border-line bg-surface shadow-card ${
        padded ? "p-5" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="mb-7 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && (
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">
            {description}
          </p>
        )}
      </div>
      {action && <div className="flex shrink-0 gap-2">{action}</div>}
    </header>
  );
}

export function SectionTitle({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
        {children}
      </h2>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Boutons
// ---------------------------------------------------------------------------

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  pending?: boolean;
  icon?: ReactNode;
};

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium " +
  "transition disabled:cursor-not-allowed disabled:opacity-55";

export function Button({ pending, icon, children, className = "", ...props }: ButtonProps) {
  return (
    <button
      {...props}
      disabled={props.disabled || pending}
      className={`${BASE} bg-salon px-4 py-2.5 text-white shadow-sm hover:brightness-110 active:brightness-95 ${className}`}
    >
      {pending ? <Spinner /> : icon}
      {children}
    </button>
  );
}

export function GhostButton({
  pending,
  icon,
  children,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={props.disabled || pending}
      className={`${BASE} border border-line bg-surface px-3.5 py-2 text-ink hover:bg-surface-hover ${className}`}
    >
      {pending ? <Spinner /> : icon}
      {children}
    </button>
  );
}

export function DangerButton({
  pending,
  icon,
  children,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={props.disabled || pending}
      className={`${BASE} border border-transparent bg-danger-bg px-3.5 py-2 text-danger hover:brightness-95 ${className}`}
    >
      {pending ? <Spinner /> : icon}
      {children}
    </button>
  );
}

function Spinner() {
  return (
    <svg viewBox="0 0 24 24" className="size-4 animate-spin" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" fill="none" opacity="0.25" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Formulaires
// ---------------------------------------------------------------------------

export const inputClass =
  "w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-ink " +
  "placeholder:text-subtle transition focus:border-salon";

export function Field({
  label,
  hint,
  error,
  children,
  className = "",
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint && !error && <span className="mt-1.5 block text-xs text-muted">{hint}</span>}
      {error && (
        <span className="mt-1.5 block text-xs font-medium text-danger">{error}</span>
      )}
    </label>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`mt-0.5 inline-flex h-6 w-10 shrink-0 items-center rounded-full transition ${
          checked ? "bg-salon" : "bg-line-strong"
        }`}
      >
        <span
          className={`size-4 rounded-full bg-white shadow-sm transition-transform ${
            checked ? "translate-x-5" : "translate-x-1"
          }`}
        />
      </button>
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </span>
    </label>
  );
}

// ---------------------------------------------------------------------------
// États
// ---------------------------------------------------------------------------

type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info" | "salon";

const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: "bg-surface-muted text-muted",
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
  info: "bg-info-bg text-info",
  salon: "bg-salon-soft text-salon",
};

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: BadgeTone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${BADGE_TONES[tone]}`}
    >
      {children}
    </span>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-line-strong bg-surface/60 px-6 py-12 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && (
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">
          {children}
        </p>
      )}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

/**
 * Squelette de chargement plutôt qu'un mot.
 *
 * Il garde la place que prendra le contenu : la page ne saute pas au moment
 * où les données arrivent.
 */
export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2.5" aria-hidden>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton h-16 rounded-2xl" />
      ))}
      <span className="sr-only">Chargement…</span>
    </div>
  );
}

export function ErrorState({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-line bg-danger-bg p-4">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        aria-hidden
        className="mt-0.5 size-5 shrink-0 text-danger"
      >
        <circle cx="12" cy="12" r="9" strokeWidth="2" />
        <path d="M12 7v6M12 16.5v.01" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
      <p className="text-sm text-ink">{children}</p>
    </div>
  );
}

export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: BadgeTone;
}) {
  return (
    <Card className="min-w-0">
      <p className="text-sm text-muted">{label}</p>
      <p
        className={`tabular mt-1.5 text-2xl font-semibold tracking-tight ${
          tone === "danger" ? "text-danger" : "text-ink"
        }`}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-subtle">{hint}</p>}
    </Card>
  );
}
