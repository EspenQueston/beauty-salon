"use client";

/**
 * Où en est un rendez-vous, en une ligne.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi une barre plutôt qu'une pastille
 * ---------------------------------------------------------------------------
 *
 * Une pastille dit « confirmée ». Elle ne dit pas ce qui reste à faire, ni ce
 * qui a déjà été fait. À midi, avec quatre clientes dans le salon, la vraie
 * question n'est pas « quel est son statut » mais « où en est-on avec elle » —
 * et c'est une position sur un chemin, pas une étiquette.
 *
 * ---------------------------------------------------------------------------
 * Quatre étapes, pas sept
 * ---------------------------------------------------------------------------
 *
 * Le modèle compte sept statuts ; la barre n'en montre que le chemin normal :
 * réservé → payé → arrivée → terminé. Les issues anormales — annulée, absente
 * — ne sont pas des étapes en arrière sur ce chemin, ce sont des sorties. Les
 * y placer laisserait croire qu'on peut en revenir.
 *
 * La barre disparaît donc pour ces deux cas, remplacée par la mention seule.
 */

import { Icon } from "./icons";

type Step = { key: string; label: string; done: boolean; current: boolean };

/** Chemin normal d'un rendez-vous, du plus tôt au plus tard. */
const PATH = [
  "pending_payment",
  "requested",
  "confirmed",
  "checked_in",
  "completed",
];

const LABELS: Record<string, string> = {
  pending_payment: "Acompte",
  requested: "À valider",
  confirmed: "Confirmé",
  checked_in: "Arrivée",
  completed: "Terminé",
};

/** Statuts qui sortent du chemin : la barre n'a plus de sens. */
const OFF_PATH: Record<string, string> = {
  cancelled: "Annulée",
  no_show: "Absente",
};

export function BookingProgress({
  status,
  hasDeposit,
}: {
  status: string;
  /**
   * Sans acompte, l'étape de paiement n'existe pas pour ce rendez-vous :
   * l'afficher ferait croire à une étape sautée.
   */
  hasDeposit: boolean;
}) {
  const off = OFF_PATH[status];
  if (off) {
    return (
      <p className="mt-3 text-xs font-medium text-muted">
        {off} — le rendez-vous n&apos;ira pas plus loin.
      </p>
    );
  }

  const path = hasDeposit
    ? PATH
    : PATH.filter((key) => key !== "pending_payment");
  const position = path.indexOf(status);
  if (position < 0) return null;

  const steps: Step[] = path.map((key, index) => ({
    key,
    label: LABELS[key],
    done: index < position,
    current: index === position,
  }));

  return (
    <ol
      aria-label="Progression du rendez-vous"
      className="mt-3 flex items-center gap-1"
    >
      {steps.map((step, index) => (
        <li
          key={step.key}
          className="flex min-w-0 flex-1 items-center gap-1"
          aria-current={step.current ? "step" : undefined}
        >
          <span className="flex min-w-0 flex-col items-center gap-1">
            <span
              aria-hidden
              className={`flex size-5 shrink-0 items-center justify-center rounded-full text-[0.6rem] font-semibold transition ${
                step.done
                  ? "bg-salon text-white"
                  : step.current
                    ? "bg-salon text-white ring-4 ring-salon-soft"
                    : "bg-surface-muted text-subtle ring-1 ring-line"
              }`}
            >
              {step.done ? <Icon name="check" className="size-3" /> : index + 1}
            </span>
            <span
              className={`truncate text-[0.65rem] ${
                step.current ? "font-medium text-ink" : "text-subtle"
              }`}
            >
              {step.label}
            </span>
          </span>

          {/* Le trait relie deux étapes : il n'y en a pas après la dernière. */}
          {index < steps.length - 1 && (
            <span
              aria-hidden
              className={`-mt-4 h-0.5 flex-1 rounded-full transition ${
                step.done ? "bg-salon" : "bg-line"
              }`}
            />
          )}
        </li>
      ))}
    </ol>
  );
}
