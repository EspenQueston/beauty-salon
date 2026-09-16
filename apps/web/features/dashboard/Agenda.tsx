"use client";

/**
 * Agenda du salon.
 *
 * L'écran qu'on ouvre le matin. Il répond à trois questions dans cet ordre :
 * qui vient aujourd'hui, qu'est-ce qui demande une action, et qu'est-ce qui
 * arrive ensuite. Les rendez-vous sont donc groupés par jour, et chaque carte
 * ne porte que les actions possibles à cet instant précis.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { formatDate, formatDayKey, formatPrice, formatTime } from "@/lib/format";
import { useNow } from "@/lib/useNow";
import {
  Badge,
  Button,
  Card,
  DangerButton,
  EmptyState,
  ErrorState,
  GhostButton,
  PageHeader,
  Skeleton,
  StatTile,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { Icon } from "./icons";
import {
  AgendaToolbar,
  MonthView,
  WeekView,
  rangeFor,
  startOfDay,
  type AgendaView,
} from "./AgendaCalendar";
import { rows as pageRows, useResource, type Page } from "./useResource";
import { BookingProgress } from "./BookingProgress";
import { CheckInButton, CheckInPanel } from "./CheckIn";
import { useDashboard } from "./DashboardShell";

interface Booking {
  id: string;
  starts_at: string;
  ends_at: string;
  status: string;
  service_name: string;
  staff_member_name: string;
  customer_name: string;
  customer_phone: string;
  total_amount: string;
  deposit_amount: string;
  deposit_paid: boolean;
  deposit_method: string;
  deposit_received: string;
  deposit_proof: {
    status: string;
    channel: string;
    reference: string;
    note: string;
    image_url: string;
    submitted_at: string;
    rejection_reason: string;
  } | null;
  options_snapshot: { name: string; price: string; minutes: number }[];
  options_amount: string;
  location_mode: string;
  address: string;
  travel_zone_name: string;
  travel_fee_amount: string;
  customer_note: string;
}

interface Summary {
  currency: string;
  late_tolerance_minutes: number;
  upcoming_count: number;
  today_count: number;
  no_show_last_30_days: number;
  cancelled_last_30_days: number;
}

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const STATUS: Record<string, { label: string; tone: Tone }> = {
  pending_payment: { label: "En attente de paiement", tone: "warning" },
  requested: { label: "Demandée", tone: "warning" },
  confirmed: { label: "Confirmée", tone: "success" },
  checked_in: { label: "Cliente arrivée", tone: "info" },
  completed: { label: "Terminée", tone: "neutral" },
  cancelled: { label: "Annulée", tone: "danger" },
  no_show: { label: "Absente", tone: "danger" },
};

/** Actions proposées selon l'état courant du rendez-vous. */
const NEXT_ACTIONS: Record<string, { status: string; label: string }[]> = {
  requested: [
    { status: "confirmed", label: "Confirmer" },
    { status: "checked_in", label: "Cliente arrivée" },
  ],
  confirmed: [
    { status: "checked_in", label: "Cliente arrivée" },
    { status: "no_show", label: "Absente" },
  ],
  checked_in: [{ status: "completed", label: "Terminée" }],
};

export function Agenda() {
  const { membership } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const timeZone = membership.tenant.timezone;
  const currency = membership.tenant.currency;

  const now = useNow();

  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [view, setView] = useState<AgendaView>("week");
  const [anchor, setAnchor] = useState(() => startOfDay(new Date()));
  const [staffId, setStaffId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  /* Le rendez-vous dont on est en train de vérifier l'arrivée, s'il y en a
     un : le lecteur s'ouvre alors ciblé sur lui. */
  const [arrival, setArrival] = useState<Booking | null>(null);

  /*
   * La recherche attend qu'on ait fini de taper.
   *
   * Sans ce délai, « Chantal » part en sept requêtes dont six sont périmées
   * avant d'arriver. 300 ms : assez pour couvrir une frappe normale, assez
   * court pour que le résultat paraisse immédiat.
   */
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const searching = debounced.length > 0;

  // L'équipe alimente le filtre. Chargée une fois, pas à chaque changement
  // de période : elle ne dépend pas de la date affichée.
  const team = useResource<Page<{ id: string; name: string }>>(
    "/api/v1/staff-members/?page_size=100",
    tenantId,
  );

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;

    const { from, to } = rangeFor(view, anchor);

    // Les filtres partent au serveur plutôt que d'être appliqués après coup :
    // une vue mois sur une équipe de six ramènerait six fois trop de lignes
    // pour n'en afficher qu'un sixième.
    //
    // Pendant une recherche, la période saute : on cherche une personne, pas
    // une semaine. C'est la seule chose qui change, et elle change ici — le
    // reste de l'écran ne sait pas qu'il y a deux modes.
    const params = new URLSearchParams({ page_size: "300" });
    if (searching) {
      params.set("search", debounced);
    } else {
      params.set("from", from.toISOString());
      params.set("to", to.toISOString());
    }
    if (staffId) params.set("staff_member", staffId);
    if (statusFilter) params.set("status", statusFilter);

    Promise.all([
      dashboardFetch<{ results: Booking[] }>(
        `/api/v1/bookings/?${params}`,
        {},
        tenantId,
      ),
      dashboardFetch<Summary>("/api/v1/bookings/summary/", {}, tenantId),
    ])
      .then(([page, stats]) => {
        if (cancelled) return;
        setBookings(page.results);
        setSummary(stats);
        setError(null);
      })
      .catch(() => {
        if (!cancelled) setError("Impossible de charger l’agenda.");
      });

    return () => {
      cancelled = true;
    };
  }, [
    view,
    anchor,
    staffId,
    statusFilter,
    searching,
    debounced,
    tenantId,
    reloadToken,
  ]);

  async function changeStatus(booking: Booking, status: string) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/bookings/${booking.id}/status/`,
          { method: "POST", body: JSON.stringify({ status }) },
          tenantId,
        ),
      {
        success: `${booking.customer_name} — ${(STATUS[status]?.label ?? status).toLowerCase()}.`,
      },
    );
    if (ok) reload();
  }

  /**
   * Accepter : l'acompte est arrivé **et** la prestation est assurable.
   *
   * Les deux en un geste, volontairement. Les séparer permettrait
   * d'encaisser pour un créneau qu'on ne peut pas tenir — la pire issue
   * pour la cliente, qui a payé et n'aura rien.
   */
  async function acceptBooking(booking: Booking, amount?: string) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/bookings/${booking.id}/accept/`,
          {
            method: "POST",
            body: JSON.stringify(amount ? { amount } : {}),
          },
          tenantId,
        ),
      { success: `Rendez-vous de ${booking.customer_name} confirmé.` },
    );
    if (ok) reload();
  }

  async function rejectProof(booking: Booking, reason: string) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/bookings/${booking.id}/deposit/reject/`,
          { method: "POST", body: JSON.stringify({ reason }) },
          tenantId,
        ),
      { success: "La cliente est prévenue et peut renvoyer une preuve." },
    );
    if (ok) reload();
  }

  async function cancel(booking: Booking) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/bookings/${booking.id}/cancel/`,
          { method: "POST", body: JSON.stringify({ reason: "Annulé par le salon" }) },
          tenantId,
        ),
      { success: `Rendez-vous de ${booking.customer_name} annulé.` },
    );
    if (ok) reload();
  }

  const grouped = useMemo(() => {
    if (!bookings) return [];
    const map = new Map<string, Booking[]>();
    for (const booking of bookings) {
      const key = formatDayKey(booking.starts_at, timeZone);
      map.set(key, [...(map.get(key) ?? []), booking]);
    }
    return [...map.entries()];
  }, [bookings, timeZone]);

  const tolerance = summary?.late_tolerance_minutes ?? 15;

  /*
   * Qui est en retard, à cette minute.
   *
   * Recalculé à chaque battement d'horloge plutôt que stocké : un retard
   * n'est pas un état du rendez-vous, c'est une lecture de l'heure. Le figer
   * obligerait à le corriger à chaque changement de statut, et à recharger la
   * page pour le voir vieillir.
   */
  const late = useMemo(() => {
    const found = new Map<string, LateState>();
    for (const booking of bookings ?? []) {
      const state = lateState(booking, now, tolerance);
      if (state) found.set(booking.id, state);
    }
    return found;
  }, [bookings, now, tolerance]);

  const waiting = [...late.values()].filter((state) => !state.overdue).length;
  const unresolved = [...late.values()].filter((state) => state.overdue).length;

  return (
    <section>
      <PageHeader
        title="Agenda"
        description="Vos rendez-vous à venir, et ce qui demande une action."
        // L'arrivée se scanne depuis l'agenda plutôt que depuis une rubrique
        // à part : c'est l'écran déjà ouvert quand une cliente pousse la
        // porte, et la ligne qui change d'état est juste en dessous.
        action={<CheckInButton tenantId={tenantId} onCheckedIn={reload} />}
      />

      {summary && (
        <div className="mb-7 grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-4">
          <StatTile label="Aujourd’hui" value={summary.today_count} hint="rendez-vous" />
          <StatTile
            label="7 prochains jours"
            value={summary.upcoming_count}
            hint="rendez-vous actifs"
          />
          <StatTile
            label="Absences"
            value={summary.no_show_last_30_days}
            hint="sur 30 jours"
            tone={summary.no_show_last_30_days > 0 ? "danger" : "neutral"}
          />
          <StatTile
            label="Annulations"
            value={summary.cancelled_last_30_days}
            hint="sur 30 jours"
          />
        </div>
      )}

      <AgendaToolbar
        view={view}
        anchor={anchor}
        staffId={staffId}
        staff={pageRows(team.data)}
        timeZone={timeZone}
        search={search}
        statusFilter={statusFilter}
        onView={setView}
        onAnchor={setAnchor}
        onStaff={setStaffId}
        onSearch={setSearch}
        onStatus={setStatusFilter}
      />

      {/* Pendant une recherche, le calendrier n'a plus de sens : les
          résultats viennent de toute la durée de vie du salon, pas de la
          semaine affichée. On le dit, et on donne le chemin du retour. */}
      {searching && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface-muted px-4 py-2.5">
          <p className="text-sm text-muted">
            {bookings === null
              ? "Recherche…"
              : `${bookings.length} résultat${bookings.length > 1 ? "s" : ""} pour « ${search.trim()} », sur tout l'agenda.`}
          </p>
          <button
            type="button"
            onClick={() => setSearch("")}
            className="ml-auto rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink transition hover:bg-surface-hover"
          >
            Revenir à l&apos;agenda
          </button>
        </div>
      )}

      {/* Bandeau vivant : il n'existe que tant qu'il y a quelque chose à
          faire, et il disparaît de lui-même dès que c'est réglé. */}
      {(waiting > 0 || unresolved > 0) && (
        <LateBanner
          waiting={waiting}
          unresolved={unresolved}
          tolerance={tolerance}
        />
      )}

      {error && <ErrorState>{error}</ErrorState>}
      {bookings === null && !error && <Skeleton rows={4} />}

      {bookings?.length === 0 && (
        <EmptyState title="Aucun rendez-vous sur cette période">
          Partagez le lien de votre mini-site pour que vos clientes réservent
          elles-mêmes, à toute heure.
        </EmptyState>
      )}

      {/*
        Semaine et mois montrent la forme de la période ; jour montre le
        détail. Les cartes complètes — statuts, acompte, notes — restent
        réservées au jour et à la semaine dépliée : les afficher dans une
        grille mensuelle donnerait un mur illisible.
      */}
      {view === "month" && !searching && bookings && (
        <MonthView
          anchor={anchor}
          bookings={bookings}
          onPickDay={(day) => {
            setAnchor(day);
            setView("day");
          }}
        />
      )}

      {view === "week" && !searching && bookings && (
        <div className="mb-7">
          <WeekView
            anchor={anchor}
            bookings={bookings}
            timeZone={timeZone}
            onPickDay={(day) => {
              setAnchor(day);
              setView("day");
            }}
          />
        </div>
      )}

      <div className={`space-y-7 ${view === "month" && !searching ? "hidden" : ""}`}>
        {grouped.map(([day, rows]) => (
          <div key={day}>
            <h2 className="mb-2.5 text-sm font-medium text-muted first-letter:uppercase">
              {formatDate(rows[0].starts_at, timeZone)}
            </h2>

            <ul className="space-y-2.5">
              {rows.map((booking) => {
                const status = STATUS[booking.status] ?? {
                  label: booking.status,
                  tone: "neutral" as Tone,
                };

                return (
                  <li key={booking.id}>
                    <Card>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="tabular text-sm font-semibold text-ink">
                            {formatTime(booking.starts_at, timeZone)} –{" "}
                            {formatTime(booking.ends_at, timeZone)}
                          </p>
                          <p className="mt-1 text-base font-medium text-ink">
                            {booking.service_name}
                          </p>
                          <p className="mt-0.5 text-sm text-muted">
                            {booking.customer_name} · {booking.customer_phone}
                          </p>
                          <p className="mt-0.5 text-sm text-subtle">
                            avec {booking.staff_member_name}
                          </p>
                        </div>

                        {/* Sur mobile, statut et montant tiennent sur une
                            ligne pleine largeur : empilés, ils se retrouvaient
                            alignés sur la largeur du plus long des deux, donc
                            ni à gauche ni à droite. */}
                        <div className="flex w-full items-center justify-between gap-2 sm:w-auto sm:flex-col sm:items-end">
                          {/* Le retard remplace le statut plutôt que de s'y
                              ajouter : « Confirmée » à côté de « en retard de
                              20 min » se contredisent à l'œil, et c'est le
                              retard qui demande une décision. */}
                          {late.has(booking.id) ? (
                            <LateBadge state={late.get(booking.id)!} />
                          ) : (
                            <Badge tone={status.tone}>{status.label}</Badge>
                          )}
                          <span className="tabular text-sm font-medium text-ink">
                            {formatPrice(booking.total_amount, currency)}
                          </span>
                        </div>
                      </div>

                      {/* Les options changent ce qu'il faut préparer et
                          combien de temps le fauteuil est pris. Elles sont
                          donc sur la carte, pas dans une fiche à ouvrir. */}
                      {booking.options_snapshot?.length > 0 && (
                        <ul className="mt-3 flex flex-wrap gap-1.5">
                          {booking.options_snapshot.map((option) => (
                            <li
                              key={option.name}
                              className="inline-flex items-center gap-1.5 rounded-full bg-surface-muted px-2.5 py-1 text-xs text-ink"
                            >
                              {option.name}
                              {option.minutes > 0 && (
                                <span className="tabular text-subtle">
                                  +{option.minutes} min
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}

                      {/* Un rendez-vous à domicile se prépare autrement : il
                          faut partir plus tôt et savoir où aller. L'adresse
                          est donc sur la carte, pas dans une fiche à
                          ouvrir. */}
                      {booking.travel_zone_name && (
                        <TravelLine booking={booking} currency={currency} />
                      )}

                      {booking.customer_note && (
                        <p className="mt-3 rounded-lg bg-surface-muted p-3 text-sm text-ink">
                          « {booking.customer_note} »
                        </p>
                      )}

                      {/* Où en est-on avec cette cliente. Une position sur
                          un chemin dit ce qui reste à faire ; une pastille,
                          non. */}
                      <BookingProgress
                        status={booking.status}
                        hasDeposit={Number(booking.deposit_amount) > 0}
                      />

                      {/* La preuve passe avant tout le reste : c'est la
                          seule chose de cette carte qui bloque quelqu'un. */}
                      {booking.deposit_proof && (
                        <ProofPanel
                          booking={booking}
                          currency={currency}
                          onAccept={acceptBooking}
                          onReject={rejectProof}
                        />
                      )}

                      {Number(booking.deposit_amount) > 0 && (
                        <DepositLine
                          booking={booking}
                          currency={currency}
                        />
                      )}

                      <div className="mt-4 flex flex-wrap gap-2">
                        {(NEXT_ACTIONS[booking.status] ?? []).map((action) =>
                          /*
                            « Cliente arrivée » n'écrit plus directement : il
                            ouvre le lecteur, sur *cette* ligne.

                            Le clic seul se faisait de mémoire — à midi, avec
                            quatre clientes dans le salon, on notait l'arrivée
                            sur la mauvaise ligne et l'agenda mentait jusqu'au
                            soir. C'est la cliente qui porte la preuve de sa
                            présence ; le salon la lit.

                            Le geste direct n'a pas disparu pour autant : il
                            est au bas du lecteur, pour la cliente qui n'a pas
                            son code.
                          */
                          action.status === "checked_in" ? (
                            <Button
                              key={action.status}
                              type="button"
                              icon={<Icon name="scan" className="size-4" />}
                              onClick={() => setArrival(booking)}
                            >
                              {action.label}
                            </Button>
                          ) : (
                            <GhostButton
                              key={action.status}
                              type="button"
                              onClick={() => changeStatus(booking, action.status)}
                            >
                              {action.label}
                            </GhostButton>
                          ),
                        )}
                        {!["cancelled", "completed"].includes(booking.status) && (
                          <DangerButton type="button" onClick={() => cancel(booking)}>
                            Annuler
                          </DangerButton>
                        )}
                      </div>
                    </Card>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      {/*
        Le lecteur, ouvert sur une ligne précise.

        Monté au niveau de la page et non dans la carte : il se superpose à
        tout l'écran, et le laisser naître à l'intérieur d'une carte le
        rendrait tributaire des marges et du défilement de cette carte.
      */}
      {arrival && (
        <CheckInPanel
          tenantId={tenantId}
          target={{
            id: arrival.id,
            customer_name: arrival.customer_name,
            service_name: arrival.service_name,
            starts_at: arrival.starts_at,
          }}
          onCheckedIn={reload}
          onSkip={() => {
            void changeStatus(arrival, "checked_in");
            setArrival(null);
          }}
          onClose={() => setArrival(null)}
        />
      )}
    </section>
  );
}

/**
 * Où en est l'acompte de ce rendez-vous.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi il n'y a plus de saisie manuelle ici
 * ---------------------------------------------------------------------------
 *
 * Il y avait un bouton « Noter un encaissement » qui ouvrait un formulaire :
 * montant, moyen de paiement, confirmation. Il faisait doublon avec la seule
 * chose qui compte vraiment — « J'ai reçu l'acompte », sur la preuve envoyée
 * par la cliente — et deux chemins vers la même écriture comptable, c'est
 * une caisse qui finit par compter deux fois le même versement.
 *
 * Il ne reste donc qu'un état, lisible d'un coup d'œil : attendu, ou reçu.
 * L'écriture se fait là où le salon vérifie réellement le versement.
 */
function DepositLine({
  booking,
  currency,
}: {
  booking: Booking;
  currency: string;
}) {
  const expected = formatPrice(booking.deposit_amount, currency);

  // ----- déjà encaissé ---------------------------------------------------
  if (booking.deposit_paid) {
    const received = Number(booking.deposit_received ?? 0);
    const short = received > 0 && received < Number(booking.deposit_amount);

    return (
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg bg-success-bg px-3 py-2">
        <p className="flex items-center gap-2 text-sm text-success">
          <Icon name="check" className="size-4 shrink-0" />
          <span>
            {received > 0
              ? formatPrice(booking.deposit_received, currency)
              : expected}{" "}
            encaissé
          </span>
        </p>

        {/* Un versement partiel se voit : c'est le reste à percevoir le jour
            du rendez-vous. */}
        {short && (
          <Badge tone="warning">
            reste {formatPrice(Number(booking.deposit_amount) - received, currency)}
          </Badge>
        )}

      </div>
    );
  }

  // ----- en attente ------------------------------------------------------
  return (
    <div className="mt-3 rounded-lg bg-warning-bg px-3 py-2">
      <p className="text-sm font-medium text-warning">
        Acompte de {expected} attendu
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------
 * Retard
 * ---------------------------------------------------------------------- */

/** Statuts pour lesquels un retard a un sens : la cliente n'est pas encore là. */
const AWAITING = ["requested", "confirmed"];

interface LateState {
  /** Minutes écoulées depuis l'heure prévue. */
  minutes: number;
  /** Le créneau entier est passé sans que rien n'ait été noté. */
  overdue: boolean;
}

/**
 * Un rendez-vous est-il en retard, à l'instant `now` ?
 *
 * Deux situations bien distinctes, et le salon n'y répond pas pareil :
 *
 *   - **En retard** : l'heure est passée, le créneau court encore. La cliente
 *     peut arriver d'une minute à l'autre ; on affiche le compteur, on ne
 *     décide rien.
 *   - **Créneau passé** : le rendez-vous est fini sur le papier et personne
 *     n'a rien noté. Là il faut trancher — arrivée, ou absente — sinon les
 *     statistiques d'absence du salon ne veulent plus rien dire.
 */
function lateState(
  booking: Booking,
  now: number,
  tolerance: number,
): LateState | null {
  // 0 = avant le montage, côté serveur : on ne sait pas quelle heure il est,
  // donc on ne signale rien plutôt que d'inventer.
  if (!now) return null;
  if (!AWAITING.includes(booking.status)) return null;

  const minutes = Math.floor((now - Date.parse(booking.starts_at)) / 60_000);

  // Même avec une tolérance nulle, on attend la minute entamée : « en retard
  // de 0 min » à l'heure pile serait faux et alarmant.
  if (minutes < Math.max(tolerance, 1)) return null;

  return { minutes, overdue: now > Date.parse(booking.ends_at) };
}

/** "1 h 05" au-delà de l'heure — un compteur à 87 min ne se lit plus. */
function formatDelay(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")}`;
}

function LateBadge({ state }: { state: LateState }) {
  if (state.overdue) {
    return <Badge tone="danger">Créneau passé · à clôturer</Badge>;
  }
  return (
    <Badge tone="warning">
      <span className="tabular">En retard de {formatDelay(state.minutes)}</span>
    </Badge>
  );
}

/**
 * Résumé des retards en cours, au-dessus de la liste.
 *
 * Sur un téléphone, une carte en retard peut être trois écrans plus bas :
 * sans ce bandeau, le signal n'existe que pour qui fait défiler. Il ne
 * s'affiche que s'il y a matière, et il vieillit avec l'horloge.
 */
function LateBanner({
  waiting,
  unresolved,
  tolerance,
}: {
  waiting: number;
  unresolved: number;
  tolerance: number;
}) {
  const parts: string[] = [];
  if (waiting > 0) {
    parts.push(`${waiting} cliente${waiting > 1 ? "s" : ""} en retard`);
  }
  if (unresolved > 0) {
    parts.push(
      `${unresolved} créneau${unresolved > 1 ? "x" : ""} passé${unresolved > 1 ? "s" : ""} à clôturer`,
    );
  }

  return (
    <div
      role="status"
      className="mb-5 flex items-start gap-3 rounded-xl border border-warning/30 bg-warning-bg px-4 py-3"
    >
      <span className="relative mt-0.5 flex size-2.5 shrink-0">
        {/* Le point qui bat : il dit que le chiffre est vivant, pas figé au
            chargement de la page. */}
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-warning opacity-60" />
        <span className="relative inline-flex size-2.5 rounded-full bg-warning" />
      </span>
      <p className="text-sm text-ink">
        <span className="font-medium">{parts.join(" · ")}.</span>{" "}
        <span className="text-muted">
          {tolerance > 0
            ? `Votre tolérance est de ${tolerance} min.`
            : "Vous ne tolérez aucun retard."}
        </span>
      </p>
    </div>
  );
}

/**
 * Le déplacement, sur la carte du rendez-vous.
 *
 * Le lien d'itinéraire est construit à partir de l'adresse saisie par la
 * cliente : elle n'a pas de coordonnées, et son quartier + son point de
 * repère sont souvent plus utiles au prestataire qu'un numéro de rue.
 */
function TravelLine({
  booking,
  currency,
}: {
  booking: Booking;
  currency: string;
}) {
  const query = [booking.address, booking.travel_zone_name]
    .filter(Boolean)
    .join(" ");
  const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
  const fee = Number(booking.travel_fee_amount);

  return (
    <div className="mt-3 rounded-lg border border-info/25 bg-info-bg p-3">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium text-ink">
        <Icon name="store" className="size-4 shrink-0" />
        À domicile · {booking.travel_zone_name}
        {fee > 0 && (
          <span className="tabular font-normal text-muted">
            {formatPrice(booking.travel_fee_amount, currency)} de déplacement,
            inclus
          </span>
        )}
      </p>

      {booking.address && (
        <a
          href={maps}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-1.5 block text-sm text-muted underline-offset-2 hover:text-ink hover:underline"
        >
          {booking.address}
        </a>
      )}
    </div>
  );
}

/**
 * La preuve de versement, et les deux décisions qu'elle appelle.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi la capture est grande
 * ---------------------------------------------------------------------------
 *
 * Parce qu'elle sert à lire un montant et une heure, pas à décorer. Une
 * vignette obligerait à ouvrir l'image dans un autre onglet pour prendre la
 * décision — et une décision qu'on repousse est une cliente qui attend.
 *
 * ---------------------------------------------------------------------------
 * « Accepter » dit deux choses à la fois
 * ---------------------------------------------------------------------------
 *
 * L'argent est arrivé, et le rendez-vous peut être tenu. Le libellé le dit
 * explicitement : un salon qui accepte sans pouvoir assurer la prestation
 * crée exactement la situation que ce circuit existe pour éviter — une
 * cliente qui a payé et n'aura rien.
 */
function ProofPanel({
  booking,
  currency,
  onAccept,
  onReject,
}: {
  booking: Booking;
  currency: string;
  onAccept: (booking: Booking, amount?: string) => void;
  onReject: (booking: Booking, reason: string) => void;
}) {
  const proof = booking.deposit_proof;
  const [refusing, setRefusing] = useState(false);
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState(booking.deposit_amount);

  if (!proof) return null;

  if (proof.status === "accepted") {
    return (
      <p className="mt-3 flex items-center gap-2 text-sm text-success">
        <Icon name="check" className="size-4" />
        Versement retrouvé et confirmé.
      </p>
    );
  }

  if (proof.status === "rejected") {
    return (
      <p className="mt-3 text-sm text-muted">
        Versement non retrouvé{proof.rejection_reason && ` — ${proof.rejection_reason}`}.
        La cliente peut renvoyer une preuve.
      </p>
    );
  }

  return (
    <div className="mt-3 rounded-xl border-l-4 border-l-amber-500 border-y border-r border-line bg-surface-muted/50 p-3">
      <p className="text-sm font-medium text-ink">
        Acompte à vérifier — {formatPrice(booking.deposit_amount, currency)}
      </p>
      <p className="mt-0.5 text-xs text-muted">
        {booking.customer_name} dit avoir payé
        {proof.channel && ` par ${proof.channel === "wechat" ? "WeChat Pay" : "Alipay"}`}
        . Retrouvez le versement dans votre application avant d&apos;accepter.
      </p>

      {/* Deux colonnes dès le téléphone : la capture à gauche, les détails
          à droite. Empilées, la décision passait sous la ligne de flottaison. */}
      <div className="mt-3 grid grid-cols-2 gap-3">
        {proof.image_url ? (
          <a
            href={proof.image_url}
            target="_blank"
            rel="noreferrer noopener"
            className="block overflow-hidden rounded-lg border border-line bg-surface"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={proof.image_url}
              alt="Capture du versement"
              className="max-h-56 w-full object-contain"
            />
          </a>
        ) : (
          <p className="rounded-lg border border-dashed border-line p-3 text-xs text-subtle">
            Aucune capture — la cliente n&apos;a pas pu en joindre.
          </p>
        )}

        <dl className="space-y-1.5 text-xs">
          {proof.reference && (
            <div>
              <dt className="text-subtle">Référence</dt>
              <dd className="tabular break-all text-ink">{proof.reference}</dd>
            </div>
          )}
          {proof.note && (
            <div>
              <dt className="text-subtle">Message</dt>
              <dd className="text-ink">{proof.note}</dd>
            </div>
          )}
          <div>
            <dt className="text-subtle">Montant reçu</dt>
            <dd>
              <input
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                inputMode="decimal"
                aria-label="Montant réellement reçu"
                className="tabular mt-0.5 w-24 rounded-lg border border-line bg-surface px-2 py-1 text-sm text-ink"
              />
            </dd>
          </div>
        </dl>
      </div>

      {refusing ? (
        <div className="mt-3">
          <input
            autoFocus
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Aucun versement à ce montant…"
            aria-label="Motif du refus"
            className={inputClass}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <DangerButton
              type="button"
              onClick={() => {
                onReject(booking, reason);
                setRefusing(false);
              }}
            >
              Confirmer le refus
            </DangerButton>
            <GhostButton type="button" onClick={() => setRefusing(false)}>
              Annuler
            </GhostButton>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" onClick={() => onAccept(booking, amount)}>
            J&apos;ai reçu l&apos;acompte — accepter
          </Button>
          <GhostButton type="button" onClick={() => setRefusing(true)}>
            Versement introuvable
          </GhostButton>
        </div>
      )}
    </div>
  );
}
