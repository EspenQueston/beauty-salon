"use client";

/**
 * Le parrainage du salon, pour sa propriétaire.
 *
 * Tout ce qui compte est calculé par le serveur : le code, qui a été parrainé,
 * ce que chaque parrainage a rapporté, ce qui s'appliquera au prochain
 * paiement. L'écran se contente de le montrer, et de rendre le code facile à
 * transmettre — un code qu'on ne partage pas ne parraine personne.
 *
 * Du salon filleul, on ne montre que son nom public, l'état du parrainage et
 * sa date : ce que le serveur en envoie, rien de plus.
 */

import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";
// Les liens portent la langue (/en/…) : sans elle, chaque clic en anglais
// passerait par une redirection.
import { Lien as Link } from "@/features/ui/Lien";

import { Badge, Card, EmptyState, ErrorState, GhostButton, PageHeader, Skeleton } from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { useDashboard } from "./DashboardShell";
import { useFormats } from "./formats";
import { Icon } from "./icons";
import { useResource } from "./useResource";
import { ParrainageClients } from "./ParrainageClients";

// ---------------------------------------------------------------------------
// Formes de l'API
// ---------------------------------------------------------------------------

type StatutFilleul = "en_verification" | "admissible" | "non_retenu";
type StatutRemise = "en_attente" | "suspendue" | "disponible" | "reservee" | "utilisee" | "expiree" | "annulee";

export interface Filleul {
  nom: string;
  statut: StatutFilleul;
  date: string;
  admissible_le: string | null;
}

export interface RemiseParrainage {
  id: string;
  pourcentage: string;
  statut: StatutRemise;
  declencheur: "inscription" | "paiement";
  filleul: string;
  cree_le: string;
  expire_le: string | null;
  utilisee_le: string | null;
  montant_deduit: string | null;
  devise: string;
  origine: "salon" | "compte";
}

export interface Regles {
  pourcentage: string;
  plafond: string;
  validite_mois: number | null;
  validite_jours?: number;
  configure?: boolean;
  cooling_mode?: string;
  delai_jours: number | null;
  recompenses_paiement_max: number;
}

interface ParrainageSalon {
  actif: boolean;
  code?: string;
  lien?: string;
  regles?: Regles;
  filleuls?: Filleul[];
  remises?: RemiseParrainage[];
  resume?: { pourcentage_prochain_paiement: string; remises_prochain_paiement: number };
}

/** Le ton de chaque statut ; libellés sous `pro.parrainage.statutFilleul` et `.statutRemise`. */
export const STATUT_FILLEUL: Record<StatutFilleul, "warning" | "success" | "neutral"> = {
  en_verification: "warning",
  admissible: "success",
  non_retenu: "neutral",
};

export const STATUT_REMISE: Record<StatutRemise, "success" | "warning" | "neutral" | "danger"> = {
  en_attente: "warning",
  suspendue: "warning",
  disponible: "success",
  reservee: "warning",
  utilisee: "neutral",
  expiree: "neutral",
  annulee: "danger",
};

// ---------------------------------------------------------------------------
// La page
// ---------------------------------------------------------------------------

export function Parrainage() {
  const t = useTranslations("pro.parrainage");
  const { pourcent } = useFormats();
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const { data, error } = useResource<ParrainageSalon>("/api/v1/parrainage", tenantId, {
    enabled: membership.role === "owner",
  });

  const entete = (
    <PageHeader
      title={t("titre")}
      description={t("description")}
    />
  );

  if (membership.role !== "owner") {
    return (
      <>
        {entete}
        <EmptyState title={t("reserve.titre")}>{t("reserve.corps")}</EmptyState>
      </>
    );
  }
  if (error) {
    return (
      <>
        {entete}
        <ErrorState>{t("erreur")}</ErrorState>
      </>
    );
  }
  if (data === null) {
    return (
      <>
        {entete}
        <Skeleton rows={3} />
      </>
    );
  }
  if (!data.actif || !data.code || !data.lien || !data.regles) {
    return (
      <>
        {entete}
        <EmptyState title={t("pause.titre")}>{t("pause.corps")}</EmptyState>
      </>
    );
  }

  const filleuls = data.filleuls ?? [];
  const remises = data.remises ?? [];
  const disponibles = remises.filter((r) => r.statut === "disponible").length;
  const valides = filleuls.filter((f) => f.statut === "admissible").length;
  const prochain = data.resume?.pourcentage_prochain_paiement ?? "0";

  return (
    <>
      {entete}

      <ParrainageClients tenantId={tenantId} devise={membership.tenant.currency} />
      <h2 className="mb-3 text-base font-semibold text-ink">{t("versSalon")}</h2>
      <PartageCode code={data.code} lien={data.lien} regles={data.regles} />

      <dl className="mb-6 grid grid-cols-2 gap-2.5 sm:mb-8 sm:grid-cols-4 sm:gap-4">
        <Chiffre terme={t("chiffres.parraines")} valeur={filleuls.length} />
        <Chiffre terme={t("chiffres.valides")} valeur={valides} />
        <Chiffre terme={t("chiffres.disponibles")} valeur={disponibles} />
        <Chiffre
          terme={t("chiffres.prochain")}
          valeur={Number(prochain) > 0 ? pourcent(prochain, "−") : "—"}
          accent={Number(prochain) > 0}
        />
      </dl>

      {Number(prochain) > 0 && (
        <p className="mb-6 flex items-start gap-2 rounded-xl bg-success-bg px-3 py-2.5 text-[12.5px] leading-relaxed text-success sm:mb-8 sm:text-sm">
          <Icon name="gift" className="mt-0.5 size-4 shrink-0" />
          <span>
            {t("reduction", { pct: prochain })}{" "}
            <Link href="/abonnement" className="font-medium underline underline-offset-2">
              {t("voirAbonnement")}
            </Link>
          </span>
        </p>
      )}

      <div className="grid min-w-0 gap-6 lg:grid-cols-2 lg:gap-8">
        <section className="min-w-0">
          <Titre>{t("chiffres.parraines")}</Titre>
          <ListeFilleuls filleuls={filleuls} />
        </section>
        <section className="min-w-0">
          <Titre>{t("vosRemises")}</Titre>
          <ListeRemises remises={remises} />
        </section>
      </div>

      <Regles regles={data.regles} salon />
    </>
  );
}

// ---------------------------------------------------------------------------
// Le code, et comment le transmettre
// ---------------------------------------------------------------------------

export function PartageCode({
  code,
  lien,
  regles,
}: {
  code: string;
  lien: string;
  regles: Regles;
}) {
  // Lu au premier rendu : ce bloc n'apparaît qu'une fois les données chargées
  // dans le navigateur, jamais au rendu du serveur — pas d'écart d'hydratation.
  const t = useTranslations("pro.parrainage.partage");
  const [partageNatif] = useState(
    () => typeof navigator !== "undefined" && typeof navigator.share === "function",
  );

  const message = t("message", { code, lien });

  return (
    <Card className="mb-6 overflow-hidden sm:mb-8" padded={false}>
      <div className="salon-gradient px-4 py-4 text-white sm:px-6 sm:py-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/80 sm:text-xs">
          {t("votreCode")}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center justify-between gap-3">
          <span className="font-mono text-2xl font-bold tracking-[0.18em] sm:text-3xl">{code}</span>
          <span className="rounded-full bg-white/15 px-2.5 py-1 text-[11px] font-semibold sm:text-xs">
            {t("parSalon", { pct: regles.pourcentage })}
          </span>
        </div>
      </div>
      <div className="grid gap-3 p-4 sm:p-5">
        <div className="flex min-w-0 items-center gap-2 rounded-xl border border-line bg-surface-muted px-3 py-2">
          <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-muted sm:text-[13px]">
            {lien}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          <Copier texte={code} succes={t("codeCopie")} libelle={t("copierCode")} />
          <Copier texte={lien} succes={t("lienCopie")} libelle={t("copierLien")} />
          <a
            href={`https://wa.me/?text=${encodeURIComponent(message)}`}
            target="_blank"
            rel="noopener noreferrer"
            // Seul sur sa ligne sans partage natif : il la prend en entier.
            className={`inline-flex items-center justify-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-ink transition hover:bg-surface-hover ${
              partageNatif ? "" : "col-span-2 sm:col-span-1"
            }`}
          >
            <Icon name="chat" className="size-4" />
            WhatsApp
          </a>
          {partageNatif && (
            <GhostButton
              type="button"
              icon={<Icon name="share" className="size-4" />}
              onClick={() => {
                navigator.share({ title: "Beauty Salon", text: message, url: lien }).catch(() => {
                  /* partage annulé : rien à dire */
                });
              }}
            >
              {t("partager")}
            </GhostButton>
          )}
        </div>
      </div>
    </Card>
  );
}

function Copier({ texte, succes, libelle }: { texte: string; succes: string; libelle: string }) {
  const t = useTranslations("pro.parrainage.partage");
  const toast = useToast();
  const [copie, setCopie] = useState(false);

  useEffect(() => {
    if (!copie) return;
    const minuterie = window.setTimeout(() => setCopie(false), 1800);
    return () => window.clearTimeout(minuterie);
  }, [copie]);

  return (
    <GhostButton
      type="button"
      className="justify-center"
      icon={<Icon name={copie ? "check" : "copy"} className="size-4" />}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(texte);
          setCopie(true);
          toast.success(succes);
        } catch {
          toast.error(t("copieImpossible"));
        }
      }}
    >
      {copie ? t("copie") : libelle}
    </GhostButton>
  );
}

// ---------------------------------------------------------------------------
// Listes
// ---------------------------------------------------------------------------

function Chiffre({
  terme,
  valeur,
  accent = false,
}: {
  terme: string;
  valeur: ReactNode;
  accent?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-2xl border border-line bg-surface px-3 py-3 sm:px-4 sm:py-4">
      <dt className="truncate text-[10.5px] uppercase tracking-wide text-subtle sm:text-xs">{terme}</dt>
      <dd
        className={`tabular mt-1 text-xl font-bold tracking-tight sm:text-2xl ${accent ? "text-success" : "text-ink"}`}
      >
        {valeur}
      </dd>
    </div>
  );
}

function Titre({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 text-sm font-semibold text-ink sm:text-base">{children}</h2>;
}

export function ListeFilleuls({ filleuls }: { filleuls: Filleul[] }) {
  const t = useTranslations("pro.parrainage");
  const { dateLongue } = useFormats();
  if (filleuls.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-line-strong px-4 py-6 text-center text-[13px] text-muted sm:text-sm">
        {t("aucunFilleul")}
      </p>
    );
  }
  return (
    <ul className="grid gap-2">
      {filleuls.map((filleul, index) => {
        const ton = STATUT_FILLEUL[filleul.statut] ?? "neutral";
        return (
          <li
            key={`${filleul.nom}-${filleul.date}-${index}`}
            className="flex min-w-0 items-center justify-between gap-3 rounded-xl border border-line bg-surface px-3 py-2.5 sm:px-4"
          >
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-medium text-ink sm:text-sm">
                {filleul.nom}
              </span>
              <span className="block text-[11px] text-subtle sm:text-xs">
                {t("inscritLe", { date: dateLongue.format(new Date(filleul.date)) })}
              </span>
            </span>
            <Badge tone={ton}>{t(`statutFilleul.${filleul.statut}`)}</Badge>
          </li>
        );
      })}
    </ul>
  );
}

export function ListeRemises({ remises }: { remises: RemiseParrainage[] }) {
  const t = useTranslations("pro.parrainage");
  const { dateLongue, montant, pourcent } = useFormats();
  if (remises.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-line-strong px-4 py-6 text-center text-[13px] text-muted sm:text-sm">
        {t("aucuneRemise")}
      </p>
    );
  }
  return (
    <ul className="grid grid-cols-2 gap-2 sm:gap-2.5">
      {remises.map((remise) => {
        const ton = STATUT_REMISE[remise.statut] ?? "neutral";
        return (
          <li key={remise.id} className="min-w-0 rounded-xl border border-line bg-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-1.5">
              <span className="tabular text-base font-bold text-ink sm:text-lg">
                {pourcent(remise.pourcentage, "−")}
              </span>
              <Badge tone={ton}>{t(`statutRemise.${remise.statut}`)}</Badge>
            </div>
            <p className="mt-1 truncate text-[11px] text-muted sm:text-xs" title={remise.filleul}>
              {remise.declencheur === "paiement"
                ? t("paiementDe", { nom: remise.filleul })
                : t("inscriptionDe", { nom: remise.filleul })}
            </p>
            <p className="mt-1 text-[10.5px] text-subtle sm:text-[11px]">
              {remise.statut === "utilisee" && remise.utilisee_le
                ? `${t("utiliseeLe", { date: dateLongue.format(new Date(remise.utilisee_le)) })}${
                    remise.montant_deduit && remise.devise
                      ? ` · ${montant(remise.montant_deduit, remise.devise)}`
                      : ""
                  }`
                : remise.statut === "disponible" || remise.statut === "reservee"
                  ? t("jusquAu", { date: dateLongue.format(new Date(remise.expire_le ?? remise.cree_le)) })
                  : t("creeeLe", { date: dateLongue.format(new Date(remise.cree_le)) })}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Les règles, dites simplement
// ---------------------------------------------------------------------------

export function Regles({ regles, salon }: { regles: Regles; salon: boolean }) {
  const t = useTranslations("pro.parrainage.regles");
  const etapes = [
    { titre: t("partager.titre"), texte: t("partager.texte") },
    { titre: t("valide.titre"), texte: t("valide.texte") },
    {
      titre: t("recevez.titre", { pct: regles.pourcentage }),
      texte: salon ? t("recevez.salon") : t("recevez.autre"),
    },
    {
      titre: t("auto.titre"),
      texte: regles.configure
        ? t("auto.texte", { jours: regles.validite_jours ?? 0 })
        : t("auto.nonConfigure"),
    },
  ];
  return (
    <section className="mt-8 sm:mt-10">
      <Titre>{t("titre")}</Titre>
      <ol className="grid grid-cols-2 gap-2.5 sm:gap-4 lg:grid-cols-4">
        {etapes.map((etape, index) => (
          <li key={etape.titre} className="min-w-0 rounded-2xl border border-line bg-surface p-3 sm:p-4">
            <span className="flex size-6 items-center justify-center rounded-full bg-salon text-xs font-semibold text-white">
              {index + 1}
            </span>
            <p className="mt-2 text-[13px] font-semibold text-ink sm:text-sm">{etape.titre}</p>
            <p className="mt-1 text-[11.5px] leading-relaxed text-muted sm:text-xs">{etape.texte}</p>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-[11.5px] leading-relaxed text-subtle sm:text-xs">
        {t("note")}
      </p>
    </section>
  );
}
