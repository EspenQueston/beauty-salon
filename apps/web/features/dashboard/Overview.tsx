"use client";

/**
 * L'accueil de l'espace professionnel.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi l'agenda n'est plus la première chose
 * ---------------------------------------------------------------------------
 *
 * Il l'était, et c'était défendable : on ouvre son salon en regardant sa
 * journée. Mais l'agenda répond à « qui vient », jamais à « comment ça va » —
 * et la seconde question ne se posait nulle part. Un salon voyait passer ses
 * rendez-vous sans jamais voir ses recettes monter, ses notes, ni ce qu'on
 * lui réserve le plus.
 *
 * L'agenda reste à un clic, et la première carte de cette page dit déjà ce
 * qu'il y a aujourd'hui.
 *
 * ---------------------------------------------------------------------------
 * L'ordre de lecture
 * ---------------------------------------------------------------------------
 *
 *   1. **Ce qui attend un geste.** En premier quand il y en a, absent
 *      sinon. Ce sont les seules lignes qui coûtent quelque chose tant
 *      qu'on ne les traite pas.
 *   2. **Aujourd'hui.** Le nombre de rendez-vous, ce qu'ils représentent,
 *      et le prochain.
 *   3. **Le mois.** Recettes, et la comparaison avec le mois d'avant — un
 *      chiffre seul ne dit pas s'il est bon.
 *   4. **Le fond.** Prestations qui marchent, avis, remplissage.
 *
 * ---------------------------------------------------------------------------
 * Deux colonnes dès le téléphone
 * ---------------------------------------------------------------------------
 *
 * Les tuiles de chiffres sont des paires courtes. Sur une colonne, la moitié
 * de l'écran reste vide et il faut faire défiler quatre fois pour six
 * nombres. Deux colonnes les font tenir en un écran, ce qui est exactement
 * l'usage : on ouvre cette page pour un coup d'œil, pas pour une lecture.
 */

import Link from "next/link";

import { Card, ErrorState, Skeleton } from "@/features/ui";
import { formatPrice } from "@/lib/format";

import { useDashboard } from "./DashboardShell";
import { Icon, type IconName } from "./icons";
import { SetupChecklist } from "./SetupChecklist";
import { useResource } from "./useResource";

interface Overview {
  currency: string;
  today: {
    count: number;
    revenue: string;
    next: {
      at: string;
      service_name: string;
      customer_name: string;
    } | null;
  };
  attention: { deposits: number; requests: number; overdue: number };
  month: { income: string; previous_income: string; growth: number | null };
  counters: {
    customers: number;
    bookings: number;
    average_basket: string | null;
    reviews: number;
    rating: number | null;
  };
  top_services: { name: string; count: number; revenue: string }[];
  ratings: { rating: number; count: number }[];
  feed: { kind: string; at: string; title: string; detail: string }[];
  occupancy: number | null;
}

/** Ce qui attend un geste, et où aller le faire. */
const TASKS: {
  key: keyof Overview["attention"];
  href: string;
  one: string;
  many: string;
}[] = [
  {
    key: "deposits",
    href: "/agenda",
    one: "acompte à vérifier",
    many: "acomptes à vérifier",
  },
  {
    key: "requests",
    href: "/agenda",
    one: "demande à accepter",
    many: "demandes à accepter",
  },
  {
    key: "overdue",
    href: "/agenda",
    one: "créneau passé à trancher",
    many: "créneaux passés à trancher",
  },
];

export function Overview() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const { data, error } = useResource<Overview>("/api/v1/overview", tenantId);

  if (error) return <ErrorState>{error}</ErrorState>;
  if (!data) return <Skeleton rows={6} />;

  const { currency, today, attention, month, counters } = data;
  const pending = TASKS.map((task) => ({
    ...task,
    count: attention[task.key],
  })).filter((task) => task.count > 0);

  return (
    <div className="space-y-5">
      <SetupChecklist />

      {/* ----- 1. Ce qui attend ---------------------------------------- */}
      {pending.length > 0 && (
        <Card className="border-l-4 border-l-warning">
          <p className="text-sm font-semibold text-ink">À traiter</p>
          <ul className="mt-2.5 grid gap-2 sm:grid-cols-3">
            {pending.map((task) => (
              <li key={task.key}>
                <Link
                  href={task.href}
                  className="flex items-baseline gap-2 rounded-lg px-2 py-1.5 transition hover:bg-surface-hover"
                >
                  <span className="tabular text-xl font-semibold text-warning">
                    {task.count}
                  </span>
                  <span className="text-sm text-muted">
                    {task.count > 1 ? task.many : task.one}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* ----- 2. Aujourd'hui, et le mois ------------------------------ */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Highlight
          label="Aujourd'hui"
          value={String(today.count)}
          unit={today.count > 1 ? "rendez-vous" : "rendez-vous"}
          icon="calendar"
          filled
          footer={
            today.next ? (
              <>
                Prochain : <strong>{today.next.service_name}</strong> —{" "}
                {today.next.customer_name} à{" "}
                {new Intl.DateTimeFormat("fr-FR", {
                  hour: "2-digit",
                  minute: "2-digit",
                }).format(new Date(today.next.at))}
              </>
            ) : today.count > 0 ? (
              "Tous les rendez-vous du jour sont passés."
            ) : (
              "Aucun rendez-vous aujourd'hui."
            )
          }
        />

        <Highlight
          label="Recettes du mois"
          value={formatPrice(month.income, currency)}
          icon="wallet"
          footer={
            month.growth === null ? (
              // Une croissance depuis zéro n'est pas un pourcentage : on
              // donne le mois précédent en clair plutôt qu'un « +100 % »
              // inventé.
              <>
                Mois précédent : {formatPrice(month.previous_income, currency)}
              </>
            ) : (
              <span
                className={month.growth >= 0 ? "text-success" : "text-danger"}
              >
                {month.growth >= 0 ? "+" : ""}
                {month.growth} % par rapport au mois précédent
              </span>
            )
          }
        />
      </div>

      {/* ----- 3. Les compteurs de fond -------------------------------- */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile
          icon="users"
          label="Clientes"
          value={String(counters.customers)}
        />
        <Tile
          icon="calendar"
          label="RDV sur 30 j"
          value={String(counters.bookings)}
        />
        <Tile
          icon="trend"
          label="Panier moyen"
          value={
            counters.average_basket
              ? formatPrice(counters.average_basket, currency)
              : "—"
          }
        />
        <Tile
          icon="star"
          label="Note moyenne"
          value={counters.rating !== null ? `${counters.rating}/5` : "—"}
          hint={
            counters.reviews > 0
              ? `${counters.reviews} avis`
              : "Aucun avis publié"
          }
        />
      </div>

      {/* ----- 4. Le détail -------------------------------------------- */}
      <div className="grid gap-5 lg:grid-cols-2">
        <TopServices rows={data.top_services} currency={currency} />
        <Ratings rows={data.ratings} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Occupancy value={data.occupancy} />
        <Feed entries={data.feed} />
      </div>
    </div>
  );
}

/**
 * Les deux chiffres du haut.
 *
 * L'un est rempli de la couleur du salon, l'autre non. Ce n'est pas une
 * alternance décorative : le rempli est celui qu'on vient chercher — la
 * journée du jour —, et le contraste le désigne sans qu'on ait à lire les
 * deux étiquettes pour trancher.
 */
function Highlight({
  label,
  value,
  unit,
  icon,
  footer,
  filled = false,
}: {
  label: string;
  value: string;
  unit?: string;
  icon: IconName;
  footer: React.ReactNode;
  filled?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl p-5 shadow-card ${
        filled
          ? "salon-gradient text-white"
          : "border border-line bg-surface text-ink"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <p
          className={`text-sm font-medium ${
            filled ? "text-white/85" : "text-muted"
          }`}
        >
          {label}
        </p>
        <Icon
          name={icon}
          className={`size-5 shrink-0 ${
            filled ? "text-white/70" : "text-subtle"
          }`}
        />
      </div>

      <p className="tabular mt-2 flex flex-wrap items-baseline gap-x-2 text-2xl font-semibold tracking-tight sm:text-3xl">
        {value}
        {unit && (
          <span
            className={`text-sm font-normal ${
              filled ? "text-white/80" : "text-muted"
            }`}
          >
            {unit}
          </span>
        )}
      </p>

      <p className={`mt-2 text-sm ${filled ? "text-white/85" : "text-muted"}`}>
        {footer}
      </p>
    </div>
  );
}

function Tile({
  icon,
  label,
  value,
  hint,
}: {
  icon: IconName;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    // L'icône passe en haut à droite, et non devant le libellé : à deux
    // colonnes sur un écran de 375 px, une tuile fait 160 px de large, et une
    // icône en tête y ampute le libellé de trois mots — « Panier moyen »
    // devenait « Panier mo… ». À droite, elle ne vole rien à personne.
    <Card className="min-w-0">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-sm leading-snug text-muted">{label}</p>
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-salon-soft">
          <Icon name={icon} className="size-4 text-salon" />
        </span>
      </div>
      <p className="tabular mt-1.5 text-xl font-semibold tracking-tight text-ink sm:text-2xl">
        {value}
      </p>
      {hint && (
        <p className="mt-0.5 text-xs leading-snug text-subtle">{hint}</p>
      )}
    </Card>
  );
}

/**
 * Les prestations les plus réservées.
 *
 * Classées sur les rendez-vous **honorés ou confirmés**, jamais sur les
 * demandes : une prestation qu'on réserve puis qu'on annule n'est pas une
 * prestation qui marche, et la faire remonter conduirait le salon à en
 * commander les fournitures.
 */
function TopServices({
  rows,
  currency,
}: {
  rows: { name: string; count: number; revenue: string }[];
  currency: string;
}) {
  if (rows.length === 0) {
    return (
      <Card>
        <p className="text-sm font-semibold text-ink">Prestations du mois</p>
        <p className="mt-2 text-sm text-muted">
          Aucun rendez-vous honoré sur les 30 derniers jours.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <p className="text-sm font-semibold text-ink">
        Prestations les plus réservées
      </p>
      <p className="mt-0.5 text-xs text-subtle">Sur les 30 derniers jours</p>

      <ul className="mt-3 divide-y divide-line">
        {rows.map((row) => (
          <li
            key={row.name}
            className="flex items-baseline justify-between gap-3 py-2.5"
          >
            <span className="min-w-0 flex-1 truncate text-sm text-ink">
              {row.name}
            </span>
            <span className="tabular shrink-0 text-sm text-muted">
              {row.count}×
            </span>
            <span className="tabular shrink-0 text-sm font-medium text-ink">
              {formatPrice(row.revenue, currency)}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/**
 * La répartition des notes, pas seulement la moyenne.
 *
 * Une moyenne de 4 recouvre aussi bien « tout le monde est content » que
 * « la moitié adore et l'autre déteste ». Ces deux salons n'ont pas le même
 * problème, et un seul chiffre les confond.
 */
function Ratings({ rows }: { rows: { rating: number; count: number }[] }) {
  const total = rows.reduce((sum, row) => sum + row.count, 0);

  if (total === 0) {
    return (
      <Card>
        <p className="text-sm font-semibold text-ink">Avis des clientes</p>
        <p className="mt-2 text-sm text-muted">
          Aucun avis publié pour l&apos;instant. Ils arrivent tout seuls :
          chaque cliente en reçoit la proposition après sa visite.
        </p>
      </Card>
    );
  }

  // Des barres plutôt qu'un anneau. Cinq parts dont deux souvent minuscules
  // ne se distinguent pas sur un disque, et l'ordre — de 5 à 1 — est ce
  // qu'on lit en premier : il se voit sur une colonne, pas sur un cercle.
  const highest = Math.max(...rows.map((row) => row.count));

  return (
    <Card>
      <p className="text-sm font-semibold text-ink">Avis des clientes</p>
      <p className="mt-0.5 text-xs text-subtle">
        {total} avis publié{total > 1 ? "s" : ""}
      </p>

      <ul className="mt-3 space-y-2">
        {rows.map((row) => (
          <li key={row.rating} className="flex items-center gap-2.5">
            <span className="tabular w-8 shrink-0 text-sm text-muted">
              {row.rating}/5
            </span>
            <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-muted">
              {row.count > 0 && (
                <span
                  className="salon-gradient block h-full rounded-full"
                  style={{
                    width: `${Math.max(4, (row.count / highest) * 100)}%`,
                  }}
                />
              )}
            </span>
            <span className="tabular w-6 shrink-0 text-right text-sm text-ink">
              {row.count}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/**
 * Le taux de remplissage.
 *
 * Le chiffre qui manquait le plus : un salon peut avoir beaucoup de
 * rendez-vous et une journée vide, ou peu de rendez-vous mais longs et
 * remplir sa semaine. Le nombre de réservations ne répond pas à « est-ce
 * que je travaille assez ».
 */
function Occupancy({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <Card>
        <p className="text-sm font-semibold text-ink">Remplissage</p>
        <p className="mt-2 text-sm text-muted">
          Déclarez vos horaires d&apos;ouverture pour connaître la part de vos
          heures réellement occupées.
        </p>
        <Link
          href="/horaires"
          className="mt-3 inline-flex text-sm font-medium text-salon hover:underline"
        >
          Poser mes horaires
        </Link>
      </Card>
    );
  }

  return (
    <Card>
      <p className="text-sm font-semibold text-ink">Remplissage</p>
      <p className="mt-0.5 text-xs text-subtle">Sur les 7 derniers jours</p>

      <p className="tabular mt-3 text-3xl font-semibold tracking-tight text-ink">
        {value} %
      </p>

      <div
        role="img"
        aria-label={`${value} % des heures d'ouverture occupées`}
        className="mt-2.5 h-2.5 overflow-hidden rounded-full bg-surface-muted"
      >
        <span
          className="salon-gradient block h-full rounded-full"
          style={{ width: `${Math.max(2, value)}%` }}
        />
      </div>

      <p className="mt-2 text-sm text-muted">
        {value >= 80
          ? "Vos journées sont pleines. C'est le moment d'ouvrir des créneaux, ou d'ajuster vos tarifs."
          : value >= 40
            ? "Un rythme confortable : il reste de la place pour de nouvelles clientes."
            : "Beaucoup d'heures ouvertes restent libres. Une promotion ou un rappel à vos habituées les remplirait."}
      </p>
    </Card>
  );
}

const FEED_ICONS: Record<string, IconName> = {
  booking: "calendar",
  review: "star",
  payment: "wallet",
};

/** Ce qui s'est passé, du plus récent au plus ancien. */
function Feed({
  entries,
}: {
  entries: { kind: string; at: string; title: string; detail: string }[];
}) {
  if (entries.length === 0) {
    return (
      <Card>
        <p className="text-sm font-semibold text-ink">Activité</p>
        <p className="mt-2 text-sm text-muted">
          Rien ne s&apos;est passé sur les 30 derniers jours.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <p className="text-sm font-semibold text-ink">Activité</p>

      <ul className="mt-3 divide-y divide-line">
        {entries.map((entry) => (
          <li key={`${entry.kind}-${entry.at}`} className="flex gap-3 py-2.5">
            <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-salon-soft">
              <Icon
                name={FEED_ICONS[entry.kind] ?? "calendar"}
                className="size-4 text-salon"
              />
            </span>

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-ink">{entry.title}</p>
              {entry.detail && (
                <p className="truncate text-xs text-subtle">{entry.detail}</p>
              )}
            </div>

            <span className="shrink-0 text-xs text-subtle">
              {ago(entry.at)}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/**
 * « à l'instant », « il y a 3 h », « il y a 5 j ».
 *
 * Un délai se comprend là où une date se lit. Sur un fil d'activité, c'est
 * la fraîcheur qui compte, pas le jour exact.
 */
function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);

  if (minutes < 2) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  return `il y a ${Math.round(hours / 24)} j`;
}
