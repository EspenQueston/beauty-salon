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

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";

import { Badge, Card, EmptyState, ErrorState, GhostButton, PageHeader, Skeleton } from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { dateLongue, montant } from "./abonnement";
import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";
import { useResource } from "./useResource";

// ---------------------------------------------------------------------------
// Formes de l'API
// ---------------------------------------------------------------------------

type StatutFilleul = "en_verification" | "admissible" | "non_retenu";
type StatutRemise = "disponible" | "reservee" | "utilisee" | "expiree" | "annulee";

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
  expire_le: string;
  utilisee_le: string | null;
  montant_deduit: string | null;
  devise: string;
  origine: "salon" | "compte";
}

export interface Regles {
  pourcentage: string;
  plafond: string;
  validite_mois: number;
  delai_jours: number;
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

export const STATUT_FILLEUL: Record<StatutFilleul, { label: string; tone: "warning" | "success" | "neutral" }> = {
  en_verification: { label: "En vérification", tone: "warning" },
  admissible: { label: "Validé", tone: "success" },
  non_retenu: { label: "Non retenu", tone: "neutral" },
};

export const STATUT_REMISE: Record<
  StatutRemise,
  { label: string; tone: "success" | "warning" | "neutral" | "danger" }
> = {
  disponible: { label: "Disponible", tone: "success" },
  reservee: { label: "Réservée", tone: "warning" },
  utilisee: { label: "Utilisée", tone: "neutral" },
  expiree: { label: "Expirée", tone: "neutral" },
  annulee: { label: "Annulée", tone: "danger" },
};

// ---------------------------------------------------------------------------
// La page
// ---------------------------------------------------------------------------

export function Parrainage() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const { data, error } = useResource<ParrainageSalon>("/api/v1/parrainage", tenantId, {
    enabled: membership.role === "owner",
  });

  const entete = (
    <PageHeader
      title="Parrainage"
      description="Invitez un salon : il profite de 30 jours d'essai si le parrainage est éligible, et vous obtenez une remise sur votre abonnement après validation."
    />
  );

  if (membership.role !== "owner") {
    return (
      <>
        {entete}
        <EmptyState title="Réservé à la propriétaire du salon">
          Le parrainage touche à l&apos;abonnement : seule la propriétaire le consulte.
        </EmptyState>
      </>
    );
  }
  if (error) {
    return (
      <>
        {entete}
        <ErrorState>Impossible de charger votre parrainage. Réessayez dans un instant.</ErrorState>
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
        <EmptyState title="Le parrainage est en pause">
          Le programme de parrainage n&apos;est pas ouvert pour le moment. Vos remises déjà
          obtenues sont conservées.
        </EmptyState>
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

      <PartageCode code={data.code} lien={data.lien} regles={data.regles} />

      <dl className="mb-6 grid grid-cols-2 gap-2.5 sm:mb-8 sm:grid-cols-4 sm:gap-4">
        <Chiffre terme="Salons parrainés" valeur={filleuls.length} />
        <Chiffre terme="Validés" valeur={valides} />
        <Chiffre terme="Remises disponibles" valeur={disponibles} />
        <Chiffre
          terme="Prochain paiement"
          valeur={Number(prochain) > 0 ? `−${prochain} %` : "—"}
          accent={Number(prochain) > 0}
        />
      </dl>

      {Number(prochain) > 0 && (
        <p className="mb-6 flex items-start gap-2 rounded-xl bg-success-bg px-3 py-2.5 text-[12.5px] leading-relaxed text-success sm:mb-8 sm:text-sm">
          <Icon name="gift" className="mt-0.5 size-4 shrink-0" />
          <span>
            Votre prochain paiement d&apos;abonnement sera réduit de {prochain} %, automatiquement.{" "}
            <Link href="/abonnement" className="font-medium underline underline-offset-2">
              Voir mon abonnement
            </Link>
          </span>
        </p>
      )}

      <div className="grid min-w-0 gap-6 lg:grid-cols-2 lg:gap-8">
        <section className="min-w-0">
          <Titre>Salons parrainés</Titre>
          <ListeFilleuls filleuls={filleuls} />
        </section>
        <section className="min-w-0">
          <Titre>Vos remises</Titre>
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
  const [partageNatif] = useState(
    () => typeof navigator !== "undefined" && typeof navigator.share === "function",
  );

  const message = `Je gère mon salon avec Beauty Salon : réservations, rappels, mini-site. Inscrivez le vôtre avec mon code ${code} et profitez de 30 jours d'essai si le parrainage est éligible : ${lien}`;

  return (
    <Card className="mb-6 overflow-hidden sm:mb-8" padded={false}>
      <div className="salon-gradient px-4 py-4 text-white sm:px-6 sm:py-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/80 sm:text-xs">
          Votre code de parrainage
        </p>
        <div className="mt-1.5 flex flex-wrap items-center justify-between gap-3">
          <span className="font-mono text-2xl font-bold tracking-[0.18em] sm:text-3xl">{code}</span>
          <span className="rounded-full bg-white/15 px-2.5 py-1 text-[11px] font-semibold sm:text-xs">
            −{regles.pourcentage} % par salon validé
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
          <Copier texte={code} quoi="Code" libelle="Copier le code" />
          <Copier texte={lien} quoi="Lien" libelle="Copier le lien" />
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
              Partager
            </GhostButton>
          )}
        </div>
      </div>
    </Card>
  );
}

function Copier({ texte, quoi, libelle }: { texte: string; quoi: string; libelle: string }) {
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
          toast.success(`${quoi} copié.`);
        } catch {
          toast.error("Copie impossible : sélectionnez le texte à la main.");
        }
      }}
    >
      {copie ? "Copié" : libelle}
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
  if (filleuls.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-line-strong px-4 py-6 text-center text-[13px] text-muted sm:text-sm">
        Aucun salon parrainé pour l&apos;instant. Partagez votre code : il suffit que le salon le
        saisisse en s&apos;inscrivant.
      </p>
    );
  }
  return (
    <ul className="grid gap-2">
      {filleuls.map((filleul, index) => {
        const etat = STATUT_FILLEUL[filleul.statut];
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
                Inscrit le {dateLongue.format(new Date(filleul.date))}
              </span>
            </span>
            <Badge tone={etat.tone}>{etat.label}</Badge>
          </li>
        );
      })}
    </ul>
  );
}

export function ListeRemises({ remises }: { remises: RemiseParrainage[] }) {
  if (remises.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-line-strong px-4 py-6 text-center text-[13px] text-muted sm:text-sm">
        Pas encore de remise. Elle arrive quand un salon parrainé est validé.
      </p>
    );
  }
  return (
    <ul className="grid grid-cols-2 gap-2 sm:gap-2.5">
      {remises.map((remise) => {
        const etat = STATUT_REMISE[remise.statut];
        return (
          <li key={remise.id} className="min-w-0 rounded-xl border border-line bg-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-1.5">
              <span className="tabular text-base font-bold text-ink sm:text-lg">
                −{remise.pourcentage} %
              </span>
              <Badge tone={etat.tone}>{etat.label}</Badge>
            </div>
            <p className="mt-1 truncate text-[11px] text-muted sm:text-xs" title={remise.filleul}>
              {remise.declencheur === "paiement" ? "Paiement de " : "Inscription de "}
              {remise.filleul}
            </p>
            <p className="mt-1 text-[10.5px] text-subtle sm:text-[11px]">
              {remise.statut === "utilisee" && remise.utilisee_le
                ? `Utilisée le ${dateLongue.format(new Date(remise.utilisee_le))}${
                    remise.montant_deduit && remise.devise
                      ? ` · ${montant(remise.montant_deduit, remise.devise)}`
                      : ""
                  }`
                : remise.statut === "disponible" || remise.statut === "reservee"
                  ? `Jusqu'au ${dateLongue.format(new Date(remise.expire_le))}`
                  : `Créée le ${dateLongue.format(new Date(remise.cree_le))}`}
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
  const etapes = [
    {
      titre: "Partagez votre code",
      texte: "Le salon le saisit en s'inscrivant, ou suit votre lien. Un salon n'a qu'un parrain.",
    },
    {
      titre: "Le salon est validé",
      texte: `${regles.delai_jours} jours après sa mise en ligne, ou dès son premier paiement d'abonnement.`,
    },
    {
      titre: `Vous recevez −${regles.pourcentage} %`,
      texte: salon
        ? `Puis −${regles.pourcentage} % à chacun de ses paiements d'abonnement, ${regles.recompenses_paiement_max} fois au plus.`
        : "Une remise sur l'abonnement d'un salon que vous gérez.",
    },
    {
      titre: "Elle s'applique toute seule",
      texte: `Sur votre prochain paiement, ${regles.plafond} % au plus par paiement, valable ${regles.validite_mois} mois.`,
    },
  ];
  return (
    <section className="mt-8 sm:mt-10">
      <Titre>Comment ça marche</Titre>
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
        Une remise n&apos;est pas de l&apos;argent : elle ne se retire pas et ne se transfère pas.
        Un parrainage de soi-même, ou entre membres d&apos;un même salon, n&apos;est pas retenu.
      </p>
    </section>
  );
}
