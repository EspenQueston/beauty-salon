"use client";

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

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";

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
  dateLongue,
  joursAvant,
  montant,
  signalerAbonnement,
  type Acces,
  type MonteeEnGamme,
} from "./abonnement";
import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";
import { rows, useResource, type Page } from "./useResource";

// ---------------------------------------------------------------------------
// Formes de l'API
// ---------------------------------------------------------------------------

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "salon";
type CodeOffre = "monthly" | "yearly";

interface PaymentRequest {
  id: string;
  created_at: string;
  plan: { code: string; name: string };
  billing_months: number;
  country: string;
  currency: string;
  amount: string;
  method_kind: "wechat" | "alipay" | "mobile_money";
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
}

interface Moyen {
  id: string;
  kind: "wechat" | "alipay" | "mobile_money";
  kind_label: string;
  libelle: string;
  account_number: string;
  account_holder: string;
  instructions: string;
  qr_url: string;
}

interface OffrePlan {
  code: CodeOffre;
  nom: string;
  description: string;
  mois: number;
  montant: string;
}

interface Devise {
  code: string;
  nom: string;
  plans: OffrePlan[];
  economie: { montant: string; pourcentage: number; douze_mois: string } | null;
  moyens: Moyen[];
}

interface Pays {
  code: string;
  nom: string;
  devises: Devise[];
}

interface Offres {
  pays: Pays[];
  suggestion: { pays: string; devise: string };
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

const DEMANDE: Record<PaymentRequest["status"], { label: string; tone: Tone }> = {
  pending: { label: "En vérification", tone: "warning" },
  approved: { label: "Validé", tone: "success" },
  rejected: { label: "Refusé", tone: "danger" },
};

const FACTURE: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Brouillon", tone: "neutral" },
  issued: { label: "À régler", tone: "warning" },
  paid: { label: "Réglée", tone: "success" },
  void: { label: "Annulée", tone: "neutral" },
};

const FORMATS_PREUVE = ["image/jpeg", "image/png", "image/webp"];
const PREUVE_MAX = 15 * 1024 * 1024;
const RELECTURE_MS = 20_000;
const HORLOGE_MS = 60_000;

/** Descend jusqu'aux offres, en douceur, sous la barre du haut. */
function allerAuxOffres() {
  document.getElementById("offres")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------------------
// La page
// ---------------------------------------------------------------------------

export function Billing() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const isOwner = membership.role === "owner";
  const toast = useToast();

  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [error, setError] = useState<string | null>(null);
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
            toast.success("Paiement validé : votre abonnement est actif.");
          } else {
            toast.info("Votre paiement a été traité. Consultez l'historique.");
          }
          signalerAbonnement();
        }
        setSubscription(data);
        setError(null);
      })
      .catch((caught) => {
        if (cancelled) return;
        setError(
          caught instanceof DashboardError && caught.status === 404
            ? "Aucun abonnement n'est encore rattaché à ce salon. L'équipe Beauty Salon s'en charge à la validation."
            : "Chargement impossible.",
        );
      });

    return () => {
      cancelled = true;
    };
  }, [tenantId, isOwner, token, toast]);

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
        <PageHeader title="Abonnement" />
        <EmptyState title="Réservé au propriétaire">
          Le règlement de l&apos;abonnement se fait depuis le compte de la
          personne qui possède le salon.
        </EmptyState>
      </section>
    );
  }

  const planCourant = subscription?.plan.code;
  const plan: CodeOffre = choixPlan ?? (planCourant === "yearly" ? "yearly" : "monthly");

  return (
    <section>
      <PageHeader
        title="Abonnement"
        description="Votre accès, votre offre et vos paiements, au même endroit."
      />

      {error && <ErrorState>{error}</ErrorState>}
      {subscription === null && !error && <Skeleton rows={3} />}

      {subscription && (
        <>
          <Etat
            abonnement={subscription}
            maintenant={maintenant}
            onAgir={subscription.demande_en_attente ? undefined : allerAuxOffres}
          />

          {subscription.demande_en_attente ? (
            <PaiementEnAttente demande={subscription.demande_en_attente} />
          ) : (
            <>
              {subscription.montee_en_gamme && plan !== "yearly" && (
                <PasserALAnnuel
                  proposition={subscription.montee_en_gamme}
                  finPeriode={subscription.acces.fin_periode}
                  onChoisir={() => {
                    setChoixPlan("yearly");
                    allerAuxOffres();
                  }}
                />
              )}
              <Commande
                offres={offres.data}
                erreur={offres.error}
                acces={subscription.acces}
                planCourant={planCourant}
                plan={plan}
                onPlan={setChoixPlan}
                tenantId={tenantId}
                onEnvoye={() => {
                  relire();
                  signalerAbonnement();
                }}
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
  const { acces } = abonnement;
  const fin = acces.fin_periode ? dateLongue.format(new Date(acces.fin_periode)) : "—";
  const limite = acces.jusqu_au ? dateLongue.format(new Date(acces.jusqu_au)) : "";
  const jours = joursAvant(acces.fin_periode, maintenant);
  const joursGrace = joursAvant(acces.jusqu_au, maintenant);
  const pluriel = (n: number) => (n > 1 ? "s" : "");

  const debut = new Date(abonnement.current_period_start).getTime();
  const total = new Date(abonnement.current_period_end).getTime() - debut;
  const restant =
    total > 0 ? Math.min(1, Math.max(0, (new Date(abonnement.current_period_end).getTime() - maintenant) / total)) : 0;
  const payant = abonnement.plan.code === "monthly" || abonnement.plan.code === "yearly";

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
      titre: "Essai gratuit en cours",
      detail: (
        <>
          Jusqu&apos;au <strong className="text-ink">{fin}</strong>. Choisissez
          votre offre quand vous voulez : la période payée commence à la fin de
          l&apos;essai.
        </>
      ),
      tone: "info",
      badge: "Essai",
      anneau: { valeur: String(jours), unite: `jour${pluriel(jours)}`, part: restant },
      action: "Choisir mon offre",
    },
    periode: {
      titre: `Offre ${abonnement.plan.name} active`,
      detail: (
        <>
          Votre salon est couvert jusqu&apos;au{" "}
          <strong className="text-ink">{fin}</strong>. Un paiement anticipé
          s&apos;ajoute à la suite, sans perdre un jour.
        </>
      ),
      tone: "success",
      badge: "Actif",
      anneau: { valeur: String(jours), unite: `jour${pluriel(jours)}`, part: restant },
      action: "Prolonger",
    },
    grace: {
      titre: "Période terminée — délai de grâce",
      detail: (
        <>
          Réglez avant le <strong className="text-ink">{limite}</strong> :
          ensuite, les réservations en ligne s&apos;arrêtent et le tableau de
          bord passe en lecture seule.
        </>
      ),
      tone: "warning",
      badge: "Grâce",
      anneau: { valeur: String(joursGrace), unite: `jour${pluriel(joursGrace)}`, part: joursGrace / 3 },
      action: "Régler maintenant",
    },
    expire: {
      titre: "Abonnement expiré",
      detail: (
        <>
          Réservations en ligne fermées, tableau de bord en lecture seule. Vos
          données sont intactes : tout se rouvre dès la validation de votre
          paiement.
        </>
      ),
      tone: "danger",
      badge: "Expiré",
      anneau: null,
      action: "Réactiver mon salon",
    },
    suspendu: {
      titre: "Abonnement suspendu",
      detail: <>L&apos;équipe Beauty Salon a suspendu ce salon. Contactez-la pour le rouvrir.</>,
      tone: "danger",
      badge: "Suspendu",
      anneau: null,
    },
    resilie: {
      titre: "Abonnement résilié",
      detail: <>Contactez l&apos;équipe Beauty Salon pour reprendre.</>,
      tone: "neutral",
      badge: "Résilié",
      anneau: null,
    },
    sans_abonnement: {
      titre: "Abonnement en préparation",
      detail: <>L&apos;équipe Beauty Salon rattache votre essai sous peu.</>,
      tone: "neutral",
      badge: "—",
      anneau: null,
    },
  };
  const vue = vues[acces.raison] ?? vues.sans_abonnement;
  const action = onAgir && vue.action ? vue.action : null;

  const faits: { terme: string; valeur: string }[] = [
    { terme: "Offre", valeur: abonnement.plan.name },
    { terme: "Statut", valeur: abonnement.status_label },
    {
      terme: acces.raison === "essai" ? "Fin de l'essai" : "Fin de période",
      valeur: fin,
    },
    {
      terme: "Tarif",
      valeur:
        payant && Number(abonnement.price_amount) > 0
          ? `${montant(abonnement.price_amount, abonnement.currency)} / ${abonnement.plan.code === "yearly" ? "an" : "mois"}`
          : "Gratuit",
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
  const rayon = 42;
  const tour = 2 * Math.PI * rayon;
  const rempli = Math.max(0.04, Math.min(1, part));

  return (
    <div
      className="relative size-16 shrink-0 sm:size-24"
      role="img"
      aria-label={`${valeur} ${unite} restant${Number(valeur) > 1 ? "s" : ""}`}
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
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-salon/30 bg-salon-soft/60 p-3.5 sm:mb-6 sm:gap-4 sm:p-4">
      <span className="salon-gradient flex size-9 shrink-0 items-center justify-center rounded-full text-white sm:size-10">
        <Icon name="sparkles" className="size-4.5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink sm:text-base">
          Passez à l&apos;annuel, économisez{" "}
          {montant(proposition.economie.montant, proposition.devise)} par an
        </p>
        <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted sm:text-sm">
          {montant(proposition.montant_annuel, proposition.devise)} pour douze mois
          (−{proposition.economie.pourcentage} %)
          {finPeriode
            ? `, à partir du ${dateLongue.format(new Date(finPeriode))} — à la suite de votre mois en cours.`
            : "."}
        </p>
      </div>
      <Button type="button" onClick={onChoisir} className="w-full sm:w-auto">
        Passer à l&apos;annuel
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Un paiement attend d'être vérifié
// ---------------------------------------------------------------------------

function PaiementEnAttente({ demande }: { demande: PaymentRequest }) {
  return (
    <Card className="mb-6 sm:mb-8">
      <div className="flex items-start gap-3">
        <span className="relative mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-warning-bg text-warning">
          <span className="absolute inset-0 animate-ping rounded-full bg-warning/20" aria-hidden />
          <Icon name="clock" className="relative size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold text-ink sm:text-base">
            Paiement en cours de vérification
          </p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-muted sm:text-sm">
            L&apos;équipe Beauty Salon retrouve votre versement sur le compte
            crédité, puis ouvre votre période. Cette page se met à jour
            d&apos;elle-même ; vous recevez aussi un e-mail et une notification.
          </p>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Fait terme="Offre">
          {demande.plan.name} · {demande.billing_months} mois
        </Fait>
        <Fait terme="Montant">{montant(demande.amount, demande.currency)}</Fait>
        <Fait terme="Moyen">{demande.method_label}</Fait>
        <Fait terme="Référence">
          <span className="font-mono text-xs">{demande.reference}</span>
        </Fait>
      </dl>
      <p className="mt-3 text-[11px] text-subtle sm:text-xs">
        Déclaré le {dateLongue.format(new Date(demande.created_at))}. Un seul
        paiement peut attendre à la fois.
      </p>
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
  plan: planVoulu,
  onPlan,
  tenantId,
  onEnvoye,
}: {
  offres: Offres | null;
  erreur: string | null;
  acces: Acces;
  planCourant?: string;
  plan: CodeOffre;
  onPlan: (code: CodeOffre) => void;
  tenantId: string;
  onEnvoye: () => void;
}) {
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
        <EmptyState title="Le règlement n'est pas encore ouvert">
          Aucun moyen de paiement n&apos;est configuré pour le moment.
          L&apos;équipe Beauty Salon vous contacte avant la fin de votre
          période — rien ne s&apos;interrompt sans prévenir.
        </EmptyState>
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
  const somme = plan ? montant(plan.montant, devise.code) : "";

  const debutPeriode =
    acces.raison === "essai" || acces.raison === "periode"
      ? `Votre nouvelle période commencera le ${dateLongue.format(new Date(acces.fin_periode ?? ""))}, à la suite de l'actuelle.`
      : "Votre période commencera à la validation du paiement.";

  function choisirPreuve(fichier: File | null) {
    setErreurPreuve(null);
    if (fichier && !FORMATS_PREUVE.includes(fichier.type)) {
      setErreurPreuve("Envoyez une capture en JPEG, PNG ou WebP.");
      return;
    }
    if (fichier && fichier.size > PREUVE_MAX) {
      setErreurPreuve("La capture dépasse 15 Mo. Envoyez une image plus légère.");
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
      setErreurEnvoi("Indiquez la référence complète de la transaction.");
      return;
    }

    const corps = new FormData();
    corps.set("plan", plan.code);
    corps.set("country", pays.code);
    corps.set("currency", devise.code);
    corps.set("method", moyen.id);
    corps.set("reference", reference.trim());
    if (preuve) corps.set("proof", preuve);

    setEnvoi(true);
    try {
      await dashboardFetch(
        "/api/v1/subscription/paiements",
        { method: "POST", body: corps },
        tenantId,
      );
      toast.success("Paiement déclaré. Vous recevez un e-mail de confirmation.");
      setReference("");
      choisirPreuve(null);
      onEnvoye();
    } catch (caught) {
      setErreurEnvoi(
        caught instanceof DashboardError ? caught.message : "Envoi impossible pour le moment.",
      );
      if (caught instanceof DashboardError && caught.code === "demande_en_attente") {
        onEnvoye();
      }
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form id="offres" onSubmit={envoyer} className="mb-8 scroll-mt-24 space-y-5 sm:space-y-7">
      {/* 1. L'offre */}
      <div>
        <Etape numero={1} titre="Votre offre" />

        {(offres.pays.length > 1 || pays.devises.length > 1) && (
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            {offres.pays.length > 1 && (
              <Pastilles
                libelle="Pays"
                options={offres.pays.map((item) => ({ valeur: item.code, texte: item.nom }))}
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
                libelle="Devise"
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

        <div role="radiogroup" aria-label="Offre" className="grid grid-cols-2 gap-2.5 sm:gap-4">
          {devise.plans.map((item) => (
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
        <p className="mt-2 text-[11.5px] leading-relaxed text-muted sm:text-xs">{debutPeriode}</p>
      </div>

      {/* 2. Le règlement */}
      <div>
        <Etape numero={2} titre={`Payez ${somme}`} />

        {devise.moyens.length > 1 && (
          <div
            role="radiogroup"
            aria-label="Moyen de paiement"
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
                <Icon name={item.kind === "mobile_money" ? "phone" : "scan"} className="size-4 shrink-0" />
                <span className="truncate">{item.libelle}</span>
              </button>
            ))}
          </div>
        )}

        {moyen && plan && <PanneauMoyen moyen={moyen} somme={somme} />}
      </div>

      {/* 3. La déclaration */}
      <div>
        <Etape numero={3} titre="Déclarez votre paiement" />
        <Card padded={false}>
          <div className="grid gap-4 p-4 sm:grid-cols-2 sm:p-5">
            <Field
              label="Référence de la transaction"
              hint="Le numéro du reçu, dans votre application de paiement."
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
                placeholder="Ex. : 4200001234202609251234"
              />
            </Field>

            <div>
              <span className="mb-1.5 block text-sm font-medium text-ink">
                Capture du reçu <span className="font-normal text-subtle">(facultative)</span>
              </span>
              <div className="flex items-center gap-3">
                {apercu ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={apercu}
                    alt="Aperçu de la capture"
                    className="size-14 shrink-0 rounded-lg border border-line object-cover"
                  />
                ) : (
                  <span className="flex size-14 shrink-0 items-center justify-center rounded-lg border border-dashed border-line-strong text-subtle">
                    <Icon name="image" className="size-5" />
                  </span>
                )}
                <div className="min-w-0 flex-1">
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-ink transition hover:bg-surface-hover">
                    {preuve ? "Changer" : "Ajouter"}
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
                      Retirer
                    </button>
                  )}
                  <p className="mt-1 truncate text-[11.5px] text-muted sm:text-xs">
                    {erreurPreuve ? (
                      <span className="font-medium text-danger">{erreurPreuve}</span>
                    ) : preuve ? (
                      preuve.name
                    ) : (
                      "JPEG, PNG ou WebP, 15 Mo au plus."
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
                <span className="hidden font-normal text-muted sm:inline"> · {plan?.nom}</span>
              </p>
              <p className="truncate text-[11px] text-muted sm:hidden">
                Offre {plan?.nom.toLowerCase()}
              </p>
              <p className="hidden text-xs text-muted sm:block">
                Votre accès s&apos;ouvre à la vérification du versement, pas à
                l&apos;envoi de ce formulaire.
              </p>
            </div>
            <Button type="submit" pending={envoi} disabled={!plan || !moyen} className="shrink-0">
              Déclarer
              <span className="hidden sm:inline"> mon paiement</span>
            </Button>
          </div>
        </Card>
        <p className="mt-2 text-[11.5px] leading-relaxed text-muted sm:hidden">
          Votre accès s&apos;ouvre à la vérification du versement, pas à
          l&apos;envoi de ce formulaire.
        </p>
      </div>
    </form>
  );
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
  const annuel = offre.code === "yearly";
  const parMois = annuel ? Number(offre.montant) / offre.mois : null;

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
      {annuel && devise.economie && (
        <span className="salon-gradient absolute -top-2.5 right-3 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white shadow-sm sm:text-[11px]">
          Meilleur prix
        </span>
      )}

      <span className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-semibold text-ink sm:text-base">{offre.nom}</span>
        <span
          aria-hidden
          className={`flex size-4 shrink-0 items-center justify-center rounded-full border sm:size-5 ${
            choisie ? "border-salon bg-salon text-white" : "border-line-strong"
          }`}
        >
          {choisie && <Icon name="check" className="size-3" />}
        </span>
      </span>

      <span className="tabular mt-2 text-lg font-bold tracking-tight text-ink sm:text-3xl">
        {montant(offre.montant, devise.code)}
      </span>
      <span className="text-[11px] text-muted sm:text-xs">
        {annuel ? "par an" : "par mois"}
        {parMois !== null && (
          <span className="block sm:inline">
            <span className="hidden sm:inline"> · </span>soit {montant(parMois.toFixed(2), devise.code)}/mois
          </span>
        )}
      </span>

      <span className="mt-2.5 flex flex-wrap gap-1">
        {annuel && devise.economie ? (
          <span className="inline-flex w-fit rounded-full bg-success-bg px-2 py-0.5 text-[10.5px] font-semibold text-success sm:text-xs">
            −{devise.economie.pourcentage} % · {montant(devise.economie.montant, devise.code)}
          </span>
        ) : (
          <span className="text-[10.5px] text-subtle sm:text-xs">Sans engagement</span>
        )}
        {actuelle && (
          <span className="inline-flex w-fit rounded-full bg-surface-muted px-2 py-0.5 text-[10.5px] font-medium text-muted sm:text-xs">
            Votre offre
          </span>
        )}
      </span>
    </button>
  );
}

function PanneauMoyen({ moyen, somme }: { moyen: Moyen; somme: string }) {
  const [qrEnErreur, setQrEnErreur] = useState<string | null>(null);

  if (moyen.kind !== "mobile_money") {
    return (
      <Card padded={false}>
        {/* Deux colonnes dès le téléphone : le code à gauche, les gestes à
            droite. Empilés, les instructions passaient sous le pouce. */}
        <div className="grid grid-cols-[7.5rem_1fr] items-start gap-3 p-3.5 sm:grid-cols-[13rem_1fr] sm:gap-6 sm:p-5">
          <div>
            {moyen.qr_url && qrEnErreur !== moyen.qr_url ? (
              <a href={moyen.qr_url} target="_blank" rel="noreferrer noopener" title="Agrandir">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={moyen.qr_url}
                  alt={`QR code ${moyen.libelle}`}
                  className="aspect-square w-full rounded-xl border border-line bg-white object-contain p-1.5 sm:p-2"
                  onError={() => setQrEnErreur(moyen.qr_url)}
                />
              </a>
            ) : (
              <p className="rounded-xl border border-dashed border-line p-3 text-center text-[11px] text-muted">
                QR code indisponible. Rechargez la page.
              </p>
            )}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink sm:text-base">{moyen.libelle}</p>
            <ol className="mt-1.5 list-decimal space-y-1 pl-4 text-[12.5px] leading-relaxed text-muted sm:text-sm">
              <li>Scannez le code avec {moyen.libelle}.</li>
              <li>
                Envoyez exactement <strong className="text-ink">{somme}</strong>.
              </li>
              <li>Copiez la référence du reçu ci-dessous.</li>
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
              <dt className="text-[10.5px] uppercase tracking-wide text-subtle sm:text-[11px]">Numéro</dt>
              <dd className="tabular truncate text-base font-semibold text-ink sm:text-lg">
                {moyen.account_number}
              </dd>
            </div>
            <Copier texte={moyen.account_number} quoi="Numéro" />
          </div>
          <div className="min-w-0 rounded-xl bg-surface-muted px-3 py-2">
            <dt className="text-[10.5px] uppercase tracking-wide text-subtle sm:text-[11px]">Titulaire</dt>
            <dd className="truncate text-[13px] font-medium text-ink sm:text-sm">{moyen.account_holder}</dd>
          </div>
          <div className="min-w-0 rounded-xl bg-surface-muted px-3 py-2">
            <dt className="text-[10.5px] uppercase tracking-wide text-subtle sm:text-[11px]">Montant</dt>
            <dd className="tabular truncate text-[13px] font-medium text-ink sm:text-sm">{somme}</dd>
          </div>
        </dl>
        <p className="mt-2.5 text-[11.5px] leading-relaxed text-muted sm:text-xs">
          Vérifiez que le nom du titulaire s&apos;affiche avant de valider
          l&apos;envoi dans votre application.
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

function Copier({ texte, quoi }: { texte: string; quoi: string }) {
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
          toast.success(`${quoi} copié.`);
        } catch {
          toast.error("Copie impossible : sélectionnez le texte à la main.");
        }
      }}
    >
      {copie ? "Copié" : "Copier"}
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
  const [onglet, setOnglet] = useState<"paiements" | "factures">("paiements");
  const factures = rows(page);

  const onglets = [
    { cle: "paiements" as const, texte: "Paiements", nombre: demandes?.length ?? 0 },
    { cle: "factures" as const, texte: "Factures", nombre: factures.length },
  ];

  return (
    <div className="mb-8">
      <div
        role="tablist"
        aria-label="Suivi de l'abonnement"
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
  if (erreur) return <ErrorState>Impossible de charger l&apos;historique.</ErrorState>;
  if (demandes === null) return <Skeleton rows={2} />;
  if (demandes.length === 0) return <Vide>Aucun paiement déclaré pour l&apos;instant.</Vide>;

  return (
    <ul className="grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-3">
      {demandes.map((demande) => {
        const etat = DEMANDE[demande.status];
        return (
          <li key={demande.id} className="min-w-0">
            <Card padded={false} className="h-full p-3 sm:p-4">
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <span className="tabular text-sm font-semibold text-ink sm:text-base">
                  {montant(demande.amount, demande.currency)}
                </span>
                <Badge tone={etat.tone}>{etat.label}</Badge>
              </div>
              <p className="mt-1 truncate text-[11.5px] text-muted sm:text-xs">
                {demande.plan.name} · {demande.method_label}
              </p>
              <p className="mt-0.5 truncate font-mono text-[10.5px] text-subtle sm:text-[11px]">
                {demande.reference}
              </p>
              <p className="mt-1.5 text-[10.5px] text-subtle sm:text-xs">
                {dateLongue.format(new Date(demande.created_at))}
              </p>

              {demande.status === "approved" && demande.period_start && demande.period_end && (
                <p className="mt-2 rounded-lg bg-success-bg px-2 py-1.5 text-[10.5px] text-success sm:text-xs">
                  Du {dateLongue.format(new Date(demande.period_start))} au{" "}
                  {dateLongue.format(new Date(demande.period_end))}
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
                  Capture
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
  if (erreur) return <ErrorState>Impossible de charger les factures.</ErrorState>;
  if (!chargees) return <Skeleton rows={2} />;
  if (factures.length === 0) return <Vide>Une facture est émise à chaque paiement validé.</Vide>;

  return (
    <ul className="grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-3">
      {factures.map((facture) => {
        const retard = facture.is_overdue && facture.status === "issued";
        const etat = FACTURE[facture.status];
        return (
          <li key={facture.id} className="min-w-0">
            <Card padded={false} className="h-full p-3 sm:p-4">
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <span className="tabular text-sm font-semibold text-ink sm:text-base">
                  {montant(facture.amount, facture.currency)}
                </span>
                <Badge tone={retard ? "danger" : (etat?.tone ?? "neutral")}>
                  {retard ? "En retard" : (etat?.label ?? facture.status)}
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
                  ? `Réglée le ${dateLongue.format(new Date(facture.paid_at))}`
                  : `Émise le ${dateLongue.format(new Date(facture.issued_at))}`}
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

const QUESTIONS: { question: string; reponse: string }[] = [
  {
    question: "Quand ma période payée commence-t-elle ?",
    reponse:
      "À la suite de votre période en cours (essai ou mois payé), sans perdre un jour. Si votre période est déjà terminée, elle commence à la validation du paiement.",
  },
  {
    question: "Puis-je passer du mensuel à l'annuel ?",
    reponse:
      "Oui, à tout moment : choisissez l'offre annuelle et réglez-la. Votre année commence à la fin de votre mois en cours.",
  },
  {
    question: "Que se passe-t-il si je ne paie pas à temps ?",
    reponse:
      "Vous disposez de 3 jours de grâce. Ensuite, les réservations en ligne s'arrêtent et le tableau de bord passe en lecture seule — votre mini-site reste visible et vos données restent intactes. Tout se rouvre dès la validation de votre paiement.",
  },
  {
    question: "Recevrai-je un rappel avant l'échéance ?",
    reponse:
      "Oui, par e-mail : une semaine avant, trois jours avant et la veille (un mois avant pour l'offre annuelle), puis à chaque étape de votre paiement.",
  },
];

function Questions() {
  return (
    <div>
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.08em] text-subtle">
        Questions fréquentes
      </h2>
      <div className="grid gap-2 sm:grid-cols-2">
        {QUESTIONS.map((item) => (
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
