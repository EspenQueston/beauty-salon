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
 * question suivante — pourquoi — puis l'historique des mouvements.
 * Les écritures sont automatiques ; cet écran ne permet aucune saisie.
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

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { browserApi } from "@/lib/api";
import { isoDateIn } from "@/lib/format";
import {
  Badge,
  Card,
  ErrorState,
  GhostButton,
  PageHeader,
  SectionTitle,
  Skeleton,
} from "@/features/ui";
import { Reveal } from "@/features/ui/Reveal";
import { useToast } from "@/features/ui/Toast";
import { useDashboard } from "./DashboardShell";
import { useFormats } from "./formats";
import { Icon, type IconName } from "./icons";
import {
  DonutChart,
  MonthlyBars,
  useLibellePoste,
  type MonthPoint,
  type Slice,
} from "./charts";
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

/** Moyens et origines connus (`Transaction.Method`, `.Source`). */
const METHODES = ["cash", "mobile_money", "transfer", "card", "wechat", "alipay", "other"];
const SOURCES = [
  "manual",
  "booking_deposit",
  "booking_balance",
  "booking_items",
  "booking_travel",
  "subscription",
];

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
  { days: 30, cle: "j30", months: 2 },
  { days: 90, cle: "m3", months: 4 },
  { days: 365, cle: "m12", months: 12 },
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

/** Les formats de l'écran, dans la langue de l'espace (`region` : fr-FR, en-GB). */
function outils(region: string) {
  return {
    money(value: number | string, currency: string): string {
      return `${Number(value).toLocaleString(region, {
        maximumFractionDigits: 0,
      })} ${currency}`;
    },

    /** Abrège au-delà du millier : « 1 240 000 FCFA » déborde d'une carte de
     *  téléphone, « 1,2 M FCFA » se lit d'un coup d'œil. Le montant exact reste
     *  lisible dans la liste des mouvements. */
    compactMoney(value: number | string): string {
      const amount = Number(value);
      const absolute = Math.abs(amount);
      if (absolute >= 1_000_000)
        return `${(amount / 1_000_000).toLocaleString(region, {
          maximumFractionDigits: 1,
        })} M`;
      if (absolute >= 10_000)
        return `${Math.round(amount / 1000).toLocaleString(region)} k`;
      return amount.toLocaleString(region, { maximumFractionDigits: 0 });
    },

    monthName(iso: string): string {
      return new Intl.DateTimeFormat(region, { month: "short" }).format(
        new Date(`${iso}T00:00:00`),
      );
    },

    longMonth(iso: string): string {
      return new Intl.DateTimeFormat(region, {
        month: "long",
        year: "numeric",
      }).format(new Date(`${iso}T00:00:00`));
    },

    dayLabel(iso: string): string {
      return new Intl.DateTimeFormat(region, {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(new Date(`${iso}T00:00:00`));
    },
  };
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
  const t = useTranslations("pro.finances");
  const { region } = useFormats();
  const { money, compactMoney, monthName, longMonth, dayLabel } = useMemo(
    () => outils(region),
    [region],
  );
  const libellePoste = useLibellePoste();
  const { membership } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const currency = membership.tenant.currency;
  const timeZone = membership.tenant.timezone;

  const [window, setWindow] = useState(365);
  const [exporting, setExporting] = useState(false);

  const active = WINDOWS.find((option) => option.days === window) ?? WINDOWS[2];
  const against = t(`fenetres.${active.cle}.avant`);

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

      toast.success(t("exportOk"));
    } catch {
      toast.error(t("exportEchec"));
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
  const waiting = previous.error ? t("comparaisonIndisponible") : t("comparaisonEnCours");

  /* ----- Ce que les figures consomment ---------------------------------- */

  const months = useMemo(
    () => (data ? data.monthly.slice(-active.months) : []),
    [data, active.months],
  );

  const incomePoints: Point[] = months.map((point) => ({
    label: monthName(point.month),
    value: Number(point.income),
    title: t("points.recettes", { mois: longMonth(point.month), montant: money(point.income, currency) }),
  }));

  const expensePoints: Point[] = months.map((point) => ({
    label: monthName(point.month),
    value: Number(point.expense),
    title: t("points.depenses", { mois: longMonth(point.month), montant: money(point.expense, currency) }),
  }));

  const cumulativePoints: Point[] = months.map((point) => ({
    label: monthName(point.month),
    value: Number(point.cumulative),
    title: t("points.cumul", { mois: longMonth(point.month), montant: money(point.cumulative, currency) }),
  }));

  const bestMonth = months.reduce<MonthPoint | null>(
    (best, point) =>
      best === null || Number(point.income) > Number(best.income)
        ? point
        : best,
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
      label: libellePoste(slice),
      amount: money(slice.total, currency),
      share: total > 0 ? (Number(slice.total) / total) * 100 : 0,
    }));
  }, [data, currency, money, libellePoste]);

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
      meta: `${dayLabel(transaction.occurred_on)} · ${
        METHODES.includes(transaction.method)
          ? t(`methodes.${transaction.method}`)
          : transaction.method_label
      }`,
      amount: `${income ? "+" : "−"} ${money(transaction.amount, currency)}`,
      income,
      badge: transaction.source !== "manual" ? "auto" : undefined,
    };
  });

  return (
    <section>
      <PageHeader
        title={t("titre")}
        description={t("description")}
        action={
          <div className="flex flex-wrap gap-2">
            <GhostButton
              type="button"
              pending={exporting}
              onClick={() => void exportWorkbook()}
            >
              {t("exporter")}
            </GhostButton>

          </div>
        }
      />

      {summary.error && (
        <ErrorState>{t("erreur")}</ErrorState>
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
            {t(`fenetres.${option.cle}.libelle`)}
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
              label={t("cartes.resultat")}
              value={compactMoney(data.totals.net)}
              unit={currency}
              note={waiting}
              evolution={
                compared
                  ? change(data.totals.net, before?.net, against, "up")
                  : null
              }
            />
            <StatCard
              icon="trend"
              tone="success"
              label={t("cartes.recettes")}
              value={compactMoney(data.totals.income)}
              unit={currency}
              note={waiting}
              evolution={
                compared
                  ? change(
                      data.totals.income,
                      before?.income,
                      against,
                      "up",
                    )
                  : null
              }
            />
            <StatCard
              icon="receipt"
              tone="danger"
              label={t("cartes.depenses")}
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
                      against,
                      "down",
                    )
                  : null
              }
            />
            <StatCard
              icon="percent"
              tone="info"
              label={t("cartes.marge")}
              value={
                data.totals.margin === null ? "—" : `${data.totals.margin} %`
              }
              unit={
                data.totals.margin === null
                  ? t("cartes.aucuneRecette")
                  : t("cartes.deCeQuiRentre")
              }
              note={waiting}
              evolution={
                compared
                  ? marginChange(
                      data.totals.margin,
                      previous.data?.totals.margin,
                      against,
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
                title={t("figures.recettes")}
                subtitle={
                  bestMonth && Number(bestMonth.income) > 0
                    ? t("figures.meilleurMois", {
                        mois: longMonth(bestMonth.month),
                        montant: money(bestMonth.income, currency),
                      })
                    : t("figures.aucuneRecette")
                }
                foot={t("figures.mouvements", { n: data.totals.count })}
              >
                <GradientBars points={incomePoints} caption={t("figures.recettes")} />
              </ChartCard>
            </Reveal>

            <Reveal delay={90}>
              <ChartCard
                tone="success"
                title={t("figures.cumul")}
                subtitle={t("figures.cumulAide")}
                foot={
                  months.length > 0
                    ? t("figures.arreteA", { mois: longMonth(months[months.length - 1].month) })
                    : t("figures.aucunMois")
                }
              >
                <GradientLine points={cumulativePoints} caption={t("figures.cumulCourbe")} />
              </ChartCard>
            </Reveal>

            <Reveal delay={180} className="md:col-span-2 lg:col-span-1">
              <ChartCard
                tone="dark"
                title={t("figures.depenses")}
                subtitle={
                  expenseRows.length > 0
                    ? t("figures.posteLourd", {
                        poste: expenseRows[0].label,
                        montant: expenseRows[0].amount,
                      })
                    : t("figures.aucuneDepense")
                }
                foot={t("figures.postes", { n: expenseRows.length })}
              >
                <GradientLine points={expensePoints} caption={t("figures.depenses")} />
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
                title={t("ouPart")}
                lead={
                  <>
                    <Icon
                      name="check"
                      className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400"
                    />
                    <span>
                      {t.rich("depensesPeriode", {
                        montant: money(data.totals.expense, currency),
                        gras: (texte) => <strong className="font-semibold text-ink">{texte}</strong>,
                      })}
                    </span>
                  </>
                }
                className="h-full"
              >
                <ShareTable
                  rows={expenseRows}
                  empty={t("aucuneDepenseTableau")}
                />
              </BoardCard>
            </Reveal>

            <Reveal delay={120}>
              <BoardCard
                title={t("derniers")}
                lead={
                  <>
                    <Icon name="clock" className="size-3.5 shrink-0" />
                    <span>{t("plusRecents", { n: feed.length })}</span>
                  </>
                }
                className="h-full"
              >
                <Feed
                  items={feed}
                  empty={t("rienEncore")}
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
              <BoardCard title={t("dOuVient")} className="h-full">
                <DonutChart slices={data.income_slices} currency={currency} />
              </BoardCard>
            </Reveal>

            <Reveal delay={120} className="lg:col-span-2">
              <BoardCard
                title={t("coteACote")}
                lead={
                  <>
                    <Icon name="trend" className="size-3.5 shrink-0" />
                    <span>{t("ecart")}</span>
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

      <SectionTitle>{t("mouvements")}</SectionTitle>

      {list.data === null && !list.error && <Skeleton rows={3} />}

      {transactions.length === 0 && list.data !== null && (
        <Card>
          <p className="text-sm text-muted">
            {t("aucunMouvement")}
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
                        <Badge tone="neutral">
                          {SOURCES.includes(transaction.source)
                            ? t(`sources.${transaction.source}`)
                            : transaction.source_label}
                        </Badge>
                      )}
                    </p>
                    <p className="mt-0.5 text-sm text-muted">
                      {dayLabel(transaction.occurred_on)}
                      {" · "}
                      {libellePoste({
                        category: transaction.category,
                        label: transaction.category_label,
                      })}
                      {transaction.counterparty &&
                        ` · ${transaction.counterparty}`}
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
                      {Number(transaction.amount).toLocaleString(region)}{" "}
                      {currency}
                    </p>
                    <p className="text-xs text-subtle">
                      {METHODES.includes(transaction.method)
                        ? t(`methodes.${transaction.method}`)
                        : transaction.method_label}
                    </p>
                  </div>
                </div>

                {transaction.note && (
                  <p className="mt-2 border-l-2 border-line-strong pl-2 text-sm italic text-muted">
                    {transaction.note}
                  </p>
                )}

                <div className="mt-2.5 border-t border-line pt-2.5">
                  <p className="text-xs text-subtle">
                    {transaction.source === "manual" ? t("manuelle") : t("automatique")}
                  </p>
                </div>
              </Card>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
