"use client";

/**
 * L'invitation aux notifications, dans l'espace cliente.
 *
 * Même mécanique que celle du tableau de bord (`useRappelPush`) : jamais de
 * demande sans clic, un report qui s'allonge, rien quand il n'y a rien à
 * proposer. Ce qui change : le chemin des appels (session cliente, en-tête
 * X-Tenant-Host), la portée « cliente », et les couleurs — celles du salon.
 *
 * Ce qu'elle promet est exactement ce que le serveur envoie
 * (`apps/notifications/cliente.py`) : confirmation, rappel de la veille,
 * changement d'horaire ou annulation par le salon.
 */

import { useCallback } from "react";
import { useTranslations } from "next-intl";

import { activerPush, etatPush, type Appel } from "@/features/dashboard/push";
import { SalonIcon } from "@/features/salon/icons";
import { useRappelPush } from "@/features/ui/useRappelPush";

import { api } from "./api";

export function RappelNotificationsCliente({ host }: { host: string }) {
  const t = useTranslations("espace.notifications");
  const appel = useCallback<Appel>(
    <T,>(chemin: string, init?: RequestInit) => api<T>(chemin, host, init),
    [host],
  );
  const lireEtat = useCallback(() => etatPush(undefined, appel), [appel]);
  const activer = useCallback(
    () => activerPush("cliente", undefined, appel),
    [appel],
  );
  const { etape, plusTard, accepter, fermer } = useRappelPush({
    cle: "beauty-salon.rappel-push.cliente",
    actif: Boolean(host),
    lireEtat,
    activer,
    delai: 3000,
  });

  if (!etape) return null;

  const bouton =
    "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition disabled:opacity-60";

  return (
    <div
      role="dialog"
      aria-labelledby="rappel-push-cliente"
      className="animate-toast-in fixed inset-x-0 bottom-0 z-50 rounded-t-3xl border border-[var(--site-line)] bg-[var(--site-surface)] p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-2xl sm:inset-x-auto sm:bottom-6 sm:right-6 sm:w-[23rem] sm:rounded-2xl"
    >
      <span
        aria-hidden
        className="mx-auto -mt-1 mb-3 block h-1 w-10 rounded-full bg-[var(--site-line)] sm:hidden"
      />

      {etape !== "active" && etape !== "refuse" && (
        <button
          type="button"
          onClick={plusTard}
          aria-label={t("plusTard")}
          className="absolute right-3 top-3 rounded-lg p-1.5 text-[var(--site-muted)] transition hover:text-[var(--site-ink)]"
        >
          <SalonIcon name="close" className="size-4" />
        </button>
      )}

      {etape === "active" ? (
        <div className="flex items-center gap-3" aria-live="polite">
          <span
            className="flex size-10 shrink-0 items-center justify-center rounded-xl"
            style={{
              background: "var(--salon-accent)",
              color: "var(--salon-ink-accent)",
            }}
          >
            <SalonIcon name="check" className="size-5" />
          </span>
          <div>
            <p
              id="rappel-push-cliente"
              className="text-sm font-semibold text-[var(--site-ink)]"
            >
              {t("activees")}
            </p>
            <p className="text-xs text-[var(--site-muted)]">
              {t("activeesCorps")}
            </p>
          </div>
        </div>
      ) : etape === "refuse" ? (
        <div>
          <p
            id="rappel-push-cliente"
            className="text-sm font-semibold text-[var(--site-ink)]"
          >
            {t("refuseTitre")}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-[var(--site-muted)]">
            {t("refuseCorps")}
          </p>
          <button
            type="button"
            onClick={fermer}
            className={`${bouton} mt-4 w-full border border-[var(--site-line)] text-[var(--site-ink)]`}
          >
            {t("compris")}
          </button>
        </div>
      ) : (
        <>
          <div className="flex items-start gap-3 pr-6">
            <span className="salon-gradient flex size-10 shrink-0 items-center justify-center rounded-xl text-white shadow-sm">
              <SalonIcon name="bell" className="size-5" />
            </span>
            <div className="min-w-0">
              <p
                id="rappel-push-cliente"
                className="text-[0.95rem] font-semibold leading-snug text-[var(--site-ink)]"
              >
                {t("titre")}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-[var(--site-muted)]">
                {etape === "ios" ? t("iosCorps") : t("corps")}
              </p>
            </div>
          </div>

          {etape === "ios" ? (
            <ol className="mt-4 space-y-2 text-xs text-[var(--site-ink)]">
              {(["ios1", "ios2", "ios3"] as const).map((cle, index) => (
                <li key={cle} className="flex gap-2.5">
                  <span className="tabular flex size-5 shrink-0 items-center justify-center rounded-full border border-[var(--site-line)] text-[0.68rem] font-semibold text-[var(--site-muted)]">
                    {index + 1}
                  </span>
                  <span className="leading-relaxed">{t(cle)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {(["point1", "point2", "point3"] as const).map((cle) => (
                <li
                  key={cle}
                  className="inline-flex items-center gap-1 rounded-full border border-[var(--site-line)] px-2.5 py-1 text-[0.7rem] font-medium text-[var(--site-ink)]"
                >
                  <SalonIcon name="check" className="size-3" />
                  {t(cle)}
                </li>
              ))}
            </ul>
          )}

          <div
            className={`mt-4 grid gap-2 ${etape === "ios" ? "grid-cols-1" : "grid-cols-2"}`}
          >
            <button
              type="button"
              onClick={plusTard}
              className={`${bouton} border border-[var(--site-line)] text-[var(--site-ink)] hover:bg-[var(--site-line)]/30`}
            >
              {etape === "ios" ? t("compris") : t("plusTard")}
            </button>
            {etape !== "ios" && (
              <button
                type="button"
                onClick={accepter}
                disabled={etape === "occupe"}
                className={`${bouton} salon-gradient text-white shadow-sm hover:brightness-110`}
              >
                <SalonIcon name="bell" className="size-4" />
                {etape === "occupe" ? "…" : t("activer")}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
