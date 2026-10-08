"use client";

/**
 * Les trois façons de regarder un agenda.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi trois vues et pas une liste
 * ---------------------------------------------------------------------------
 *
 * Une liste répond à « qu'est-ce qui arrive ensuite ». Elle ne répond pas à
 * « ai-je de la place jeudi » ni à « quelle semaine est chargée » — et ce sont
 * ces deux questions-là qu'on pose à un agenda de salon quand une cliente est
 * au téléphone.
 *
 *   - **Jour** : la journée heure par heure. C'est la vue du matin, celle
 *     qu'on garde ouverte.
 *   - **Semaine** : sept colonnes côte à côte. C'est la vue qui montre les
 *     trous, donc celle qui sert à caser un rendez-vous.
 *   - **Mois** : la densité d'un coup d'œil. Elle ne montre pas les détails,
 *     elle montre où regarder ensuite.
 *
 * ---------------------------------------------------------------------------
 * Sur téléphone
 * ---------------------------------------------------------------------------
 *
 * Sept colonnes de 50 px ne sont lisibles sur aucun téléphone. La vue semaine
 * bascule donc en deux colonnes de journées empilées sous `lg`, ce qui garde
 * la comparaison entre jours voisins sans réduire le texte à l'illisible. Le
 * mois, lui, reste une grille 7×5 : c'est une carte de chaleur, pas un texte,
 * et elle se lit très bien en petit.
 */

import { useMemo } from "react";

import { formatTime } from "@/lib/format";
import { Icon } from "./icons";

export type AgendaView = "day" | "week" | "month";

export interface CalendarBooking {
  id: string;
  starts_at: string;
  ends_at: string;
  customer_name: string;
  service_name: string;
  staff_member_name: string;
  status: string;
}

/** Statuts qui occupent réellement le fauteuil. */
const ACTIVE = new Set(["requested", "confirmed", "checked_in", "completed"]);

const DAY_NAMES = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"];

const TONES: Record<string, string> = {
  requested: "border-l-amber-500 bg-amber-500/10",
  confirmed: "border-l-salon bg-salon-soft",
  checked_in: "border-l-sky-500 bg-sky-500/10",
  completed: "border-l-emerald-500 bg-emerald-500/10",
  cancelled: "border-l-line-strong bg-surface-muted",
  no_show: "border-l-red-500 bg-red-500/10",
};

/* --------------------------------------------------------------------------
 * Dates — tout est calculé sur des jours locaux, jamais sur des chaînes
 * ---------------------------------------------------------------------- */

export function startOfDay(date: Date): Date {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

/** Lundi de la semaine contenant `date`. La semaine française commence lundi. */
export function startOfWeek(date: Date): Date {
  const copy = startOfDay(date);
  const shift = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - shift);
  return copy;
}

export function startOfMonth(date: Date): Date {
  const copy = startOfDay(date);
  copy.setDate(1);
  return copy;
}

export function addDays(date: Date, count: number): Date {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + count);
  return copy;
}

/** Bornes chargées depuis l'API pour une vue donnée. */
export function rangeFor(
  view: AgendaView,
  anchor: Date,
): { from: Date; to: Date } {
  if (view === "day") {
    const from = startOfDay(anchor);
    return { from, to: addDays(from, 1) };
  }
  if (view === "week") {
    const from = startOfWeek(anchor);
    return { from, to: addDays(from, 7) };
  }
  // Le mois affiché déborde sur les semaines voisines : on charge la grille
  // entière, sinon les premières et dernières cases seraient vides à tort.
  const first = startOfMonth(anchor);
  const from = startOfWeek(first);
  return { from, to: addDays(from, 42) };
}

/** Clé de regroupement stable, insensible au fuseau d'affichage. */
function dayKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;
}

function groupByDay(
  bookings: CalendarBooking[],
): Map<string, CalendarBooking[]> {
  const map = new Map<string, CalendarBooking[]>();
  for (const booking of bookings) {
    const key = dayKey(new Date(booking.starts_at));
    const list = map.get(key);
    if (list) list.push(booking);
    else map.set(key, [booking]);
  }
  for (const list of map.values()) {
    list.sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  }
  return map;
}

/* --------------------------------------------------------------------------
 * Barre d'outils
 * ---------------------------------------------------------------------- */

export function AgendaToolbar({
  view,
  anchor,
  staffId,
  staff,
  timeZone,
  search,
  statusFilter,
  onView,
  onAnchor,
  onStaff,
  onSearch,
  onStatus,
}: {
  view: AgendaView;
  anchor: Date;
  staffId: string | null;
  staff: { id: string; name: string }[];
  timeZone: string;
  search: string;
  statusFilter: string;
  onView: (view: AgendaView) => void;
  onAnchor: (date: Date) => void;
  onStaff: (id: string | null) => void;
  onSearch: (value: string) => void;
  onStatus: (value: string) => void;
}) {
  const step = view === "day" ? 1 : view === "week" ? 7 : 0;

  function shift(direction: -1 | 1) {
    if (view === "month") {
      const next = startOfMonth(anchor);
      next.setMonth(next.getMonth() + direction);
      onAnchor(next);
      return;
    }
    onAnchor(addDays(anchor, step * direction));
  }

  const isToday =
    dayKey(startOfDay(new Date())) === dayKey(startOfDay(anchor)) &&
    view === "day";

  return (
    /*
      Deux rangées sur téléphone, une seule dès qu'il y a la place.
      
      Tout mettre sur une rangée qui se replie écrasait le libellé de période
      en une colonne d'un mot par ligne — la seule information de la barre
      qu'on lit vraiment, réduite à un accordéon.
    */
    <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      {/* Bascule de vue : trois segments, jamais un menu déroulant. On change
          de vue dix fois par jour, et un menu coûte deux gestes à chaque
          fois. */}
      <div
        role="tablist"
        aria-label="Affichage de l'agenda"
        className="flex rounded-lg border border-line bg-surface p-0.5"
      >
        {(
          [
            ["day", "Jour"],
            ["week", "Semaine"],
            ["month", "Mois"],
          ] as [AgendaView, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={view === key}
            onClick={() => onView(key)}
            className={`rounded-md px-3 py-1.5 text-sm transition ${
              view === key
                ? "bg-salon font-medium text-white"
                : "text-muted hover:text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex min-w-0 items-center gap-0.5">
        <button
          type="button"
          onClick={() => shift(-1)}
          aria-label="Période précédente"
          className="rounded-lg border border-line bg-surface p-2 text-muted transition hover:text-ink"
        >
          <Icon name="chevron-left" className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => onAnchor(startOfDay(new Date()))}
          disabled={isToday}
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-muted transition hover:text-ink disabled:opacity-50"
        >
          Aujourd&apos;hui
        </button>
        <button
          type="button"
          onClick={() => shift(1)}
          aria-label="Période suivante"
          className="rounded-lg border border-line bg-surface p-2 text-muted transition hover:text-ink"
        >
          <Icon name="chevron-right" className="size-4" />
        </button>

        <p
          aria-live="polite"
          className="min-w-0 flex-1 truncate pl-1.5 text-sm font-medium text-ink first-letter:uppercase"
        >
          {periodLabel(view, anchor, timeZone)}
        </p>
      </div>

      {/*
        Recherche et filtres, poussés à droite.

        -------------------------------------------------------------------
        Ce que la recherche fait à la période
        -------------------------------------------------------------------

        Elle la met en pause. Chercher « Chantal » et ne rien trouver parce
        qu'elle vient le mois prochain serait le contraire d'une recherche :
        dès qu'un terme est saisi, le serveur cherche sur tout l'agenda et
        l'écran passe en liste de résultats. Effacer le champ rend la
        semaine qu'on regardait.

        Le filtre de statut, lui, reste dans la période : « montre-moi les
        annulées » se pose toujours sur ce qu'on a sous les yeux.
      */}
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 sm:justify-end">
        <label className="relative min-w-0 flex-1 sm:max-w-56">
          <span className="sr-only">
            Rechercher une cliente ou une prestation
          </span>
          <Icon
            name="search"
            className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-subtle"
          />
          <input
            type="search"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Nom, téléphone, prestation"
            className="w-full rounded-lg border border-line bg-surface py-2 pl-8 pr-3 text-sm text-ink placeholder:text-subtle"
          />
        </label>

        <select
          value={statusFilter}
          onChange={(event) => onStatus(event.target.value)}
          aria-label="Filtrer par statut"
          className="min-w-0 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
        >
          <option value="">Tous les statuts</option>
          {STATUS_FILTERS.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label}
            </option>
          ))}
        </select>

        {/* Le filtre par prestataire n'apparaît qu'à partir de deux : sur un
            salon d'une personne, ce serait un champ qui ne filtre rien. */}
        {staff.length > 1 && (
          <select
            value={staffId ?? ""}
            onChange={(event) => onStaff(event.target.value || null)}
            aria-label="Filtrer par prestataire"
            className="min-w-0 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
          >
            <option value="">Toute l&apos;équipe</option>
            {staff.map((member) => (
              <option key={member.id} value={member.id}>
                {member.name}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}

/**
 * Les statuts proposés au filtre.
 *
 * Pas tous ceux du modèle : « en attente de paiement » et « demandée » sont
 * regroupés sous « à traiter », parce que c'est la même action côté salon —
 * regarder et trancher. Un filtre qui reproduit la machine à états oblige à
 * connaître la machine à états.
 */
const STATUS_FILTERS = [
  { value: "pending_payment,requested", label: "À traiter" },
  { value: "confirmed", label: "Confirmées" },
  { value: "checked_in", label: "Clientes arrivées" },
  { value: "completed", label: "Terminées" },
  { value: "cancelled", label: "Annulées" },
  { value: "no_show", label: "Absentes" },
];

function periodLabel(view: AgendaView, anchor: Date, timeZone: string): string {
  if (view === "day") {
    return new Intl.DateTimeFormat("fr-FR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      timeZone,
    }).format(anchor);
  }
  if (view === "week") {
    const from = startOfWeek(anchor);
    const to = addDays(from, 6);
    const short = new Intl.DateTimeFormat("fr-FR", {
      day: "numeric",
      month: "short",
    });
    return `${short.format(from)} – ${short.format(to)}`;
  }
  return new Intl.DateTimeFormat("fr-FR", {
    month: "long",
    year: "numeric",
  }).format(anchor);
}

/* --------------------------------------------------------------------------
 * Vue semaine
 * ---------------------------------------------------------------------- */

export function WeekView({
  anchor,
  bookings,
  timeZone,
  onPickDay,
}: {
  anchor: Date;
  bookings: CalendarBooking[];
  timeZone: string;
  onPickDay: (date: Date) => void;
}) {
  const first = startOfWeek(anchor);
  const byDay = useMemo(() => groupByDay(bookings), [bookings]);
  const todayKey = dayKey(startOfDay(new Date()));

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-7">
      {Array.from({ length: 7 }, (_, offset) => {
        const day = addDays(first, offset);
        const key = dayKey(day);
        const rows = byDay.get(key) ?? [];
        const active = rows.filter((row) => ACTIVE.has(row.status));

        return (
          <div
            key={key}
            className={`min-h-28 rounded-xl border p-2 ${
              key === todayKey
                ? "border-salon bg-salon-soft/40"
                : "border-line bg-surface"
            }`}
          >
            <button
              type="button"
              onClick={() => onPickDay(day)}
              className="mb-1.5 flex w-full items-baseline justify-between gap-1 text-left"
            >
              <span className="text-xs font-medium text-muted">
                {DAY_NAMES[offset]}
              </span>
              <span
                className={`tabular text-sm font-semibold ${
                  key === todayKey ? "text-salon" : "text-ink"
                }`}
              >
                {day.getDate()}
              </span>
            </button>

            {active.length === 0 ? (
              <p className="text-xs text-subtle">—</p>
            ) : (
              <ul className="space-y-1">
                {active.slice(0, 4).map((booking) => (
                  <li
                    key={booking.id}
                    className={`truncate rounded border-l-2 px-1.5 py-1 text-[0.7rem] leading-tight ${
                      TONES[booking.status] ?? "border-l-line bg-surface-muted"
                    }`}
                    title={`${booking.customer_name} · ${booking.service_name}`}
                  >
                    <span className="tabular font-medium text-ink">
                      {formatTime(booking.starts_at, timeZone)}
                    </span>{" "}
                    <span className="text-muted">{booking.customer_name}</span>
                  </li>
                ))}
                {active.length > 4 && (
                  <li className="px-1.5 text-[0.7rem] text-subtle">
                    +{active.length - 4} autre{active.length - 4 > 1 ? "s" : ""}
                  </li>
                )}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Vue mois
 * ---------------------------------------------------------------------- */

export function MonthView({
  anchor,
  bookings,
  onPickDay,
}: {
  anchor: Date;
  bookings: CalendarBooking[];
  onPickDay: (date: Date) => void;
}) {
  const first = startOfWeek(startOfMonth(anchor));
  const month = anchor.getMonth();
  const byDay = useMemo(() => groupByDay(bookings), [bookings]);
  const todayKey = dayKey(startOfDay(new Date()));

  // L'échelle de densité est relative au mois affiché : « chargé » ne veut
  // pas dire la même chose pour un salon d'une personne et pour une équipe
  // de six.
  const busiest = useMemo(() => {
    let most = 0;
    for (const rows of byDay.values()) {
      most = Math.max(
        most,
        rows.filter((row) => ACTIVE.has(row.status)).length,
      );
    }
    return most;
  }, [byDay]);

  return (
    <div>
      <div className="mb-1 grid grid-cols-7 gap-1">
        {DAY_NAMES.map((name) => (
          <span
            key={name}
            className="py-1 text-center text-[0.7rem] font-medium uppercase tracking-wide text-subtle"
          >
            {name}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: 42 }, (_, offset) => {
          const day = addDays(first, offset);
          const key = dayKey(day);
          const rows = byDay.get(key) ?? [];
          const count = rows.filter((row) => ACTIVE.has(row.status)).length;
          const outside = day.getMonth() !== month;

          return (
            <button
              key={key}
              type="button"
              onClick={() => onPickDay(day)}
              aria-label={`${day.getDate()} — ${count} rendez-vous`}
              className={`relative flex aspect-square flex-col items-center justify-center rounded-lg border text-sm transition sm:aspect-[4/3] ${
                key === todayKey
                  ? "border-salon"
                  : "border-line hover:border-line-strong"
              } ${outside ? "opacity-35" : ""}`}
              style={
                count > 0 && busiest > 0
                  ? {
                      // Un fond dont l'intensité suit la charge : la teinte du
                      // salon, jamais une couleur d'alerte — une journée
                      // pleine est une bonne nouvelle.
                      background: `color-mix(in srgb, var(--salon-primary) ${Math.round(
                        8 + (count / busiest) * 26,
                      )}%, transparent)`,
                    }
                  : undefined
              }
            >
              <span
                className={`tabular font-medium ${
                  key === todayKey ? "text-salon" : "text-ink"
                }`}
              >
                {day.getDate()}
              </span>
              {count > 0 && (
                <span className="tabular text-[0.65rem] text-muted">
                  {count} RDV
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
