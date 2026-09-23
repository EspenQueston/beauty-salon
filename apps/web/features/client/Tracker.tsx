"use client";

/**
 * Le suivi d'un rendez-vous, vu par la cliente.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'une pastille de statut ne dit pas
 * ---------------------------------------------------------------------------
 *
 * L'espace affichait « Confirmé » et s'arrêtait là. Le mot est juste, mais il
 * répond à « où en suis-je » sans répondre à « et après ». Une cliente qui
 * vient de régler son acompte ne sait pas si le salon doit encore valider ;
 * une cliente confirmée ne sait pas qu'on lui demandera un code en arrivant.
 *
 * Le chemin complet règle les deux d'un coup : on voit d'où l'on vient, où
 * l'on est, et ce qui reste. C'est exactement ce que fait un suivi de colis,
 * et pour la même raison — l'attente se supporte quand elle est située.
 *
 * ---------------------------------------------------------------------------
 * Le chemin dépend du rendez-vous, pas du modèle de données
 * ---------------------------------------------------------------------------
 *
 * Un rendez-vous sans acompte n'a pas d'étape « acompte » : l'afficher
 * barrée ou grisée ferait chercher une somme que personne ne réclame. Les
 * étapes sont donc construites à partir de *ce* rendez-vous.
 *
 * Une annulation n'est pas une étape du chemin : c'est une sortie de route.
 * Le chemin disparaît alors, remplacé par la raison — un parcours qui
 * s'arrête au milieu sans explication est pire que pas de parcours du tout.
 */

import { useTranslations } from "next-intl";
import type { ClientBooking } from "./types";
import { SalonIcon, type SalonIconName } from "@/features/salon/icons";

interface Step {
  key: string;
  label: string;
  icon: SalonIconName;
  /** Ce qui se passe à cette étape, en une ligne. Affiché sur l'étape en
   *  cours seulement : partout ailleurs, ce serait un mur de texte. */
  detail: string;
}

/** L'ordre réel des états d'un rendez-vous, du plus tôt au plus tard. */
const ORDER = [
  "pending_payment",
  "requested",
  "confirmed",
  "checked_in",
  "completed",
] as const;

export function Tracker({ booking }: { booking: ClientBooking }) {
  const t = useTranslations("espace");
  // Sortie de route : rien à suivre, tout à expliquer.
  if (booking.status === "cancelled" || booking.status === "no_show")
    return null;

  const steps: Step[] = [];

  // L'acompte n'est une étape que s'il en existe un. Un rendez-vous réglé sur
  // place n'a pas à porter une case que personne ne cochera.
  if (Number(booking.deposit_amount) > 0) {
    steps.push({
      key: "pending_payment",
      label: "Acompte",
      icon: "calendar",
      detail: t("suivi.acompteCorps"),
    });
    steps.push({
      key: "requested",
      label: t("suivi.aValider"),
      icon: "clock",
      detail: t("suivi.aValiderCorps"),
    });
  } else {
    steps.push({
      key: "requested",
      label: t("suivi.demande"),
      icon: "clock",
      detail: t("suivi.demandeCorps"),
    });
  }

  steps.push(
    {
      key: "confirmed",
      label: t("suivi.confirme"),
      icon: "check",
      detail: t("suivi.confirmeCorps"),
    },
    {
      key: "checked_in",
      label: t("suivi.arrivee"),
      icon: "store",
      detail: t("suivi.arriveeCorps"),
    },
    {
      key: "completed",
      label: t("suivi.termine"),
      icon: "sparkle",
      detail: t("suivi.termineCorps"),
    },
  );

  const rank = ORDER.indexOf(booking.status as (typeof ORDER)[number]);
  const current = Math.max(
    0,
    steps.findIndex(
      (step) => ORDER.indexOf(step.key as (typeof ORDER)[number]) >= rank,
    ),
  );
  const detail = steps[current]?.detail ?? "";

  return (
    <div>
      {/*
        Une rangée, jamais une colonne.

        Cinq étapes empilées prendraient la moitié d'un écran de téléphone
        pour une information qu'on lit en une seconde. En rangée, les libellés
        rapetissent mais restent lisibles, et le trait qui les relie se lit
        d'un coup d'œil — c'est lui qui porte le sens, pas les mots.
      */}
      <ol className="flex items-start">
        {steps.map((step, index) => {
          const done = index < current;
          const here = index === current;
          return (
            <li
              key={step.key}
              className="relative flex min-w-0 flex-1 flex-col items-center"
            >
              {/* Le trait relie les pastilles entre elles : il part de la
                  précédente, donc jamais devant la première. */}
              {index > 0 && (
                <span
                  aria-hidden
                  className={`absolute right-1/2 top-3.5 h-0.5 w-full sm:top-4 ${
                    done || here
                      ? "bg-[var(--salon-primary)]"
                      : "bg-[var(--site-line)]"
                  }`}
                />
              )}

              <span
                aria-hidden
                className={`relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full transition sm:size-8 ${
                  done
                    ? "bg-[var(--salon-primary)] text-white"
                    : here
                      ? // L'étape en cours est cerclée plutôt que pleine :
                        // pleine, elle se confondait avec les étapes franchies.
                        "bg-[var(--site-surface)] text-[var(--salon-ink)] ring-2 ring-[var(--salon-primary)]"
                      : "bg-[var(--site-line)] text-[var(--site-subtle)]"
                }`}
              >
                <SalonIcon
                  name={done ? "check" : step.icon}
                  className="size-3.5 sm:size-4"
                />
              </span>

              <span
                className={`mt-1.5 w-full truncate px-0.5 text-center text-[0.6rem] leading-tight sm:text-xs ${
                  here
                    ? "font-semibold text-[var(--site-ink)]"
                    : "text-[var(--site-subtle)]"
                }`}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>

      {/* Ce qui se passe maintenant, sous le chemin. C'est la phrase qui
          transforme un schéma en réponse. */}
      {detail && (
        <p className="mt-3 text-center text-xs leading-relaxed text-[var(--site-muted)] sm:text-sm">
          {detail}
        </p>
      )}
    </div>
  );
}
