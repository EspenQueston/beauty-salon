"use client";

/**
 * Le parrainage, côté cliente.
 *
 * Une cliente qui connaît un salon peut lui recommander Beauty Salon avec son
 * code. Si ce salon est validé, elle reçoit une remise sur l'abonnement d'un
 * salon qu'elle gère elle-même — jamais de l'argent. Tout est calculé par le
 * serveur ; d'un salon parrainé, on ne voit que son nom public et l'état du
 * parrainage.
 */

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { SalonIcon } from "@/features/salon/icons";
import { appUrl } from "@/lib/site";
import { api } from "./api";

interface Filleul {
  nom: string;
  statut: "en_verification" | "admissible" | "non_retenu";
  date: string;
}

interface Remise {
  id: string;
  pourcentage: string;
  statut: "disponible" | "reservee" | "utilisee" | "expiree" | "annulee";
  filleul: string;
  expire_le: string;
}

interface Donnees {
  actif: boolean;
  code?: string;
  lien?: string;
  regles?: { pourcentage: string; plafond: string; validite_mois: number; delai_jours: number };
  filleuls?: Filleul[];
  remises?: Remise[];
  possede_un_salon?: boolean;
}

const CARD =
  "rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-[0_1px_3px_rgb(23_23_28_/_0.06)]";
const BOUTON =
  "inline-flex items-center justify-center gap-1.5 rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] px-3 py-2 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]";

export function ParrainageCliente({ host }: { host: string }) {
  const t = useTranslations("espace.parrainage");
  const locale = useLocale();
  const [donnees, setDonnees] = useState<Donnees | null>(null);
  const [copie, setCopie] = useState<"code" | "lien" | null>(null);

  useEffect(() => {
    let annule = false;
    api<Donnees>("/api/v1/public/client/parrainage", host)
      .then((resultat) => !annule && setDonnees(resultat))
      .catch(() => !annule && setDonnees({ actif: false }));
    return () => {
      annule = true;
    };
  }, [host]);

  useEffect(() => {
    if (!copie) return;
    const minuterie = window.setTimeout(() => setCopie(null), 1800);
    return () => window.clearTimeout(minuterie);
  }, [copie]);

  // Programme fermé ou lecture impossible : la section n'apparaît pas.
  if (!donnees?.actif || !donnees.code || !donnees.lien || !donnees.regles) return null;

  const { code, lien, regles } = donnees;
  const filleuls = donnees.filleuls ?? [];
  const remises = donnees.remises ?? [];
  const disponibles = remises.filter((r) => r.statut === "disponible");
  const date = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const message = t("message", { code, lien });

  async function copier(texte: string, quoi: "code" | "lien") {
    try {
      await navigator.clipboard.writeText(texte);
      setCopie(quoi);
    } catch {
      /* presse-papiers refusé : le texte reste sélectionnable */
    }
  }

  return (
    <section className="mb-8" aria-labelledby="parrainage-titre">
      <div className={`${CARD} overflow-hidden`}>
        <div className="salon-gradient px-4 py-4 text-white sm:px-5">
          <h2 id="parrainage-titre" className="text-base font-semibold sm:text-lg">
            {t("titre")}
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-white/85 sm:text-sm">
            {t("accroche", { pourcentage: regles.pourcentage })}
          </p>
        </div>

        <div className="grid gap-3 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="select-all font-mono text-xl font-bold tracking-[0.16em] text-[var(--site-ink)] sm:text-2xl">
              {code}
            </span>
            <span className="text-xs text-[var(--site-subtle)]">{t("votreCode")}</span>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            <button type="button" className={BOUTON} onClick={() => void copier(code, "code")}>
              {copie === "code" && <SalonIcon name="check" className="size-4" />}
              {copie === "code" ? t("copie") : t("copierCode")}
            </button>
            <button type="button" className={BOUTON} onClick={() => void copier(lien, "lien")}>
              {copie === "lien" && <SalonIcon name="check" className="size-4" />}
              {copie === "lien" ? t("copie") : t("copierLien")}
            </button>
            <a
              href={`https://wa.me/?text=${encodeURIComponent(message)}`}
              target="_blank"
              rel="noopener noreferrer"
              className={`${BOUTON} col-span-2 sm:col-span-1`}
            >
              <SalonIcon name="whatsapp" className="size-4" />
              {t("whatsapp")}
            </a>
          </div>

          <dl className="grid grid-cols-2 gap-2.5">
            <div className="rounded-xl bg-[var(--site-bg,transparent)] px-3 py-2 ring-1 ring-[var(--site-line)]">
              <dt className="text-xs text-[var(--site-subtle)]">{t("salonsParraines")}</dt>
              <dd className="tabular mt-0.5 text-xl font-semibold text-[var(--site-ink)]">
                {filleuls.length}
              </dd>
            </div>
            <div className="rounded-xl bg-[var(--site-bg,transparent)] px-3 py-2 ring-1 ring-[var(--site-line)]">
              <dt className="text-xs text-[var(--site-subtle)]">{t("remisesDisponibles")}</dt>
              <dd className="tabular mt-0.5 text-xl font-semibold text-[var(--salon-ink)]">
                {disponibles.length}
              </dd>
            </div>
          </dl>

          {filleuls.length > 0 && (
            <ul className="grid gap-1.5">
              {filleuls.map((filleul, index) => (
                <li
                  key={`${filleul.nom}-${index}`}
                  className="flex min-w-0 items-center justify-between gap-3 text-sm"
                >
                  <span className="min-w-0 truncate text-[var(--site-ink)]">{filleul.nom}</span>
                  <span className="shrink-0 text-xs text-[var(--site-muted)]">
                    {t(`statut.${filleul.statut}`)} · {date.format(new Date(filleul.date))}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {disponibles.length > 0 && (
            <p className="rounded-xl bg-[var(--salon-primary)]/10 px-3 py-2 text-[13px] leading-relaxed text-[var(--site-ink)]">
              {donnees.possede_un_salon ? (
                <>
                  {t("utiliserSalon")}{" "}
                  <a href={`${appUrl}/abonnement`} className="font-medium underline underline-offset-2">
                    {t("monAbonnement")}
                  </a>
                </>
              ) : (
                t("utiliserSansSalon")
              )}
            </p>
          )}

          <p className="text-xs leading-relaxed text-[var(--site-subtle)]">
            {t("regles", {
              delai: regles.delai_jours,
              plafond: regles.plafond,
              mois: regles.validite_mois,
            })}
          </p>
        </div>
      </div>
    </section>
  );
}
