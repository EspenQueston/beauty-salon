"use client";

/**
 * L'invitation à activer les notifications, côté salon.
 *
 * Feuille ancrée en bas sur téléphone, à portée du pouce ; carte flottante
 * en bas à droite sur grand écran, sans voile : elle ne bloque rien, la
 * page reste utilisable derrière. Le moment, le report, et ce qu'elle ne
 * fait jamais sont décrits dans `useRappelPush`.
 */

import { useCallback } from "react";

import { Button, GhostButton } from "@/features/ui";
import { useRappelPush } from "@/features/ui/useRappelPush";

import { Icon } from "./icons";
import { activerPush, etatPush } from "./push";

const POINTS = ["Nouvelles réservations", "Annulations", "Acomptes à vérifier"];

export function RappelNotifications({ tenantId }: { tenantId: string }) {
  const lireEtat = useCallback(() => etatPush(tenantId), [tenantId]);
  const activer = useCallback(() => activerPush("salon", tenantId), [tenantId]);
  const { etape, plusTard, accepter, fermer } = useRappelPush({
    cle: "beauty-salon.rappel-push.salon",
    actif: Boolean(tenantId),
    lireEtat,
    activer,
  });

  if (!etape) return null;

  return (
    <div
      role="dialog"
      aria-labelledby="rappel-push-titre"
      className="animate-toast-in fixed inset-x-0 bottom-0 z-40 rounded-t-3xl border border-line bg-surface p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-float sm:inset-x-auto sm:bottom-6 sm:right-6 sm:w-[23rem] sm:rounded-2xl sm:p-5"
    >
      {/* La poignée dit « feuille » sur téléphone ; inutile ailleurs. */}
      <span
        aria-hidden
        className="mx-auto -mt-1 mb-3 block h-1 w-10 rounded-full bg-line sm:hidden"
      />

      {etape !== "active" && etape !== "refuse" && (
        <button
          type="button"
          onClick={plusTard}
          aria-label="Plus tard"
          className="absolute right-3 top-3 rounded-lg p-1.5 text-muted transition hover:bg-surface-hover hover:text-ink"
        >
          <Icon name="close" className="size-4" />
        </button>
      )}

      {etape === "active" ? (
        <div className="flex items-center gap-3" aria-live="polite">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-success-bg text-success">
            <Icon name="check" className="size-5" />
          </span>
          <div>
            <p
              id="rappel-push-titre"
              className="text-sm font-semibold text-ink"
            >
              Notifications activées
            </p>
            <p className="text-xs text-muted">
              Cet appareil sera prévenu à chaque nouvelle demande.
            </p>
          </div>
        </div>
      ) : etape === "refuse" ? (
        <div>
          <div className="flex items-start gap-3 pr-2">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-warning-bg text-warning">
              <Icon name="bell" className="size-5" />
            </span>
            <div className="min-w-0">
              <p
                id="rappel-push-titre"
                className="text-sm font-semibold text-ink"
              >
                Notifications bloquées
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                Cet appareil ne vous préviendra pas des nouvelles réservations.
                Pour les rouvrir : touchez le cadenas à gauche de
                l&apos;adresse, puis « Notifications » → « Autoriser », et
                rechargez la page.
              </p>
            </div>
          </div>
          <GhostButton type="button" onClick={fermer} className="mt-4 w-full">
            Compris
          </GhostButton>
        </div>
      ) : (
        <>
          <div className="flex items-start gap-3 pr-6">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-salon text-white shadow-sm">
              <Icon name="bell" className="size-5" />
            </span>
            <div className="min-w-0">
              <p
                id="rappel-push-titre"
                className="text-[0.95rem] font-semibold leading-snug text-ink"
              >
                Ne ratez plus aucun rendez-vous
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                {etape === "ios"
                  ? "Sur iPhone, les notifications arrivent une fois le tableau de bord ajouté à l'écran d'accueil."
                  : "Soyez prévenue à l'instant sur cet appareil, même l'application fermée."}
              </p>
            </div>
          </div>

          {etape === "ios" ? (
            <ol className="mt-4 space-y-2 text-xs text-ink">
              {[
                <>
                  Touchez <strong>Partager</strong> (le carré avec une flèche)
                  dans Safari.
                </>,
                <>
                  Choisissez{" "}
                  <strong>« Sur l&apos;écran d&apos;accueil »</strong>.
                </>,
                <>
                  Ouvrez le tableau de bord depuis la nouvelle icône : cette
                  invitation vous proposera d&apos;activer.
                </>,
              ].map((texte, index) => (
                <li key={index} className="flex gap-2.5">
                  <span className="tabular flex size-5 shrink-0 items-center justify-center rounded-full bg-surface-muted text-[0.68rem] font-semibold text-muted">
                    {index + 1}
                  </span>
                  <span className="leading-relaxed">{texte}</span>
                </li>
              ))}
            </ol>
          ) : (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {POINTS.map((point) => (
                <li
                  key={point}
                  className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-1 text-[0.7rem] font-medium text-ink"
                >
                  <Icon name="check" className="size-3 text-success" />
                  {point}
                </li>
              ))}
            </ul>
          )}

          <div
            className={`mt-4 grid gap-2 ${etape === "ios" ? "grid-cols-1" : "grid-cols-2"}`}
          >
            <GhostButton type="button" onClick={plusTard}>
              {etape === "ios" ? "J'ai compris" : "Plus tard"}
            </GhostButton>
            {etape !== "ios" && (
              <Button
                type="button"
                onClick={accepter}
                pending={etape === "occupe"}
                icon={<Icon name="bell" className="size-4" />}
              >
                Activer
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
