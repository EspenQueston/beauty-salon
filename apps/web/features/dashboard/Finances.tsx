"use client";

/**
 * Les comptes du salon : ce qui rentre, ce qui sort, ce qu'il reste.
 *
 * ---------------------------------------------------------------------------
 * L'ordre de la page n'est pas décoratif
 * ---------------------------------------------------------------------------
 *
 * On ouvre cet écran pour une seule question : « qu'est-ce qu'il me reste ce
 * mois-ci ». Le résultat est donc le premier chiffre, en grand, avant tout
 * graphique. Les figures viennent ensuite parce qu'elles répondent à la
 * question *suivante* — pourquoi — et la saisie en dernier, parce qu'on la
 * fait le soir, pas en arrivant.
 *
 * ---------------------------------------------------------------------------
 * Ce qui se remplit tout seul
 * ---------------------------------------------------------------------------
 *
 * Chaque prestation marquée « terminée » crée sa recette. Un cahier de
 * comptes qu'il faut remplir deux fois n'est jamais rempli, et un salon qui
 * ouvre cet écran le premier jour doit déjà y voir ses chiffres — sinon il
 * ne revient pas.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi cet écran ne ressemble pas aux autres
 * ---------------------------------------------------------------------------
 *
 * C'est le seul de l'espace où l'on vient lire plutôt qu'agir. Sa mise en
 * page — pastilles de couleur qui débordent, panneaux de graphiques, tableau
 * à barres, fil des derniers mouvements — vient de `board.tsx` et ne sert
 * qu'ici : sur l'agenda ou la fiche d'une cliente, un aplat de couleur en
 * tête de carte repousserait le bouton qu'on est venue chercher.
 *
 * ---------------------------------------------------------------------------
 * La comparaison est mesurée, pas devinée
 * ---------------------------------------------------------------------------
 *
 * Les quatre chiffres portent une évolution. Elle n'est pas tirée des douze
 * seaux mensuels — sur une fenêtre de 30 jours, onze d'entre eux sont vides
 * et la comparaison ne voudrait rien dire. Elle vient d'un second appel sur
 * la **période précédente de même longueur** : 30 jours se comparent aux 30
 * jours d'avant, 12 mois aux 12 mois d'avant.
 */

import { useMemo, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { browserApi } from "@/lib/api";
import { isoDateIn } from "@/lib/format";
import {
  Badge,
  Button,
  Card,
  ErrorState,
  GhostButton,
  PageHeader,
  SectionTitle,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { Reveal } from "@/features/ui/Reveal";
import { useToast } from "@/features/ui/Toast";
import { useDashboard } from "./DashboardShell";
import { Icon, type IconName } from "./icons";
import { DonutChart, MonthlyBars, type MonthPoint, type Slice } from "./charts";
import {
  BoardCard,
  ChartCard,
  Feed,
  GradientBars,
  GradientLine,
  ShareTable,
  StatCard,
  type Evolution,
  type FeedItem,
  type Point,
  type ShareRow,
  type Tone,
} from "./board";
import { rows, useResource, type Page } from "./useResource";

interface Transaction {
  id: string;
  kind: "income" | "expense";
  category: string;
  category_label: string;
  label: string;
  amount: string;
  occurred_on: string;
  method: string;
  method_label: string;
  counterparty: string;
  note: string;
  source: "manual" | "booking_deposit" | "booking_balance" | "subscription";
  source_label: string;
  from_booking: boolean;
}

interface Summary {
  currency: string;
  from: string;
  to: string;
  totals: {
    income: string;
    expense: string;
    net: string;
    margin: number | null;
    count: number;
  };
  monthly: MonthPoint[];
  expense_by_category: Slice[];
  income_by_category: Slice[];
  income_slices: Slice[];
}

const INCOME_CATEGORIES = [
  { value: "service", label: "Prestation" },
  { value: "product", label: "Vente de produit" },
  { value: "travel", label: "Déplacement" },
  { value: "tip", label: "Pourboire" },
  { value: "other_income", label: "Autre recette" },
];

const EXPENSE_CATEGORIES = [
  { value: "supplies", label: "Fournitures et produits" },
  { value: "rent", label: "Loyer" },
  { value: "wages", label: "Salaires" },
  { value: "utilities", label: "Eau, électricité, internet" },
  { value: "transport", label: "Transport et déplacements" },
  { value: "marketing", label: "Publicité" },
  { value: "equipment", label: "Matériel" },
  { value: "taxes", label: "Taxes et impôts" },
  { value: "other_expense", label: "Autre dépense" },
];

const METHODS = [
  { value: "cash", label: "Espèces" },
  { value: "mobile_money", label: "Mobile Money" },
  { value: "transfer", label: "Virement" },
  { value: "card", label: "Carte" },
  { value: "wechat", label: "WeChat Pay" },
  { value: "other", label: "Autre" },
];

/**
 * Une icône par poste.
 *
 * Dans un tableau de dix lignes, l'icône est ce qui permet de retrouver
 * « Loyer » sans lire les dix libellés. Elle ne remplace jamais le texte,
 * qui reste la seule chose que lit un lecteur d'écran.
 */
const CATEGORY_ICONS: Record<string, IconName> = {
  service: "sparkles",
  product: "bag",
  // Le même camion que la dépense « Transport et déplacements », en face.
  // C'est le rapprochement des deux lignes qui dit si un forfait de zone
  // couvre ce qu'il coûte.
  travel: "truck",
  tip: "star",
  other_income: "wallet",
  supplies: "bag",
  rent: "store",
  wages: "users",
  utilities: "bolt",
  transport: "truck",
  marketing: "megaphone",
  equipment: "tool",
  taxes: "percent",
  other_expense: "receipt",
  __other__: "grid",
};

function categoryIcon(category: string, income: boolean): IconName {
  return CATEGORY_ICONS[category] ?? (income ? "wallet" : "receipt");
}

/**
 * Fenêtres proposées.
 *
 * `months` borne les graphiques : sur 30 jours, afficher douze seaux
 * mensuels dont onze sont vides donne une figure plate qui laisse croire à
 * un salon à l'arrêt. `against` nomme la période de comparaison en toutes
 * lettres — « +12 % » sans dire par rapport à quoi n'est pas un chiffre.
 */
const WINDOWS = [
  { days: 30, label: "30 jours", months: 2, against: "les 30 jours d'avant" },
  { days: 90, label: "3 mois", months: 4, against: "les 3 mois d'avant" },
  { days: 365, label: "12 mois", months: 12, against: "les 12 mois d'avant" },
];

/*
  Les bornes de la fenêtre se calculent dans le fuseau du salon.

  Elles étaient calculées en UTC, et c'est ce qui faisait disparaître des
  recettes. À Shanghai il est 1 h du matin le 16 quand UTC est encore au 15 :
  la borne « jusqu'à aujourd'hui » valait alors le 15, et une prestation
  terminée le 16 tombait hors de la fenêtre. Huit heures par nuit, l'écran
  des comptes affichait un total amputé — sans rien signaler, puisque de son
  point de vue la ligne n'existait pas.

  Voir `isoDateIn` : le raisonnement complet y est.
*/

function money(value: number | string, currency: string): string {
  return `${Number(value).toLocaleString("fr-FR", {
    maximumFractionDigits: 0,
  })} ${currency}`;
}

/** Abrège au-delà du millier : « 1 240 000 FCFA » déborde d'une carte de
 *  téléphone, « 1,2 M FCFA » se lit d'un coup d'œil. Le montant exact reste
 *  lisible dans la liste des mouvements. */
function compactMoney(value: number | string): string {
  const amount = Number(value);
  const absolute = Math.abs(amount);
  if (absolute >= 1_000_000)
    return `${(amount / 1_000_000).toLocaleString("fr-FR", {
      maximumFractionDigits: 1,
    })} M`;
  if (absolute >= 10_000)
    return `${Math.round(amount / 1000).toLocaleString("fr-FR")} k`;
  return amount.toLocaleString("fr-FR", { maximumFractionDigits: 0 });
}

function monthName(iso: string): string {
  return new Intl.DateTimeFormat("fr-FR", { month: "short" }).format(
    new Date(`${iso}T00:00:00`),
  );
}

function longMonth(iso: string): string {
  return new Intl.DateTimeFormat("fr-FR", {
    month: "long",
    year: "numeric",
  }).format(new Date(`${iso}T00:00:00`));
}

function dayLabel(iso: string): string {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${iso}T00:00:00`));
}

/**
 * Variation entre deux périodes de même longueur.
 *
 * `null` quand la période de référence est vide : zéro divisé par zéro ne
 * vaut pas « 0 % », il ne vaut pas de réponse. Écrire « +100 % » parce qu'on
 * est passé de rien à quelque chose serait une invention.
 */
function change(
  current: number | string,
  previous: number | string | undefined,
  against: string,
  good: "up" | "down",
): Evolution {
  const now = Number(current);
  const before = Number(previous);
  if (!Number.isFinite(before) || before === 0) {
    return { percent: null, against, good };
  }
  return { percent: ((now - before) / Math.abs(before)) * 100, against, good };
}

/** Une marge gagne des **points**, pas des pourcents : de 10 % à 13 %, elle
 *  prend 3 points — dire « +30 % » ferait croire à une marge de 13 fois. */
function marginChange(
  current: number | null,
  previous: number | null | undefined,
  against: string,
): Evolution {
  if (current === null || previous === null || previous === undefined) {
    return { percent: null, against, good: "up", unit: "pts" };
  }
  return { percent: current - previous, against, good: "up", unit: "pts" };
}

export function Finances() {
  const { membership } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const currency = membership.tenant.currency;
  const timeZone = membership.tenant.timezone;

  const [window, setWindow] = useState(365);
  const [adding, setAdding] = useState<"income" | "expense" | null>(null);
  const [exporting, setExporting] = useState(false);

  const active = WINDOWS.find((option) => option.days === window) ?? WINDOWS[2];

  const range = useMemo(
    () => `from=${isoDateIn(timeZone, -window)}&to=${isoDateIn(timeZone)}`,
    [window, timeZone],
  );

  /*
    La période précédente, de longueur identique et sans recouvrement : elle
    s'arrête la veille du jour où commence la période affichée. Un jour de
    chevauchement serait compté des deux côtés et gonflerait la comparaison.
  */
  const previousRange = useMemo(
    () =>
      `from=${isoDateIn(timeZone, -window * 2)}&to=${isoDateIn(timeZone, -(window + 1))}`,
    [window, timeZone],
  );

  const summary = useResource<Summary>(
    `/api/v1/transactions/summary/?${range}`,
    tenantId,
  );
  const previous = useResource<Summary>(
    `/api/v1/transactions/summary/?${previousRange}`,
    tenantId,
  );
  const list = useResource<Page<Transaction>>(
    `/api/v1/transactions/?${range}&page_size=50`,
    tenantId,
  );

  function reload() {
    summary.reload();
    previous.reload();
    list.reload();
  }

  async function remove(transaction: Transaction) {
    /*
      Une ligne automatique ne se supprime pas à la légère.

      Elle constate de l'argent réellement entré ou sorti — un acompte
      encaissé, un abonnement réglé. L'effacer ne défait pas l'encaissement,
      elle fausse seulement la caisse. Le geste qui corrige un acompte est
      « Corriger » dans l'agenda, pas « Supprimer » ici.
    */
    if (transaction.source !== "manual") {
      const origin =
        transaction.source === "subscription"
          ? "Cette ligne suit une facture d'abonnement réglée."
          : "Cette ligne suit un encaissement enregistré dans l'agenda.";
      toast.error(`${origin} Corrigez-la à sa source plutôt qu'ici.`);
      return;
    }

    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/transactions/${transaction.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: "Ligne supprimée." },
    );
    if (ok) reload();
  }

  /**
   * Téléchargement du classeur.
   *
   * Passe par un blob plutôt que par un lien direct : la requête doit porter
   * la session et l'en-tête de salon, ce qu'un `<a href>` ne fait pas.
   */
  async function exportWorkbook() {
    setExporting(true);
    try {
      const response = await fetch(
        `${browserApi()}/api/v1/transactions/export/?${range}`,
        { credentials: "include", headers: { "X-Tenant-Id": tenantId } },
      );
      if (!response.ok) throw new Error("Export impossible.");

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download =
        response.headers
          .get("Content-Disposition")
          ?.match(/filename="([^"]+)"/)?.[1] ?? "comptes.xlsx";
      link.click();
      URL.revokeObjectURL(url);

      toast.success("Classeur téléchargé : une feuille par sens.");
    } catch {
      toast.error("Export impossible pour le moment.");
    } finally {
      setExporting(false);
    }
  }

  const data = summary.data;
  const before = previous.data?.totals;
  const transactions = rows(list.data);

  /*
    Tant que la période de référence n'est pas revenue, aucune évolution
    n'est affichée — pas même « rien à comparer ».

    Sans ce garde-fou, les quatre cartes annoncent d'abord qu'il n'y a rien à
    comparer, puis se corrigent une demi-seconde plus tard. Un chiffre qui se
    dément tout seul sous les yeux de la gérante coûte plus cher en confiance
    que la demi-seconde gagnée.
  */
  const compared = previous.data !== null;
  const waiting = previous.error
    ? "comparaison indisponible"
    : "comparaison en cours…";

  /* ----- Ce que les figures consomment ---------------------------------- */

  const months = useMemo(
    () => (data ? data.monthly.slice(-active.months) : []),
    [data, active.months],
  );

  const incomePoints: Point[] = months.map((point) => ({
    label: monthName(point.month),
    value: Number(point.income),
    title: `${longMonth(point.month)} : ${money(point.income, currency)} de recettes`,
  }));

  const expensePoints: Point[] = months.map((point) => ({
    label: monthName(point.month),
    value: Number(point.expense),
    title: `${longMonth(point.month)} : ${money(point.expense, currency)} de dépenses`,
  }));

  const cumulativePoints: Point[] = months.map((point) => ({
    label: monthName(point.month),
    value: Number(point.cumulative),
    title: `Fin ${longMonth(point.month)} : ${money(point.cumulative, currency)} cumulés`,
  }));

  const bestMonth = months.reduce<MonthPoint | null>(
    (best, point) =>
      best === null || Number(point.income) > Number(best.income) ? point : best,
    null,
  );

  const expenseRows: ShareRow[] = useMemo(() => {
    if (!data) return [];
    const total = data.expense_by_category.reduce(
      (sum, slice) => sum + Number(slice.total),
      0,
    );
    return data.expense_by_category.map((slice) => ({
      key: slice.category,
      icon: categoryIcon(slice.category, false),
      tone: "dark" as Tone,
      label: slice.label,
      amount: money(slice.total, currency),
      share: total > 0 ? (Number(slice.total) / total) * 100 : 0,
    }));
  }, [data, currency]);

  /* Les six derniers mouvements, du plus récent au plus ancien. Six parce
     que le fil accompagne le tableau à sa droite et doit tenir la même
     hauteur que lui — au-delà, il l'allonge sans rien apprendre. */
  const feed: FeedItem[] = transactions.slice(0, 6).map((transaction) => {
    const income = transaction.kind === "income";
    return {
      id: transaction.id,
      icon: categoryIcon(transaction.category, income),
      tone: income ? "success" : "danger",
      title: transaction.label,
      meta: `${dayLabel(transaction.occurred_on)} · ${transaction.method_label}`,
      amount: `${income ? "+" : "−"} ${money(transaction.amount, currency)}`,
      income,
      badge: transaction.source !== "manual" ? "auto" : undefined,
    };
  });

  return (
    <section>
      <PageHeader
        title="Comptes"
        description="Ce qui rentre, ce qui sort, ce qu'il vous reste."
        action={
          <div className="flex flex-wrap gap-2">
            <GhostButton
              type="button"
              pending={exporting}
              onClick={() => void exportWorkbook()}
            >
              Exporter en Excel
            </GhostButton>
            <Button
              type="button"
              icon={<Icon name="plus" className="size-4" />}
              onClick={() => setAdding("expense")}
            >
              Saisir
            </Button>
          </div>
        }
      />

      {summary.error && (
        <ErrorState>Impossible de charger vos comptes.</ErrorState>
      )}

      <div className="mb-5 flex rounded-xl border border-line bg-surface p-1 shadow-card">
        {WINDOWS.map((option) => (
          <button
            key={option.days}
            type="button"
            aria-pressed={window === option.days}
            onClick={() => setWindow(option.days)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm transition ${
              window === option.days
                ? "salon-gradient font-medium text-white shadow-sm"
                : "text-muted hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {data === null && !summary.error && <Skeleton rows={4} />}

      {data && (
        <>
          {/*
            1 — Les quatre chiffres.

            `mt-10` réserve la place que les pastilles prennent au-dessus de
            leur carte : sans cette marge, la première rangée mordrait sur le
            sélecteur de période.
          */}
          <Reveal className="mb-6 mt-10 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <StatCard
              icon="wallet"
              tone="dark"
              label="Résultat"
              value={compactMoney(data.totals.net)}
              unit={currency}
              note={waiting}
              evolution={
                compared
                  ? change(data.totals.net, before?.net, active.against, "up")
                  : null
              }
            />
            <StatCard
              icon="trend"
              tone="success"
              label="Recettes"
              value={compactMoney(data.totals.income)}
              unit={currency}
              note={waiting}
              evolution={
                compared
                  ? change(data.totals.income, before?.income, active.against, "up")
                  : null
              }
            />
            <StatCard
              icon="receipt"
              tone="danger"
              label="Dépenses"
              value={compactMoney(data.totals.expense)}
              unit={currency}
              note={waiting}
              // Des dépenses qui montent ne sont pas une bonne nouvelle : la
              // flèche et la couleur doivent le dire, sinon la carte félicite
              // le salon de dépenser plus.
              evolution={
                compared
                  ? change(
                      data.totals.expense,
                      before?.expense,
                      active.against,
                      "down",
                    )
                  : null
              }
            />
            <StatCard
              icon="percent"
              tone="info"
              label="Marge"
              value={
                data.totals.margin === null ? "—" : `${data.totals.margin} %`
              }
              unit={data.totals.margin === null ? "aucune recette" : "de ce qui rentre"}
              note={waiting}
              evolution={
                compared
                  ? marginChange(
                      data.totals.margin,
                      previous.data?.totals.margin,
                      active.against,
                    )
                  : null
              }
            />
          </Reveal>

          {/*
            2 — Les trois figures.

            Une série par panneau, volontairement : un graphique en couleur
            pleine ne peut pas porter deux légendes lisibles. La comparaison
            recettes/dépenses a sa propre carte plus bas, sur fond clair et
            avec son axe.

            Une colonne sur téléphone, et c'est la seule entorse à la règle
            des deux colonnes : douze abréviations de mois dans 170 pixels ne
            se lisent plus.
          */}
          <div className="mb-6 mt-10 grid gap-5 sm:gap-4 md:grid-cols-2 lg:mt-12 lg:grid-cols-3">
            <Reveal>
              <ChartCard
                tone="salon"
                title="Recettes mois par mois"
                subtitle={
                  bestMonth && Number(bestMonth.income) > 0
                    ? `Meilleur mois : ${longMonth(bestMonth.month)}, ${money(
                        bestMonth.income,
                        currency,
                      )}.`
                    : "Aucune recette enregistrée sur la période."
                }
                foot={`${data.totals.count} mouvement${
                  data.totals.count > 1 ? "s" : ""
                } sur la période`}
              >
                <GradientBars
                  points={incomePoints}
                  caption="Recettes mois par mois"
                />
              </ChartCard>
            </Reveal>

            <Reveal delay={90}>
              <ChartCard
                tone="success"
                title="Résultat cumulé"
                subtitle="Ce qu'il reste une fois tous les mois additionnés — la courbe qui dit si vous remontez la pente."
                foot={
                  months.length > 0
                    ? `arrêté à ${longMonth(months[months.length - 1].month)}`
                    : "aucun mois à afficher"
                }
              >
                <GradientLine
                  points={cumulativePoints}
                  caption="Résultat cumulé mois par mois"
                />
              </ChartCard>
            </Reveal>

            <Reveal delay={180} className="md:col-span-2 lg:col-span-1">
              <ChartCard
                tone="dark"
                title="Dépenses mois par mois"
                subtitle={
                  expenseRows.length > 0
                    ? `Poste le plus lourd : ${expenseRows[0].label}, ${expenseRows[0].amount}.`
                    : "Aucune dépense enregistrée sur la période."
                }
                foot={`${expenseRows.length} poste${
                  expenseRows.length > 1 ? "s" : ""
                } de dépense`}
              >
                <GradientLine
                  points={expensePoints}
                  caption="Dépenses mois par mois"
                />
              </ChartCard>
            </Reveal>
          </div>

          {/*
            3 — Où part l'argent, et ce qui vient de se passer.

            Côte à côte parce qu'on les lit ensemble : le tableau dit la
            structure des dépenses, le fil dit ce qui l'a fait bouger hier.
          */}
          <div className="mb-6 grid gap-5 lg:grid-cols-3">
            <Reveal className="lg:col-span-2">
              <BoardCard
                title="Où part l'argent"
                lead={
                  <>
                    <Icon
                      name="check"
                      className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400"
                    />
                    <span>
                      <strong className="font-semibold text-ink">
                        {money(data.totals.expense, currency)}
                      </strong>{" "}
                      de dépenses sur la période
                    </span>
                  </>
                }
                className="h-full"
              >
                <ShareTable
                  rows={expenseRows}
                  empty="Aucune dépense enregistrée sur la période. Saisissez-en une pour voir vos postes se classer ici."
                />
              </BoardCard>
            </Reveal>

            <Reveal delay={120}>
              <BoardCard
                title="Derniers mouvements"
                lead={
                  <>
                    <Icon name="clock" className="size-3.5 shrink-0" />
                    <span>les {feed.length} plus récents</span>
                  </>
                }
                className="h-full"
              >
                <Feed
                  items={feed}
                  empty="Rien encore. Les prestations que vous marquez « terminée » apparaîtront ici toutes seules."
                />
              </BoardCard>
            </Reveal>
          </div>

          {/*
            4 — Les deux figures qui demandent un axe.

            Sur fond clair, elles : l'anneau a besoin de trois teintes
            distinctes et les barres groupées d'une échelle chiffrée — deux
            choses qu'un panneau de couleur pleine ne permet pas.
          */}
          <div className="mb-6 grid gap-5 lg:grid-cols-3">
            <Reveal>
              <BoardCard title="D'où vient l'argent" className="h-full">
                <DonutChart slices={data.income_slices} currency={currency} />
              </BoardCard>
            </Reveal>

            <Reveal delay={120} className="lg:col-span-2">
              <BoardCard
                title="Recettes et dépenses, côte à côte"
                lead={
                  <>
                    <Icon name="trend" className="size-3.5 shrink-0" />
                    <span>c&apos;est l&apos;écart entre les deux qui compte</span>
                  </>
                }
                className="h-full"
              >
                <MonthlyBars points={months} currency={currency} />
              </BoardCard>
            </Reveal>
          </div>
        </>
      )}

      {adding && (
        <TransactionForm
          tenantId={tenantId}
          currency={currency}
          timeZone={timeZone}
          kind={adding}
          onKind={setAdding}
          onClose={() => setAdding(null)}
          onSaved={() => {
            setAdding(null);
            reload();
          }}
        />
      )}

      <SectionTitle>Mouvements</SectionTitle>

      {list.data === null && !list.error && <Skeleton rows={3} />}

      {transactions.length === 0 && list.data !== null && (
        <Card>
          <p className="text-sm text-muted">
            Aucun mouvement sur la période. Les prestations que vous marquez
            « terminée » apparaîtront ici automatiquement.
          </p>
        </Card>
      )}

      <ul className="space-y-2">
        {transactions.map((transaction) => {
          const income = transaction.kind === "income";
          return (
            <li key={transaction.id}>
              <Card>
                <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2">
                      <span
                        aria-hidden
                        className="size-2.5 shrink-0 rounded-sm"
                        style={{
                          background: income
                            ? "var(--viz-income)"
                            : "var(--viz-expense)",
                        }}
                      />
                      <span className="min-w-0 truncate font-medium text-ink">
                        {transaction.label}
                      </span>
                      {/* Une ligne que le salon n'a pas saisie se signale :
                          sans cela il cherche qui l'a écrite, ou pire, la
                          supprime en croyant à une erreur. */}
                      {transaction.source !== "manual" && (
                        <Badge tone="neutral">{transaction.source_label}</Badge>
                      )}
                    </p>
                    <p className="mt-0.5 text-sm text-muted">
                      {dayLabel(transaction.occurred_on)}
                      {" · "}
                      {transaction.category_label}
                      {transaction.counterparty && ` · ${transaction.counterparty}`}
                    </p>
                  </div>

                  <div className="text-right">
                    {/* Le signe est écrit, pas seulement coloré : une couleur
                        seule ne dit pas le sens à tout le monde. */}
                    <p
                      className={`tabular font-semibold ${
                        income ? "text-emerald-600" : "text-ink"
                      }`}
                    >
                      {income ? "+" : "−"}{" "}
                      {Number(transaction.amount).toLocaleString("fr-FR")}{" "}
                      {currency}
                    </p>
                    <p className="text-xs text-subtle">
                      {transaction.method_label}
                    </p>
                  </div>
                </div>

                {transaction.note && (
                  <p className="mt-2 border-l-2 border-line-strong pl-2 text-sm italic text-muted">
                    {transaction.note}
                  </p>
                )}

                <div className="mt-2.5 border-t border-line pt-2.5">
                  {transaction.source === "manual" ? (
                    <button
                      type="button"
                      onClick={() => remove(transaction)}
                      className="text-xs text-danger underline-offset-2 hover:underline"
                    >
                      Supprimer
                    </button>
                  ) : (
                    <p className="text-xs text-subtle">
                      Enregistrée automatiquement — se corrige à sa source.
                    </p>
                  )}
                </div>
              </Card>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/**
 * Saisie d'un mouvement.
 *
 * Le sens se choisit en premier parce qu'il change tout le reste : les postes
 * d'une recette ne sont pas ceux d'une dépense. Le proposer après aurait
 * obligé à vider le champ précédent à chaque bascule.
 *
 * La date vaut aujourd'hui par défaut : c'est le cas dans la quasi-totalité
 * des saisies, et une date à remplir à chaque ligne est ce qui fait
 * abandonner un cahier de comptes.
 */
function TransactionForm({
  tenantId,
  currency,
  timeZone,
  kind,
  onKind,
  onClose,
  onSaved,
}: {
  tenantId: string;
  currency: string;
  /** Le fuseau du salon : « aujourd.hui » est le sien, pas celui du poste. */
  timeZone: string;
  kind: "income" | "expense";
  onKind: (kind: "income" | "expense") => void;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const categories = kind === "income" ? INCOME_CATEGORIES : EXPENSE_CATEGORIES;

  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState(categories[0].value);
  const [occurredOn, setOccurredOn] = useState(isoDateIn(timeZone));
  const [method, setMethod] = useState("cash");
  const [counterparty, setCounterparty] = useState("");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);

  function switchKind(next: "income" | "expense") {
    onKind(next);
    setCategory(
      (next === "income" ? INCOME_CATEGORIES : EXPENSE_CATEGORIES)[0].value,
    );
  }

  async function submit(event: { preventDefault: () => void }) {
    event.preventDefault();
    if (!label.trim() || !amount) return;

    setPending(true);
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/transactions/",
          {
            method: "POST",
            body: JSON.stringify({
              kind,
              category,
              label: label.trim(),
              amount,
              occurred_on: occurredOn,
              method,
              counterparty: counterparty.trim(),
              note: note.trim(),
            }),
          },
          tenantId,
        ),
      {
        success:
          kind === "income" ? "Recette enregistrée." : "Dépense enregistrée.",
      },
    );
    setPending(false);
    if (ok) onSaved();
  }

  return (
    <Card className="mb-6">
      <SectionTitle>Nouveau mouvement</SectionTitle>

      <div className="mb-4 flex rounded-lg border border-line bg-surface p-0.5">
        {(
          [
            ["expense", "Dépense"],
            ["income", "Recette"],
          ] as ["income" | "expense", string][]
        ).map(([value, text]) => (
          <button
            key={value}
            type="button"
            aria-pressed={kind === value}
            onClick={() => switchKind(value)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm transition ${
              kind === value
                ? "bg-salon font-medium text-white"
                : "text-muted hover:text-ink"
            }`}
          >
            <span
              aria-hidden
              className="size-2.5 rounded-sm"
              style={{
                background:
                  value === "income" ? "var(--viz-income)" : "var(--viz-expense)",
              }}
            />
            {text}
          </button>
        ))}
      </div>

      {/* Deux colonnes dès le téléphone pour les champs courts : un
          formulaire qui paraît long fait renoncer avant la première frappe. */}
      <div
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void submit(event);
          }
        }}
        className="grid grid-cols-2 gap-3"
      >
        <label className="col-span-2 block">
          <span className="mb-1 block text-xs text-muted">
            {kind === "income" ? "De quoi s'agit-il" : "C'était pour quoi"}
          </span>
          <input
            autoFocus
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder={
              kind === "income" ? "Vente de mèches" : "Mèches kanekalon"
            }
            className={inputClass}
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs text-muted">
            Montant ({currency})
          </span>
          <input
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            inputMode="decimal"
            placeholder="0"
            className={`${inputClass} tabular`}
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs text-muted">Date</span>
          <input
            value={occurredOn}
            onChange={(event) => setOccurredOn(event.target.value)}
            type="date"
            max={isoDateIn(timeZone)}
            className={inputClass}
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs text-muted">Poste</span>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className={inputClass}
          >
            {categories.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-xs text-muted">Moyen</span>
          <select
            value={method}
            onChange={(event) => setMethod(event.target.value)}
            className={inputClass}
          >
            {METHODS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="col-span-2 block">
          <span className="mb-1 block text-xs text-muted">
            {kind === "income" ? "De qui" : "À qui"} (facultatif)
          </span>
          <input
            value={counterparty}
            onChange={(event) => setCounterparty(event.target.value)}
            placeholder={kind === "income" ? "Nom de la cliente" : "Fournisseur"}
            className={inputClass}
          />
        </label>

        <label className="col-span-2 block">
          <span className="mb-1 block text-xs text-muted">
            Détail (facultatif)
          </span>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={2}
            className={inputClass}
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          type="button"
          pending={pending}
          disabled={!label.trim() || !amount}
          onClick={(event) => void submit(event)}
        >
          Enregistrer
        </Button>
        <GhostButton type="button" onClick={onClose}>
          Annuler
        </GhostButton>
      </div>
    </Card>
  );
}
