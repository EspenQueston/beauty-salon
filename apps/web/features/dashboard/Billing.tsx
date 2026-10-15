"use client";

import { KkiapayButton } from "./KkiapayButton";
import { SaspayButton, SaspayEnAttente } from "./SaspayButton";

/**
 * Abonnement du salon : l'état, le choix d'une offre, le règlement.
 *
 * ---------------------------------------------------------------------------
 * Ce que l'écran promet, et ce qu'il ne promet pas
 * ---------------------------------------------------------------------------
 *
 * Aucune passerelle n'est branchée : le propriétaire paie hors ligne (WeChat
 * Pay, Alipay, Mobile Money), puis déclare son paiement avec la référence de
 * la transaction. Un paiement déclaré est « en vérification », jamais
 * « payé », tant que l'équipe Beauty Salon ne l'a pas retrouvé sur le compte
 * crédité. Le montant affiché vient du serveur, qui le recalcule à l'envoi.
 *
 * ---------------------------------------------------------------------------
 * Pensé d'abord pour le téléphone
 * ---------------------------------------------------------------------------
 *
 * Un propriétaire de salon règle son abonnement depuis son téléphone, entre
 * deux clientes, l'application de paiement ouverte à côté. D'où :
 *
 *   - un état qui tient en une carte : l'anneau du temps restant, la date,
 *     et l'action du moment ;
 *   - tout en deux colonnes dès 360 px — offres, moyens, faits, historique —
 *     plutôt qu'une longue colonne qui repousse l'action sous la ligne de
 *     flottaison ;
 *   - le bouton d'envoi collé au bas de l'écran pendant qu'on remplit ;
 *   - le QR code à côté de ses instructions, pas au-dessus.
 *
 * Vivant : le compte à rebours avance chaque minute ; tant qu'un paiement
 * attend, l'écran relit l'abonnement toutes les vingt secondes et au retour
 * sur l'onglet — la validation apparaît d'elle-même.
 */

import { useTranslations } from "next-intl";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";

// Les liens portent la langue (/en/…) : sans elle, chaque clic en anglais
// passerait par une redirection.
import { Lien as Link } from "@/features/ui/Lien";

import { DashboardError, dashboardFetch } from "@/lib/dashboard";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  GhostButton,
  PageHeader,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import {
  ABONNEMENT_CHANGE,
  FONCTIONS_PRO,
  joursAvant,
  signalerAbonnement,
  type Acces,
  type FonctionPro,
  type Fonctions,
  type Groupe,
  type MonteeEnGamme,
} from "./abonnement";
import { useDashboard } from "./DashboardShell";
import { useFormats } from "./formats";
import { Icon } from "./icons";
import { rows, useResource, type Page } from "./useResource";

// ---------------------------------------------------------------------------
// Formes de l'API
// ---------------------------------------------------------------------------

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "salon";
type CodeOffre = "monthly" | "yearly" | "pro_monthly" | "pro_yearly";
const CODES: readonly string[] = ["monthly", "yearly", "pro_monthly", "pro_yearly"];

/** Ce que ferait un paiement, calculé par le serveur au moment de l'affichage. */
interface Effet {
  nature: "renouvellement" | "reprise" | "montee" | "descente";
  debut: string;
  fin: string;
  jours_credites: number;
}

interface ChangementProgramme {
  plan: { code: string; name: string; group: Groupe };
  debut: string;
  fin: string;
  montant: string;
  devise: string;
}

interface PaymentRequest {
  id: string;
  created_at: string;
  plan: { code: string; name: string };
  billing_months: number;
  country: string;
  currency: string;
  amount: string;
  /** Tarif avant remises de parrainage (absent sur les anciennes demandes). */
  montant_catalogue: string | null;
  remise_pourcentage: string;
  remise_montant: string;
  method_kind: "wechat" | "alipay" | "mobile_money" | "kkiapay" | "saspay";
  method_kind_label: string;
  method_label: string;
  method_account_number: string;
  method_account_holder: string;
  reference: string;
  proof_url: string;
  status: "pending" | "approved" | "rejected";
  status_label: string;
  rejection_reason: string;
  reviewed_at: string | null;
  period_start: string | null;
  period_end: string | null;
}

interface Subscription {
  id: string;
  plan: { code: string; name: string; description: string; billing_months: number };
  status: string;
  status_label: string;
  price_amount: string;
  currency: string;
  trial_ends_at: string | null;
  current_period_start: string;
  current_period_end: string;
  acces: Acces;
  demande_en_attente: PaymentRequest | null;
  montee_en_gamme: MonteeEnGamme | null;
  groupe: Groupe | null;
  fonctions: Fonctions;
  changement_programme: ChangementProgramme | null;
}

interface Moyen {
  id: string;
  kind: "wechat" | "alipay" | "mobile_money" | "kkiapay" | "saspay";
  kind_label: string;
  libelle: string;
  account_number: string;
  account_holder: string;
  instructions: string;
  qr_url: string;
}

interface OffrePlan {
  code: CodeOffre;
  groupe: Groupe;
  nom: string;
  description: string;
  mois: number;
  montant: string;
  /** Ce qu'il reste à verser, remises de parrainage déduites. */
  montant_final?: string;
  effet: Effet | null;
}

interface Economie {
  montant: string;
  pourcentage: number;
  douze_mois: string;
}

interface Devise {
  code: string;
  nom: string;
  plans: OffrePlan[];
  economie: Economie | null;
  economies?: Partial<Record<Groupe, Economie | null>>;
  moyens: Moyen[];
}

interface Pays {
  code: string;
  nom: string;
  devises: Devise[];
}

interface Offres {
  pays: Pays[];
  fonctions_pro: { code: FonctionPro; nom: string; description: string }[];
  groupe_actuel: string;
  suggestion: { pays: string; devise: string };
  remise_parrainage?: { pourcentage: string; nombre: number };
}

interface Invoice {
  id: string;
  number: string;
  label: string;
  amount: string;
  currency: string;
  status: "draft" | "issued" | "paid" | "void";
  issued_at: string;
  due_at: string;
  paid_at: string | null;
  payment_method: string;
  is_overdue: boolean;
}

/** Le ton de chaque statut ; libellés sous `pro.abonnement.statutDemande` et `.statutFacture`. */
const DEMANDE: Record<PaymentRequest["status"], Tone> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
};

const FACTURE: Record<string, Tone> = {
  draft: "neutral",
  issued: "warning",
  paid: "success",
  void: "neutral",
};

const FORMATS_PREUVE = ["image/jpeg", "image/png", "image/webp"];
const PREUVE_MAX = 15 * 1024 * 1024;
const RELECTURE_MS = 20_000;
const HORLOGE_MS = 60_000;

type Traduire = ReturnType<typeof useTranslations>;

/** Les offres connues (`Plan.Code`) ; le nom vient du catalogue, celui du serveur sinon. */
const PLANS_CONNUS = ["trial", "monthly", "yearly", "pro_monthly", "pro_yearly"];
const STATUTS_ABONNEMENT = [
  "trialing", "active", "expired", "pending_payment", "suspended", "past_due", "cancelled",
];

function nomPlan(t: Traduire, plan: { code: string; name: string }): string {
  return PLANS_CONNUS.includes(plan.code) ? t(`plans.${plan.code}`) : plan.name;
}

/** Descend jusqu'aux offres, en douceur, sous la barre du haut. */
function allerAuxOffres() {
  document.getElementById("offres")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------------------
// La page
// ---------------------------------------------------------------------------

export function Billing() {
  const t = useTranslations("pro.abonnement");
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const isOwner = membership.role === "owner";
  const toast = useToast();

  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [error, setError] = useState<"aucun" | "echec" | null>(null);
  const [token, setToken] = useState(0);
  const [maintenant, setMaintenant] = useState(() => Date.now());
  const [choixPlan, setChoixPlan] = useState<CodeOffre | null>(null);

  const offres = useResource<Offres>("/api/v1/subscription/offres", tenantId, {
    enabled: isOwner,
  });
  const paiements = useResource<PaymentRequest[]>(
    "/api/v1/subscription/paiements",
    tenantId,
    { enabled: isOwner },
  );
  const factures = useResource<Page<Invoice>>("/api/v1/invoices/", tenantId, {
    enabled: isOwner,
  });

  const { reload: reloadPaiements } = paiements;
  const { reload: reloadFactures } = factures;
  const relire = useCallback(() => {
    setToken((value) => value + 1);
    setMaintenant(Date.now());
    reloadPaiements();
    reloadFactures();
  }, [reloadPaiements, reloadFactures]);

  // La demande en attente, pour reconnaître le moment où elle est tranchée
  // et l'annoncer une fois.
  const attente = useRef<string | null>(null);

  useEffect(() => {
    if (!isOwner) return;
    let cancelled = false;

    dashboardFetch<Subscription>("/api/v1/subscription", {}, tenantId)
      .then((data) => {
        if (cancelled) return;
        const avant = attente.current;
        attente.current = data.demande_en_attente?.id ?? null;
        if (avant && !data.demande_en_attente) {
          if (data.acces.ouvert && data.status === "active") {
            toast.success(t("paiementValide"));
          } else {
            toast.info(t("paiementTraite"));
          }
          signalerAbonnement();
        }
        setSubscription(data);
        setError(null);
      })
      .catch((caught) => {
        if (cancelled) return;
        setError(caught instanceof DashboardError && caught.status === 404 ? "aucun" : "echec");
      });

    return () => {
      cancelled = true;
    };
  }, [tenantId, isOwner, token, toast, t]);

  // Relecture périodique tant qu'un paiement attend, et au retour sur
  // l'onglet — c'est là qu'on revient après avoir payé sur son téléphone.
  const enAttente = Boolean(subscription?.demande_en_attente);
  useEffect(() => {
    if (!isOwner) return;
    const auRetour = () => {
      if (document.visibilityState === "visible") relire();
    };
    document.addEventListener("visibilitychange", auRetour);
    window.addEventListener(ABONNEMENT_CHANGE, relire);
    const horloge = window.setInterval(() => setMaintenant(Date.now()), HORLOGE_MS);
    const minuterie = enAttente ? window.setInterval(relire, RELECTURE_MS) : undefined;
    return () => {
      document.removeEventListener("visibilitychange", auRetour);
      window.removeEventListener(ABONNEMENT_CHANGE, relire);
      window.clearInterval(horloge);
      if (minuterie) window.clearInterval(minuterie);
    };
  }, [isOwner, enAttente, relire]);

  // Arriver par « Passer à l'annuel » (barre du haut, e-mail) : on descend
  // jusqu'aux offres une fois la page chargée.
  const offresPretes = offres.data !== null && subscription !== null;
  useEffect(() => {
    if (offresPretes && window.location.hash === "#offres") {
      window.setTimeout(allerAuxOffres, 150);
    }
  }, [offresPretes]);

  if (!isOwner) {
    return (
      <section>
        <PageHeader title={t("titre")} />
        <EmptyState title={t("reserve.titre")}>{t("reserve.corps")}</EmptyState>
      </section>
    );
  }

  const planCourant = subscription?.plan.code;
  const plan: CodeOffre =
    choixPlan ?? (planCourant && CODES.includes(planCourant) ? (planCourant as CodeOffre) : "monthly");
  const proEnVente = Boolean(
    offres.data?.pays.some((pays) =>
      pays.devises.some((devise) => devise.plans.some((item) => item.groupe === "pro")),
    ),
  );

  return (
    <section>
      <PageHeader
        title={t("titre")}
        description={t("description")}
      />

      {error && <ErrorState>{error === "aucun" ? t("aucunAbonnement") : t("erreur")}</ErrorState>}
      {subscription === null && !error && <Skeleton rows={3} />}

      {subscription && (
        <>
          <Etat
            abonnement={subscription}
            maintenant={maintenant}
            onAgir={subscription.demande_en_attente ? undefined : allerAuxOffres}
          />

          {subscription.changement_programme && (
            <Programme changement={subscription.changement_programme} />
          )}

          {subscription.demande_en_attente ? (
            <PaiementEnAttente
              demande={subscription.demande_en_attente}
              tenantId={tenantId}
              onConfirme={() => {
                relire();
                signalerAbonnement();
              }}
            />
          ) : (
            <>
              {proEnVente &&
                subscription.plan.code !== "pro_monthly" &&
                subscription.plan.code !== "pro_yearly" &&
                !subscription.changement_programme &&
                !plan.startsWith("pro_") && (
                  <PasserAPro
                    fonctions={offres.data?.fonctions_pro ?? []}
                    onChoisir={() => {
                      setChoixPlan(plan === "yearly" ? "pro_yearly" : "pro_monthly");
                      allerAuxOffres();
                    }}
                  />
                )}
              {subscription.montee_en_gamme && plan !== subscription.montee_en_gamme.vers && (
                <PasserALAnnuel
                  proposition={subscription.montee_en_gamme}
                  finPeriode={subscription.acces.fin_periode}
                  onChoisir={() => {
                    setChoixPlan(subscription.montee_en_gamme?.vers ?? "yearly");
                    allerAuxOffres();
                  }}
                />
              )}
              <Commande
                offres={offres.data}
                erreur={offres.error}
                acces={subscription.acces}
                planCourant={planCourant}
                programme={subscription.changement_programme}
                plan={plan}
                onPlan={setChoixPlan}
                tenantId={tenantId}
                onEnvoye={() => {
                  relire();
                  signalerAbonnement();
                }}
                onTarifModifie={offres.reload}
              />
            </>
          )}
        </>
      )}

      <Suivi
        demandes={paiements.data}
        erreurDemandes={paiements.error}
        factures={factures.data}
        erreurFactures={factures.error}
      />

      <Questions />
    </section>
  );
}

// ---------------------------------------------------------------------------
// L'état : ce qui est ouvert, jusqu'à quand
// ---------------------------------------------------------------------------

function Etat({
  abonnement,
  maintenant,
  onAgir,
}: {
  abonnement: Subscription;
  maintenant: number;
  onAgir?: () => void;
}) {
  const t = useTranslations("pro.abonnement");
  const e = useTranslations("pro.abonnement.etat");
  const { dateLongue, montant } = useFormats();
  const { acces } = abonnement;
  const fin = acces.fin_periode ? dateLongue.format(new Date(acces.fin_periode)) : "—";
  const limite = acces.jusqu_au ? dateLongue.format(new Date(acces.jusqu_au)) : "";
  const jours = joursAvant(acces.fin_periode, maintenant);
  const joursGrace = joursAvant(acces.jusqu_au, maintenant);
  const unite = (n: number) => e("jours", { n });
  const gras = (texte: ReactNode) => <strong className="text-ink">{texte}</strong>;
  const nom = nomPlan(t, abonnement.plan);

  const debut = new Date(abonnement.current_period_start).getTime();
  const total = new Date(abonnement.current_period_end).getTime() - debut;
  const restant =
    total > 0 ? Math.min(1, Math.max(0, (new Date(abonnement.current_period_end).getTime() - maintenant) / total)) : 0;
  const payant = CODES.includes(abonnement.plan.code);
  const annuel = abonnement.plan.billing_months === 12;

  const vues: Record<
    Acces["raison"],
    {
      titre: string;
      detail: ReactNode;
      tone: Tone;
      badge: string;
      anneau: { valeur: string; unite: string; part: number } | null;
      action?: string;
    }
  > = {
    essai: {
      titre: e("essai.titre"),
      detail: e.rich("essai.detail", { date: fin, gras }),
      tone: "info",
      badge: e("essai.badge"),
      anneau: { valeur: String(jours), unite: unite(jours), part: restant },
      action: e("essai.action"),
    },
    periode: {
      titre: e("periode.titre", { offre: nom }),
      detail: e.rich("periode.detail", { date: fin, gras }),
      tone: "success",
      badge: e("periode.badge"),
      anneau: { valeur: String(jours), unite: unite(jours), part: restant },
      action: e("periode.action"),
    },
    grace: {
      titre: e("grace.titre"),
      detail: e.rich("grace.detail", { date: limite, gras }),
      tone: "warning",
      badge: e("grace.badge"),
      anneau: { valeur: String(joursGrace), unite: unite(joursGrace), part: joursGrace / 3 },
      action: e("grace.action"),
    },
    expire: {
      titre: e("expire.titre"),
      detail: e("expire.detail"),
      tone: "danger",
      badge: e("expire.badge"),
      anneau: null,
      action: e("expire.action"),
    },
    suspendu: {
      titre: e("suspendu.titre"),
      detail: e("suspendu.detail"),
      tone: "danger",
      badge: e("suspendu.badge"),
      anneau: null,
    },
    resilie: {
      titre: e("resilie.titre"),
      detail: e("resilie.detail"),
      tone: "neutral",
      badge: e("resilie.badge"),
      anneau: null,
    },
    sans_abonnement: {
      titre: e("sansAbonnement.titre"),
      detail: e("sansAbonnement.detail"),
      tone: "neutral",
      badge: "—",
      anneau: null,
    },
  };
  const vue = vues[acces.raison] ?? vues.sans_abonnement;
  const action = onAgir && vue.action ? vue.action : null;

  const faits: { terme: string; valeur: string }[] = [
    { terme: e("faits.offre"), valeur: nom },
    {
      terme: e("faits.statut"),
      valeur: STATUTS_ABONNEMENT.includes(abonnement.status)
        ? t(`statutAbonnement.${abonnement.status}`)
        : abonnement.status_label,
    },
    {
      terme: acces.raison === "essai" ? e("faits.finEssai") : e("faits.finPeriode"),
      valeur: fin,
    },
    {
      terme: e("faits.tarif"),
      valeur:
        payant && Number(abonnement.price_amount) > 0
          ? `${montant(abonnement.price_amount, abonnement.currency)} / ${annuel ? e("faits.an") : e("faits.mois")}`
          : e("faits.gratuit"),
    },
  ];

  return (
    <Card padded={false} className="relative mb-4 overflow-hidden sm:mb-6">
      <div aria-hidden className={`absolute inset-x-0 top-0 h-1 ${BANDES[vue.tone]}`} />

      <div className="flex items-center gap-3.5 p-4 sm:gap-6 sm:p-6">
        {vue.anneau ? (
          <Anneau {...vue.anneau} tone={vue.tone} />
        ) : (
          <span
            className={`flex size-16 shrink-0 items-center justify-center rounded-full sm:size-24 ${PASTILLES[vue.tone]}`}
          >
            <Icon name={vue.tone === "danger" ? "receipt" : "clock"} className="size-7 sm:size-9" />
          </span>
        )}

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={vue.tone}>{vue.badge}</Badge>
            {abonnement.groupe && <PastilleGroupe groupe={abonnement.groupe} />}
          </div>
          <p className="mt-1.5 text-[15px] font-semibold leading-snug text-ink sm:text-xl">
            {vue.titre}
          </p>
          <p className="mt-1 max-w-2xl text-[12.5px] leading-relaxed text-muted sm:text-sm">
            {vue.detail}
          </p>
        </div>

        {/* Enveloppé : `Button` pose son propre `inline-flex`, qui l'emporte
            sur un `hidden` passé en classe. */}
        {action && (
          <div className="hidden shrink-0 sm:block">
            <Button type="button" onClick={onAgir}>
              {action}
            </Button>
          </div>
        )}
      </div>

      <dl className="grid grid-cols-2 border-t border-line sm:grid-cols-4">
        {faits.map((fait, index) => (
          <div
            key={fait.terme}
            className={`min-w-0 px-4 py-2.5 sm:px-6 sm:py-3.5 ${
              index % 2 === 0 ? "border-r border-line" : ""
            } ${index < 2 ? "border-b border-line sm:border-b-0" : ""} ${
              index === 1 ? "sm:border-r" : ""
            }`}
          >
            <dt className="text-[10.5px] font-medium uppercase tracking-wide text-subtle sm:text-[11px]">
              {fait.terme}
            </dt>
            <dd className="mt-0.5 truncate text-[13px] font-semibold text-ink sm:text-sm">
              {fait.valeur}
            </dd>
          </div>
        ))}
      </dl>

      {action && (
        <div className="border-t border-line p-3 sm:hidden">
          <Button type="button" onClick={onAgir} className="w-full">
            {action}
          </Button>
        </div>
      )}
    </Card>
  );
}

const BANDES: Record<Tone, string> = {
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  neutral: "bg-line-strong",
  salon: "bg-salon",
};

const PASTILLES: Record<Tone, string> = {
  info: "bg-info-bg text-info",
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
  neutral: "bg-surface-muted text-muted",
  salon: "bg-salon-soft text-salon",
};

const TRAITS: Record<Tone, string> = {
  info: "text-info",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  neutral: "text-muted",
  salon: "text-salon",
};

/** L'anneau du temps restant : il se vide à mesure que l'échéance approche. */
function Anneau({
  valeur,
  unite,
  part,
  tone,
}: {
  valeur: string;
  unite: string;
  part: number;
  tone: Tone;
}) {
  const e = useTranslations("pro.abonnement.etat");
  const rayon = 42;
  const tour = 2 * Math.PI * rayon;
  const rempli = Math.max(0.04, Math.min(1, part));

  return (
    <div
      className="relative size-16 shrink-0 sm:size-24"
      role="img"
      aria-label={e("restants", { n: Number(valeur) })}
    >
      <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden>
        <circle cx="50" cy="50" r={rayon} fill="none" strokeWidth="8" className="stroke-surface-muted" />
        <circle
          cx="50"
          cy="50"
          r={rayon}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          stroke="currentColor"
          strokeDasharray={tour}
          strokeDashoffset={tour * (1 - rempli)}
          className={`${TRAITS[tone]} transition-[stroke-dashoffset] duration-700`}
        />
      </svg>
      <span className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className="tabular text-lg font-bold text-ink sm:text-3xl">{valeur}</span>
        <span className="mt-0.5 text-[9.5px] text-muted sm:text-[11px]">{unite}</span>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Standard et Pro
// ---------------------------------------------------------------------------

export function PastilleGroupe({ groupe }: { groupe: Groupe }) {
  return groupe === "pro" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-ink px-2 py-0.5 text-[10.5px] font-bold uppercase tracking-wide text-surface sm:text-[11px]">
      <Icon name="crown" className="size-3" />
      Pro
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full border border-line px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide text-muted sm:text-[11px]">
      Standard
    </span>
  );
}

/** Ce que Pro ajoute : la liste vient du serveur, qui n'annonce que ce qui est ouvert. */
function ListeFonctions({
  fonctions,
  compacte = false,
}: {
  fonctions: Offres["fonctions_pro"];
  compacte?: boolean;
}) {
  const f = useTranslations("pro.fonctionsPro");
  const connue = (code: string) => code in FONCTIONS_PRO;
  return (
    <ul className={`grid gap-1.5 ${compacte ? "grid-cols-2" : "grid-cols-2 lg:grid-cols-3"} sm:gap-2`}>
      {fonctions.map((fonction) => (
        <li key={fonction.code} className="flex min-w-0 items-start gap-1.5">
          <Icon name="check" className="mt-0.5 size-3.5 shrink-0 text-salon sm:size-4" />
          <span className="min-w-0">
            <span className="block text-[12px] font-medium leading-snug text-ink sm:text-[13px]">
              {connue(fonction.code) ? f(`${fonction.code}.nom`) : fonction.nom}
            </span>
            {!compacte && (
              <span className="block text-[11px] leading-snug text-muted sm:text-xs">
                {connue(fonction.code) ? f(`${fonction.code}.resume`) : fonction.description}
              </span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

function PasserAPro({
  fonctions,
  onChoisir,
}: {
  fonctions: Offres["fonctions_pro"];
  onChoisir: () => void;
}) {
  const t = useTranslations("pro.abonnement.pro");
  const f = useTranslations("pro.fonctionsPro");
  return (
    <div className="relative mb-4 overflow-hidden rounded-2xl border border-line bg-ink p-3.5 text-surface sm:mb-6 sm:p-5">
      <div
        aria-hidden
        className="salon-gradient pointer-events-none absolute -right-16 -top-16 size-44 rounded-full opacity-40 blur-2xl"
      />
      <div className="relative flex flex-wrap items-start gap-3 sm:gap-4">
        <span className="salon-gradient flex size-9 shrink-0 items-center justify-center rounded-full text-white sm:size-10">
          <Icon name="crown" className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold sm:text-base">{t("titre")}</p>
          <p className="mt-0.5 text-[12.5px] leading-relaxed opacity-75 sm:text-sm">
            {t("plus")}
          </p>
        </div>
        <div className="hidden shrink-0 sm:block">
          <button
            type="button"
            onClick={onChoisir}
            className="rounded-xl bg-surface px-4 py-2 text-sm font-semibold text-ink shadow-sm transition hover:brightness-95"
          >
            {t("decouvrir")}
          </button>
        </div>
      </div>
      {fonctions.length > 0 && (
        <ul className="relative mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3">
          {fonctions.map((fonction) => (
            <li key={fonction.code} className="flex min-w-0 items-center gap-1.5 text-[12px] sm:text-[13px]">
              <Icon name="check" className="size-3.5 shrink-0 opacity-80" />
              <span className="truncate">
                {fonction.code in FONCTIONS_PRO ? f(`${fonction.code}.nom`) : fonction.nom}
              </span>
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        onClick={onChoisir}
        className="relative mt-3 w-full rounded-xl bg-surface px-4 py-2 text-sm font-semibold text-ink shadow-sm sm:hidden"
      >
        {t("decouvrir")}
      </button>
    </div>
  );
}

/** Un passage à Standard programmé : Pro va à son terme, puis Standard prend la suite. */
function Programme({ changement }: { changement: ChangementProgramme }) {
  const t = useTranslations("pro.abonnement");
  const p = useTranslations("pro.abonnement.programme");
  const { dateLongue, montant } = useFormats();
  const nom = nomPlan(t, changement.plan);
  return (
    <div className="mb-4 flex items-start gap-3 rounded-2xl border border-info/30 bg-info-bg p-3.5 sm:mb-6 sm:p-4">
      <Icon name="calendar" className="mt-0.5 size-5 shrink-0 text-info" />
      <div className="min-w-0 text-[12.5px] leading-relaxed text-ink sm:text-sm">
        <p className="font-semibold">
          {p("titre", { offre: nom, date: dateLongue.format(new Date(changement.debut)) })}
        </p>
        <p className="mt-0.5 text-muted">
          {p("detail", {
            offre: nom,
            fin: dateLongue.format(new Date(changement.fin)),
            montant: montant(changement.montant, changement.devise),
          })}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// La proposition de l'annuel
// ---------------------------------------------------------------------------

function PasserALAnnuel({
  proposition,
  finPeriode,
  onChoisir,
}: {
  proposition: MonteeEnGamme;
  finPeriode: string | null;
  onChoisir: () => void;
}) {
  const t = useTranslations("pro.abonnement.annuel");
  const { dateLongue, montant } = useFormats();
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-salon/30 bg-salon-soft/60 p-3.5 sm:mb-6 sm:gap-4 sm:p-4">
      <span className="salon-gradient flex size-9 shrink-0 items-center justify-center rounded-full text-white sm:size-10">
        <Icon name="sparkles" className="size-4.5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink sm:text-base">
          {t("titre", { montant: montant(proposition.economie.montant, proposition.devise) })}
        </p>
        <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted sm:text-sm">
          {finPeriode
            ? t("detailSuite", {
                montant: montant(proposition.montant_annuel, proposition.devise),
                pct: proposition.economie.pourcentage,
                date: dateLongue.format(new Date(finPeriode)),
              })
            : t("detail", {
                montant: montant(proposition.montant_annuel, proposition.devise),
                pct: proposition.economie.pourcentage,
              })}
        </p>
      </div>
      <Button type="button" onClick={onChoisir} className="w-full sm:w-auto">
        {t("bouton")}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Un paiement attend d'être vérifié
// ---------------------------------------------------------------------------

function PaiementEnAttente({
  demande,
  tenantId,
  onConfirme,
}: {
  demande: PaymentRequest;
  tenantId: string;
  onConfirme: () => void;
}) {
  const t = useTranslations("pro.abonnement");
  const a = useTranslations("pro.abonnement.attente");
  const { dateLongue, montant, pourcent } = useFormats();
  const { membership } = useDashboard();
  return (
    <Card className="mb-6 sm:mb-8">
      <div className="flex items-start gap-3">
        <span className="relative mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-warning-bg text-warning">
          <span className="absolute inset-0 animate-ping rounded-full bg-warning/20" aria-hidden />
          <Icon name="clock" className="relative size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold text-ink sm:text-base">
            {a("titre")}
          </p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-muted sm:text-sm">
            {demande.method_kind === "kkiapay"
              ? a("kkiapay")
              : demande.method_kind === "saspay"
                ? a("saspay")
                : a("manuel")}
          </p>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Fait terme={a("offre")}>
          {nomPlan(t, demande.plan)} · {a("mois", { n: demande.billing_months })}
        </Fait>
        <Fait terme={a("montant")}>
          {montant(demande.amount, demande.currency)}
          {Number(demande.remise_montant) > 0 && (
            <span className="ml-1 text-[11px] font-normal text-success">
              ({pourcent(Number(demande.remise_pourcentage), "−")})
            </span>
          )}
        </Fait>
        <Fait terme={a("moyen")}>{demande.method_label}</Fait>
        <Fait terme={a("reference")}>
          <span className="font-mono text-xs">{demande.reference}</span>
        </Fait>
      </dl>
      <p className="mt-3 text-[11px] text-subtle sm:text-xs">
        {a("declare", { date: dateLongue.format(new Date(demande.created_at)) })}
      </p>
      {demande.method_kind === "saspay" && (
        <SaspayEnAttente tenantId={tenantId} demande={demande.id} onConfirme={onConfirme} />
      )}
    </Card>
  );
}

function Fait({ terme, children }: { terme: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl bg-surface-muted px-3 py-2">
      <dt className="text-[10.5px] uppercase tracking-wide text-subtle sm:text-[11px]">{terme}</dt>
      <dd className="mt-0.5 truncate text-[13px] font-medium text-ink sm:text-sm">{children}</dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Choisir, payer, déclarer
// ---------------------------------------------------------------------------

function Commande({
  offres,
  erreur,
  acces,
  planCourant,
  programme,
  plan: planVoulu,
  onPlan,
  tenantId,
  onEnvoye,
  onTarifModifie,
}: {
  offres: Offres | null;
  erreur: string | null;
  acces: Acces;
  planCourant?: string;
  programme: ChangementProgramme | null;
  plan: CodeOffre;
  onPlan: (code: CodeOffre) => void;
  tenantId: string;
  onEnvoye: () => void;
  /** Le tarif a change depuis l'affichage : relire les offres. */
  onTarifModifie: () => void;
}) {
  const t = useTranslations("pro.abonnement");
  const c = useTranslations("pro.abonnement.commande");
  const { region, dateLongue, montant } = useFormats();
  const toast = useToast();
  const [choixPays, setChoixPays] = useState<string | null>(null);
  const [choixDevise, setChoixDevise] = useState<string | null>(null);
  const [choixMoyen, setChoixMoyen] = useState<string | null>(null);
  const [reference, setReference] = useState("");
  const [preuve, setPreuve] = useState<File | null>(null);
  const [apercu, setApercu] = useState<string | null>(null);
  const [erreurPreuve, setErreurPreuve] = useState<string | null>(null);
  const [erreurEnvoi, setErreurEnvoi] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  // L'aperçu est une URL d'objet : elle se libère quand elle change ou que
  // la page se ferme, sinon le navigateur garde l'image en mémoire.
  useEffect(() => {
    if (!apercu) return;
    return () => URL.revokeObjectURL(apercu);
  }, [apercu]);

  if (erreur) return <ErrorState>{erreur}</ErrorState>;
  if (offres === null) return <Skeleton rows={2} />;

  if (offres.pays.length === 0) {
    return (
      <div id="offres" className="mb-8 scroll-mt-24">
        <EmptyState title={c("fermee.titre")}>{c("fermee.corps")}</EmptyState>
      </div>
    );
  }

  // Les choix se déduisent plutôt que de se recopier dans un effet : un pays
  // qui disparaît du catalogue retombe de lui-même sur le suivant.
  const pays =
    offres.pays.find((item) => item.code === choixPays) ??
    offres.pays.find((item) => item.code === offres.suggestion.pays) ??
    offres.pays[0];
  const devise =
    pays.devises.find((item) => item.code === choixDevise) ??
    pays.devises.find((item) => item.code === offres.suggestion.devise) ??
    pays.devises[0];
  const plan = devise.plans.find((item) => item.code === planVoulu) ?? devise.plans[0];
  const moyen = devise.moyens.find((item) => item.id === choixMoyen) ?? devise.moyens[0];
  // Le montant a verser : remises de parrainage deduites, calculees par le
  // serveur. C'est lui qu'on affiche, et lui que le serveur attend.
  const aVerser = plan ? (plan.montant_final ?? plan.montant) : "";
  const somme = plan ? montant(aVerser, devise.code) : "";
  const remise = offres.remise_parrainage;

  // Les deux groupes, s'ils sont tous deux en vente dans cette devise : une
  // devise sans prix Pro ne montre pas d'onglet Pro vide.
  const groupes = (["standard", "pro"] as const).filter((groupe) =>
    devise.plans.some((item) => item.groupe === groupe),
  );
  const groupe: Groupe = plan?.groupe ?? "standard";
  const plansDuGroupe = devise.plans.filter((item) => item.groupe === groupe);
  const bloque = groupe === "pro" && programme !== null;

  function changerDeGroupe(vers: Groupe) {
    if (vers === groupe) return;
    // On garde le rythme choisi : mensuel reste mensuel, annuel reste annuel.
    const annuel = plan?.mois === 12;
    const cible =
      devise.plans.find((item) => item.groupe === vers && (item.mois === 12) === annuel) ??
      devise.plans.find((item) => item.groupe === vers);
    if (cible) onPlan(cible.code);
  }

  const debutPeriode = plan?.effet
    ? decrireEffet(plan.effet, c, dateLongue, acces.raison === "essai")
    : acces.raison === "essai" || acces.raison === "periode"
      ? c("debutSuite", { date: dateLongue.format(new Date(acces.fin_periode ?? "")) })
      : c("debutValidation");

  /** Le pays, nommé par le navigateur dans la langue de l'espace. */
  const nomPays = (code: string, repli: string) => {
    try {
      return new Intl.DisplayNames([region], { type: "region" }).of(code) ?? repli;
    } catch {
      return repli;
    }
  };
  const nomOffre = plan ? nomPlan(t, { code: plan.code, name: plan.nom }) : "";

  function choisirPreuve(fichier: File | null) {
    setErreurPreuve(null);
    if (fichier && !FORMATS_PREUVE.includes(fichier.type)) {
      setErreurPreuve(c("preuveFormat"));
      return;
    }
    if (fichier && fichier.size > PREUVE_MAX) {
      setErreurPreuve(c("preuveTaille"));
      return;
    }
    setPreuve(fichier);
    setApercu(fichier ? URL.createObjectURL(fichier) : null);
  }

  async function envoyer(event: FormEvent) {
    event.preventDefault();
    if (!plan || !moyen) return;
    setErreurEnvoi(null);
    if (reference.trim().length < 4) {
      setErreurEnvoi(c("referenceCourte"));
      return;
    }

    const corps = new FormData();
    corps.set("plan", plan.code);
    corps.set("country", pays.code);
    corps.set("currency", devise.code);
    corps.set("method", moyen.id);
    corps.set("reference", reference.trim());
    // Le montant affiche : le serveur refuse s'il ne correspond plus au
    // tarif du moment, plutot que d'enregistrer un montant jamais montre.
    corps.set("montant_attendu", aVerser);
    if (preuve) corps.set("proof", preuve);

    setEnvoi(true);
    try {
      await dashboardFetch(
        "/api/v1/subscription/paiements",
        { method: "POST", body: corps },
        tenantId,
      );
      toast.success(c("declareOk"));
      setReference("");
      choisirPreuve(null);
      onEnvoye();
    } catch (caught) {
      setErreurEnvoi(
        caught instanceof DashboardError ? caught.message : c("envoiImpossible"),
      );
      if (caught instanceof DashboardError && caught.code === "demande_en_attente") {
        onEnvoye();
      }
      if (caught instanceof DashboardError && caught.code === "tarif_modifie") {
        onTarifModifie();
      }
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form id="offres" onSubmit={envoyer} className="mb-8 scroll-mt-24 space-y-5 sm:space-y-7">
      {/* 1. L'offre */}
      <div>
        <Etape numero={1} titre={c("etape1")} />

        {(offres.pays.length > 1 || pays.devises.length > 1) && (
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            {offres.pays.length > 1 && (
              <Pastilles
                libelle={c("pays")}
                options={offres.pays.map((item) => ({ valeur: item.code, texte: nomPays(item.code, item.nom) }))}
                valeur={pays.code}
                onChange={(valeur) => {
                  setChoixPays(valeur);
                  setChoixDevise(null);
                  setChoixMoyen(null);
                }}
              />
            )}
            {pays.devises.length > 1 && (
              <Pastilles
                libelle={c("devise")}
                options={pays.devises.map((item) => ({ valeur: item.code, texte: item.code }))}
                valeur={devise.code}
                onChange={(valeur) => {
                  setChoixDevise(valeur);
                  setChoixMoyen(null);
                }}
              />
            )}
          </div>
        )}

        {groupes.length > 1 && (
          <div
            role="tablist"
            aria-label={c("gamme")}
            className="mb-3 grid w-full grid-cols-2 rounded-xl border border-line bg-surface-muted p-1 sm:inline-grid sm:w-auto"
          >
            {groupes.map((item) => (
              <button
                key={item}
                type="button"
                role="tab"
                aria-selected={groupe === item}
                onClick={() => changerDeGroupe(item)}
                className={`flex items-center justify-center gap-1.5 rounded-lg px-4 py-1.5 text-[13px] font-semibold transition sm:px-6 sm:text-sm ${
                  groupe === item ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
                }`}
              >
                {item === "pro" && <Icon name="crown" className="size-3.5" />}
                {t(`groupes.${item}`)}
              </button>
            ))}
          </div>
        )}

        {remise && remise.nombre > 0 && (
          <p className="mb-3 flex items-start gap-2 rounded-xl bg-success-bg px-3 py-2 text-[12px] leading-relaxed text-success sm:text-[13px]">
            <Icon name="gift" className="mt-0.5 size-4 shrink-0" />
            <span>
              {c.rich("remise", {
                pct: remise.pourcentage,
                n: remise.nombre,
                gras: (texte) => <strong className="font-semibold">{texte}</strong>,
              })}{" "}
              <Link href="/parrainage" className="font-medium underline underline-offset-2">
                {c("monParrainage")}
              </Link>
            </span>
          </p>
        )}

        <div role="radiogroup" aria-label={c("offre")} className="grid grid-cols-2 gap-2.5 sm:gap-4">
          {plansDuGroupe.map((item) => (
            <CarteOffre
              key={item.code}
              offre={item}
              devise={devise}
              choisie={item.code === plan?.code}
              actuelle={item.code === planCourant}
              onChoisir={() => onPlan(item.code)}
            />
          ))}
        </div>

        {groupe === "pro" && offres.fonctions_pro.length > 0 && (
          <div className="mt-3 rounded-2xl border border-line bg-surface p-3 sm:p-4">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-subtle sm:text-xs">
              {c("toutStandard")}
            </p>
            <ListeFonctions fonctions={offres.fonctions_pro} />
          </div>
        )}

        {bloque ? (
          <p className="mt-2 rounded-xl bg-warning-bg px-3 py-2 text-[12px] leading-relaxed text-warning sm:text-xs">
            {c("bloque", { offre: programme ? nomPlan(t, programme.plan) : "" })}
          </p>
        ) : (
          <p className="mt-2 text-[11.5px] leading-relaxed text-muted sm:text-xs">{debutPeriode}</p>
        )}
      </div>

      {/* 2. Le règlement */}
      <div>
        <Etape numero={2} titre={c("etape2", { somme })} />

        {devise.moyens.length > 1 && (
          <div
            role="radiogroup"
            aria-label={c("moyen")}
            className="mb-3 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap"
          >
            {devise.moyens.map((item) => (
              <button
                key={item.id}
                type="button"
                role="radio"
                aria-checked={item.id === moyen?.id}
                onClick={() => setChoixMoyen(item.id)}
                className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-left text-[13px] font-medium transition sm:text-sm ${
                  item.id === moyen?.id
                    ? "border-salon bg-salon-soft text-salon"
                    : "border-line bg-surface text-ink hover:bg-surface-hover"
                }`}
              >
                <Icon
                  name={item.kind === "mobile_money" || item.kind === "saspay" ? "phone" : "scan"}
                  className="size-4 shrink-0"
                />
                <span className="truncate">{item.libelle}</span>
              </button>
            ))}
          </div>
        )}

        {moyen && plan && moyen.kind === "kkiapay" ? (
          <KkiapayButton tenantId={tenantId} choix={{ plan: plan.code, country: pays.code,
            currency: devise.code, method: moyen.id, montant_attendu: aVerser }} onConfirme={onEnvoye} />
        ) : moyen && plan && moyen.kind === "saspay" ? (
          <SaspayButton tenantId={tenantId} choix={{ plan: plan.code, country: pays.code,
            currency: devise.code, method: moyen.id, montant_attendu: aVerser }} />
        ) : moyen && plan && <PanneauMoyen moyen={moyen} somme={somme} />}
      </div>

      {/* 3. La déclaration */}
      {moyen?.kind !== "kkiapay" && moyen?.kind !== "saspay" && <div>
        <Etape numero={3} titre={c("etape3")} />
        <Card padded={false}>
          <div className="grid gap-4 p-4 sm:grid-cols-2 sm:p-5">
            <Field
              label={c("reference")}
              hint={c("referenceAide")}
            >
              <input
                className={inputClass}
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                maxLength={100}
                autoComplete="off"
                spellCheck={false}
                inputMode="text"
                required
                placeholder={c("referenceExemple")}
              />
            </Field>

            <div>
              <span className="mb-1.5 block text-sm font-medium text-ink">
                {c("capture")} <span className="font-normal text-subtle">{c("facultative")}</span>
              </span>
              <div className="flex items-center gap-3">
                {apercu ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={apercu}
                    alt={c("apercuCapture")}
                    className="size-14 shrink-0 rounded-lg border border-line object-cover"
                  />
                ) : (
                  <span className="flex size-14 shrink-0 items-center justify-center rounded-lg border border-dashed border-line-strong text-subtle">
                    <Icon name="image" className="size-5" />
                  </span>
                )}
                <div className="min-w-0 flex-1">
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-ink transition hover:bg-surface-hover">
                    {preuve ? c("changer") : c("ajouter")}
                    <input
                      type="file"
                      accept={FORMATS_PREUVE.join(",")}
                      className="sr-only"
                      onChange={(event) => {
                        choisirPreuve(event.target.files?.[0] ?? null);
                        event.target.value = "";
                      }}
                    />
                  </label>
                  {preuve && (
                    <button
                      type="button"
                      onClick={() => choisirPreuve(null)}
                      className="ml-2 text-xs text-muted underline-offset-2 hover:underline"
                    >
                      {c("retirer")}
                    </button>
                  )}
                  <p className="mt-1 truncate text-[11.5px] text-muted sm:text-xs">
                    {erreurPreuve ? (
                      <span className="font-medium text-danger">{erreurPreuve}</span>
                    ) : preuve ? (
                      preuve.name
                    ) : (
                      c("formats")
                    )}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {erreurEnvoi && (
            <div className="px-4 pb-4 sm:px-5">
              <ErrorState>{erreurEnvoi}</ErrorState>
            </div>
          )}

          {/* Collé au bas de l'écran sur téléphone tant que le formulaire est
              visible : l'action reste à portée du pouce pendant la saisie.
              La marge droite laisse la place au bouton flottant des réglages. */}
          <div className="sticky bottom-0 z-10 flex items-center gap-3 rounded-b-2xl border-t border-line bg-surface/95 px-4 py-3 pr-20 backdrop-blur sm:static sm:justify-between sm:bg-surface sm:px-5 sm:pr-5">
            <div className="min-w-0 flex-1">
              <p className="tabular truncate text-sm font-semibold text-ink sm:text-base">
                {somme}
                <span className="hidden font-normal text-muted sm:inline"> · {nomOffre}</span>
              </p>
              <p className="truncate text-[11px] text-muted sm:hidden">
                {c("offreMin", { offre: nomOffre })}
              </p>
              <p className="hidden text-xs text-muted sm:block">{c("accesVerification")}</p>
            </div>
            <Button type="submit" pending={envoi} disabled={!plan || !moyen || bloque} className="shrink-0">
              {c("declarer")}
              <span className="hidden sm:inline">{c("declarerSuite")}</span>
            </Button>
          </div>
        </Card>
        <p className="mt-2 text-[11.5px] leading-relaxed text-muted sm:hidden">
          {c("accesVerification")}
        </p>
      </div>}
    </form>
  );
}

/** Ce que fera le paiement, en une phrase — calculé aujourd'hui, appliqué à la validation. */
function decrireEffet(
  effet: Effet,
  c: Traduire,
  dateLongue: Intl.DateTimeFormat,
  pendantEssai = false,
): string {
  const debut = dateLongue.format(new Date(effet.debut));
  const fin = dateLongue.format(new Date(effet.fin));
  const jours = Math.round(effet.jours_credites);
  switch (effet.nature) {
    case "montee":
      // Pendant l'essai : les jours restants s'ajoutent en entier, sans
      // conversion (decide avec le produit).
      if (pendantEssai) {
        return jours > 0
          ? c("effet.monteeEssai", { n: jours, fin })
          : c("effet.monteeSimple", { fin });
      }
      return jours > 0
        ? c("effet.montee", { n: jours, fin })
        : c("effet.monteeSimple", { fin });
    case "descente":
      return c("effet.descente", { debut, fin });
    case "renouvellement":
      return c("effet.renouvellement", { debut, fin });
    default:
      return c("effet.defaut", { fin });
  }
}

function Etape({ numero, titre }: { numero: number; titre: string }) {
  return (
    <h2 className="mb-2.5 flex items-center gap-2 text-sm font-semibold text-ink sm:mb-3 sm:text-base">
      <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-salon text-[11px] font-semibold text-white sm:size-6 sm:text-xs">
        {numero}
      </span>
      {titre}
    </h2>
  );
}

function Pastilles({
  libelle,
  options,
  valeur,
  onChange,
}: {
  libelle: string;
  options: { valeur: string; texte: string }[];
  valeur: string;
  onChange: (valeur: string) => void;
}) {
  return (
    <div role="radiogroup" aria-label={libelle} className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-xs text-subtle">{libelle}</span>
      {options.map((option) => (
        <button
          key={option.valeur}
          type="button"
          role="radio"
          aria-checked={option.valeur === valeur}
          onClick={() => onChange(option.valeur)}
          className={`rounded-full border px-3 py-1 text-xs font-medium transition sm:text-[13px] ${
            option.valeur === valeur
              ? "border-salon bg-salon text-white"
              : "border-line bg-surface text-ink hover:bg-surface-hover"
          }`}
        >
          {option.texte}
        </button>
      ))}
    </div>
  );
}

function CarteOffre({
  offre,
  devise,
  choisie,
  actuelle,
  onChoisir,
}: {
  offre: OffrePlan;
  devise: Devise;
  choisie: boolean;
  actuelle: boolean;
  onChoisir: () => void;
}) {
  const t = useTranslations("pro.abonnement");
  const o = useTranslations("pro.abonnement.carte");
  const { montant } = useFormats();
  const annuel = offre.mois === 12;
  const final = offre.montant_final ?? offre.montant;
  const remise = Number(final) < Number(offre.montant);
  const parMois = annuel ? Number(final) / offre.mois : null;
  const economie =
    devise.economies?.[offre.groupe] ?? (offre.groupe === "standard" ? devise.economie : null);

  return (
    <button
      type="button"
      role="radio"
      aria-checked={choisie}
      onClick={onChoisir}
      className={`relative flex min-w-0 flex-col rounded-2xl border p-3 text-left transition active:scale-[0.99] sm:p-5 ${
        choisie
          ? "border-salon bg-salon-soft/60 shadow-card ring-1 ring-salon"
          : "border-line bg-surface hover:border-line-strong"
      }`}
    >
      {annuel && economie && (
        <span className="salon-gradient absolute -top-2.5 right-3 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white shadow-sm sm:text-[11px]">
          {o("meilleurPrix")}
        </span>
      )}

      <span className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-semibold text-ink sm:text-base">
          {nomPlan(t, { code: offre.code, name: offre.nom })}
        </span>
        <span
          aria-hidden
          className={`flex size-4 shrink-0 items-center justify-center rounded-full border sm:size-5 ${
            choisie ? "border-salon bg-salon text-white" : "border-line-strong"
          }`}
        >
          {choisie && <Icon name="check" className="size-3" />}
        </span>
      </span>

      {remise && (
        <span className="tabular mt-2 text-[11px] text-subtle line-through sm:text-sm">
          {montant(offre.montant, devise.code)}
        </span>
      )}
      <span
        className={`tabular min-w-0 break-words text-base font-bold tracking-tight text-ink sm:text-xl lg:text-2xl ${remise ? "" : "mt-2"}`}
      >
        {montant(final, devise.code)}
      </span>
      <span className="text-[11px] text-muted sm:text-xs">
        {annuel ? o("parAn") : o("parMois")}
        {parMois !== null && (
          <span className="block sm:inline">
            <span className="hidden sm:inline"> · </span>
            {o("soit", { montant: montant(parMois.toFixed(2), devise.code) })}
          </span>
        )}
      </span>

      <span className="mt-2.5 flex flex-wrap gap-1">
        {annuel && economie ? (
          <span className="inline-flex w-fit rounded-full bg-success-bg px-2 py-0.5 text-[10.5px] font-semibold text-success sm:text-xs">
            {o("economie", { pct: economie.pourcentage, montant: montant(economie.montant, devise.code) })}
          </span>
        ) : (
          <span className="text-[10.5px] text-subtle sm:text-xs">{o("sansEngagement")}</span>
        )}
        {actuelle && (
          <span className="inline-flex w-fit rounded-full bg-surface-muted px-2 py-0.5 text-[10.5px] font-medium text-muted sm:text-xs">
            {o("votreOffre")}
          </span>
        )}
      </span>
    </button>
  );
}

function PanneauMoyen({ moyen, somme }: { moyen: Moyen; somme: string }) {
  const m = useTranslations("pro.abonnement.moyen");
  const [qrEnErreur, setQrEnErreur] = useState<string | null>(null);

  if (moyen.kind !== "mobile_money") {
    return (
      <Card padded={false}>
        {/* Deux colonnes dès le téléphone : le code à gauche, les gestes à
            droite. Empilés, les instructions passaient sous le pouce. */}
        <div className="grid grid-cols-[7.5rem_1fr] items-start gap-3 p-3.5 sm:grid-cols-[13rem_1fr] sm:gap-6 sm:p-5">
          <div>
            {moyen.qr_url && qrEnErreur !== moyen.qr_url ? (
              <a href={moyen.qr_url} target="_blank" rel="noreferrer noopener" title={m("agrandir")}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={moyen.qr_url}
                  alt={m("qr", { moyen: moyen.libelle })}
                  className="aspect-square w-full rounded-xl border border-line bg-white object-contain p-1.5 sm:p-2"
                  onError={() => setQrEnErreur(moyen.qr_url)}
                />
              </a>
            ) : (
              <p className="rounded-xl border border-dashed border-line p-3 text-center text-[11px] text-muted">
                {m("qrIndisponible")}
              </p>
            )}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink sm:text-base">{moyen.libelle}</p>
            <ol className="mt-1.5 list-decimal space-y-1 pl-4 text-[12.5px] leading-relaxed text-muted sm:text-sm">
              <li>{m("scannez", { moyen: moyen.libelle })}</li>
              <li>
                {m.rich("envoyez", {
                  somme,
                  gras: (texte) => <strong className="text-ink">{texte}</strong>,
                })}
              </li>
              <li>{m("copiez")}</li>
            </ol>
          </div>
        </div>
        {moyen.instructions && (
          <p className="whitespace-pre-line border-t border-line px-3.5 py-2.5 text-[11.5px] leading-relaxed text-muted sm:px-5 sm:text-xs">
            {moyen.instructions}
          </p>
        )}
      </Card>
    );
  }

  return (
    <Card padded={false}>
      <div className="p-3.5 sm:p-5">
        <p className="text-sm font-semibold text-ink sm:text-base">{moyen.libelle}</p>
        <dl className="mt-3 grid grid-cols-2 gap-2">
          <div className="col-span-2 flex items-center justify-between gap-3 rounded-xl bg-surface-muted px-3 py-2.5">
            <div className="min-w-0">
              <dt className="text-[10.5px] uppercase tracking-wide text-subtle sm:text-[11px]">{m("numero")}</dt>
              <dd className="tabular truncate text-base font-semibold text-ink sm:text-lg">
                {moyen.account_number}
              </dd>
            </div>
            <Copier texte={moyen.account_number} succes={m("numeroCopie")} />
          </div>
          <div className="min-w-0 rounded-xl bg-surface-muted px-3 py-2">
            <dt className="text-[10.5px] uppercase tracking-wide text-subtle sm:text-[11px]">{m("titulaire")}</dt>
            <dd className="truncate text-[13px] font-medium text-ink sm:text-sm">{moyen.account_holder}</dd>
          </div>
          <div className="min-w-0 rounded-xl bg-surface-muted px-3 py-2">
            <dt className="text-[10.5px] uppercase tracking-wide text-subtle sm:text-[11px]">{m("montant")}</dt>
            <dd className="tabular truncate text-[13px] font-medium text-ink sm:text-sm">{somme}</dd>
          </div>
        </dl>
        <p className="mt-2.5 text-[11.5px] leading-relaxed text-muted sm:text-xs">
          {m("verifiez")}
        </p>
      </div>
      {moyen.instructions && (
        <p className="whitespace-pre-line border-t border-line px-3.5 py-2.5 text-[11.5px] leading-relaxed text-muted sm:px-5 sm:text-xs">
          {moyen.instructions}
        </p>
      )}
    </Card>
  );
}

function Copier({ texte, succes }: { texte: string; succes: string }) {
  const m = useTranslations("pro.abonnement.moyen");
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
      className="shrink-0"
      icon={<Icon name={copie ? "check" : "copy"} className="size-4" />}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(texte);
          setCopie(true);
          toast.success(succes);
        } catch {
          toast.error(m("copieImpossible"));
        }
      }}
    >
      {copie ? m("copie") : m("copier")}
    </GhostButton>
  );
}

// ---------------------------------------------------------------------------
// Le suivi : paiements déclarés et factures, en onglets
// ---------------------------------------------------------------------------

function Suivi({
  demandes,
  erreurDemandes,
  factures: page,
  erreurFactures,
}: {
  demandes: PaymentRequest[] | null;
  erreurDemandes: string | null;
  factures: Page<Invoice> | null;
  erreurFactures: string | null;
}) {
  const s = useTranslations("pro.abonnement.suivi");
  const [onglet, setOnglet] = useState<"paiements" | "factures">("paiements");
  const factures = rows(page);

  const onglets = [
    { cle: "paiements" as const, texte: s("paiements"), nombre: demandes?.length ?? 0 },
    { cle: "factures" as const, texte: s("factures"), nombre: factures.length },
  ];

  return (
    <div className="mb-8">
      <div
        role="tablist"
        aria-label={s("aria")}
        className="mb-3 inline-flex rounded-xl border border-line bg-surface-muted p-1"
      >
        {onglets.map((item) => (
          <button
            key={item.cle}
            type="button"
            role="tab"
            aria-selected={onglet === item.cle}
            onClick={() => setOnglet(item.cle)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium transition sm:px-4 sm:text-sm ${
              onglet === item.cle ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            {item.texte}
            {item.nombre > 0 && (
              <span className="tabular rounded-full bg-surface-muted px-1.5 text-[11px] text-muted">
                {item.nombre}
              </span>
            )}
          </button>
        ))}
      </div>

      {onglet === "paiements" ? (
        <Historique demandes={demandes} erreur={erreurDemandes} />
      ) : (
        <Factures factures={factures} chargees={page !== null} erreur={erreurFactures} />
      )}
    </div>
  );
}

function Vide({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-2xl border border-dashed border-line-strong px-4 py-6 text-center text-[13px] text-muted sm:text-sm">
      {children}
    </p>
  );
}

function Historique({
  demandes,
  erreur,
}: {
  demandes: PaymentRequest[] | null;
  erreur: string | null;
}) {
  const t = useTranslations("pro.abonnement");
  const s = useTranslations("pro.abonnement.suivi");
  const { dateLongue, montant } = useFormats();
  if (erreur) return <ErrorState>{s("erreurHistorique")}</ErrorState>;
  if (demandes === null) return <Skeleton rows={2} />;
  if (demandes.length === 0) return <Vide>{s("aucunPaiement")}</Vide>;

  return (
    <ul className="grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-3">
      {demandes.map((demande) => {
        const ton = DEMANDE[demande.status] ?? "neutral";
        return (
          <li key={demande.id} className="min-w-0">
            <Card padded={false} className="h-full p-3 sm:p-4">
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <span className="tabular text-sm font-semibold text-ink sm:text-base">
                  {montant(demande.amount, demande.currency)}
                </span>
                <Badge tone={ton}>
                  {demande.status in DEMANDE
                    ? t(`statutDemande.${demande.status}`)
                    : demande.status_label}
                </Badge>
              </div>
              <p className="mt-1 truncate text-[11.5px] text-muted sm:text-xs">
                {nomPlan(t, demande.plan)} · {demande.method_label}
              </p>
              {Number(demande.remise_montant) > 0 && (
                <p className="mt-1 truncate text-[10.5px] font-medium text-success sm:text-xs">
                  {s("parrainage", {
                    pct: Number(demande.remise_pourcentage),
                    montant: montant(demande.remise_montant, demande.currency),
                  })}
                </p>
              )}
              <p className="mt-0.5 truncate font-mono text-[10.5px] text-subtle sm:text-[11px]">
                {demande.reference}
              </p>
              <p className="mt-1.5 text-[10.5px] text-subtle sm:text-xs">
                {dateLongue.format(new Date(demande.created_at))}
              </p>

              {demande.status === "approved" && demande.period_start && demande.period_end && (
                <p className="mt-2 rounded-lg bg-success-bg px-2 py-1.5 text-[10.5px] text-success sm:text-xs">
                  {s("periode", {
                    debut: dateLongue.format(new Date(demande.period_start)),
                    fin: dateLongue.format(new Date(demande.period_end)),
                  })}
                </p>
              )}
              {demande.status === "rejected" && demande.rejection_reason && (
                <p className="mt-2 rounded-lg bg-danger-bg px-2 py-1.5 text-[10.5px] text-danger sm:text-xs">
                  {demande.rejection_reason}
                </p>
              )}
              {demande.proof_url && (
                <a
                  href={demande.proof_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-salon hover:underline sm:text-xs"
                >
                  <Icon name="image" className="size-3.5" />
                  {s("capture")}
                </a>
              )}
            </Card>
          </li>
        );
      })}
    </ul>
  );
}

function Factures({
  factures,
  chargees,
  erreur,
}: {
  factures: Invoice[];
  chargees: boolean;
  erreur: string | null;
}) {
  const t = useTranslations("pro.abonnement");
  const s = useTranslations("pro.abonnement.suivi");
  const { dateLongue, montant } = useFormats();
  if (erreur) return <ErrorState>{s("erreurFactures")}</ErrorState>;
  if (!chargees) return <Skeleton rows={2} />;
  if (factures.length === 0) return <Vide>{s("aucuneFacture")}</Vide>;

  return (
    <ul className="grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-3">
      {factures.map((facture) => {
        const retard = facture.is_overdue && facture.status === "issued";
        const ton = FACTURE[facture.status];
        return (
          <li key={facture.id} className="min-w-0">
            <Card padded={false} className="h-full p-3 sm:p-4">
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <span className="tabular text-sm font-semibold text-ink sm:text-base">
                  {montant(facture.amount, facture.currency)}
                </span>
                <Badge tone={retard ? "danger" : (ton ?? "neutral")}>
                  {retard
                    ? s("enRetard")
                    : ton
                      ? t(`statutFacture.${facture.status}`)
                      : facture.status}
                </Badge>
              </div>
              <p className="tabular mt-1 truncate text-[11.5px] font-medium text-ink sm:text-xs">
                {facture.number}
              </p>
              <p className="mt-0.5 line-clamp-2 text-[10.5px] text-muted sm:text-xs">
                {facture.label}
              </p>
              <p className="mt-1.5 text-[10.5px] text-subtle sm:text-xs">
                {facture.paid_at
                  ? s("regleeLe", { date: dateLongue.format(new Date(facture.paid_at)) })
                  : s("emiseLe", { date: dateLongue.format(new Date(facture.issued_at)) })}
              </p>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Les questions qu'on se pose avant de payer
// ---------------------------------------------------------------------------

/** Les questions, sous `pro.abonnement.questions` (`q` et `r`). */
const QUESTIONS = ["debut", "annuel", "versPro", "versStandard", "retard", "rappel"];

function Questions() {
  const q = useTranslations("pro.abonnement.questions");
  return (
    <div>
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
        {q("titre")}
      </h2>
      <div className="grid gap-2 sm:grid-cols-2">
        {QUESTIONS.map((cle) => ({ question: q(`${cle}.q`), reponse: q(`${cle}.r`) })).map((item) => (
          <details
            key={item.question}
            className="group rounded-2xl border border-line bg-surface px-4 py-3 open:shadow-card"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[13px] font-medium text-ink sm:text-sm">
              {item.question}
              <Icon
                name="plus"
                className="size-4 shrink-0 text-muted transition-transform group-open:rotate-45"
              />
            </summary>
            <p className="mt-2 text-[12.5px] leading-relaxed text-muted sm:text-sm">
              {item.reponse}
            </p>
          </details>
        ))}
      </div>
    </div>
  );
}
