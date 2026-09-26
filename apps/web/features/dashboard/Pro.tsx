"use client";

/**
 * Ce que partagent les écrans de l'offre Pro.
 *
 * Un salon Standard voit ces écrans — c'est ainsi qu'il découvre ce que Pro
 * apporte — mais verrouillés : un bandeau dit pourquoi et mène à l'offre.
 * Le verrou de l'écran n'est qu'une politesse : le serveur refuse de toute
 * façon, en 403 « offre_pro_requise », ce que le salon n'a pas.
 */

import Link from "next/link";
import type { ReactNode } from "react";

import { useAcces } from "./AccessBanner";
import { FONCTIONS_PRO, type FonctionPro } from "./abonnement";
import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";

/** `null` tant que l'accès n'est pas lu : on n'affiche pas un verrou à tort. */
export function useFonction(fonction: FonctionPro): boolean | null {
  const { acces } = useAcces();
  if (!acces) return null;
  return Boolean(acces.fonctions?.[fonction]);
}

export function VerrouPro({
  fonction,
  children,
}: {
  fonction: FonctionPro;
  children?: ReactNode;
}) {
  const { membership } = useDashboard();
  const { acces } = useAcces();
  const proprietaire = membership.role === "owner";
  const enPause = acces?.groupe === "pro";

  return (
    <div className="relative mb-5 overflow-hidden rounded-2xl border border-line bg-ink p-4 text-surface sm:mb-6 sm:p-5">
      <div
        aria-hidden
        className="salon-gradient pointer-events-none absolute -right-20 -top-20 size-52 rounded-full opacity-40 blur-3xl"
      />
      <div className="relative flex flex-wrap items-center gap-3 sm:gap-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-surface/10">
          <Icon name="lock" className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold sm:text-base">
            {FONCTIONS_PRO[fonction].nom} fait partie de l&apos;offre Pro
          </p>
          <p className="mt-0.5 text-[12.5px] leading-relaxed opacity-75 sm:text-sm">
            {enPause
              ? "Cette fonction est momentanément fermée par l'équipe Beauty Salon."
              : (children ??
                `${FONCTIONS_PRO[fonction].resume} Vos réglages sont gardés : ils reprennent dès que Pro est actif.`)}
          </p>
        </div>
        {!enPause &&
          (proprietaire ? (
            <Link
              href="/abonnement#offres"
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-surface px-4 py-2 text-sm font-semibold text-ink shadow-sm transition hover:brightness-95 sm:w-auto"
            >
              <Icon name="crown" className="size-4" />
              Passer à Pro
            </Link>
          ) : (
            <span className="text-xs opacity-75">Parlez-en au propriétaire du salon.</span>
          ))}
      </div>
    </div>
  );
}

/** Un petit en-tête de carte : icône, titre, statut. */
export function EnteteCarte({
  icone,
  titre,
  detail,
  statut,
}: {
  icone: Parameters<typeof Icon>[0]["name"];
  titre: string;
  detail?: ReactNode;
  statut?: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-salon-soft text-salon sm:size-10">
        <Icon name={icone} className="size-4.5 sm:size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-[14px] font-semibold text-ink sm:text-base">{titre}</h2>
          {statut}
        </div>
        {detail && (
          <p className="mt-0.5 text-[12px] leading-relaxed text-muted sm:text-sm">{detail}</p>
        )}
      </div>
    </div>
  );
}
