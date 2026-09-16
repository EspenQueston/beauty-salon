"use client";

/**
 * Déplacer un rendez-vous, depuis l'agenda.
 *
 * ---------------------------------------------------------------------------
 * Ce que ça débloque
 * ---------------------------------------------------------------------------
 *
 * La route existait — `POST /bookings/<id>/reschedule` — testée, et appelée
 * par aucun écran. Le salon n'avait donc qu'une seule sortie quand une
 * cliente demandait un autre jour : annuler, puis ressaisir. Deux gestes qui
 * perdent l'acompte déjà versé, l'historique, et préviennent la cliente d'une
 * annulation qui n'en est pas une.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi les vrais créneaux, et pas un champ de date
 * ---------------------------------------------------------------------------
 *
 * Un sélecteur de date laisse écrire n'importe quelle heure : le dimanche, à
 * 3 h du matin, ou par-dessus un autre rendez-vous. Le serveur refuse — mais
 * après coup, et la gérante ne sait pas quoi essayer ensuite.
 *
 * Le panneau interroge donc la disponibilité réelle, la même que celle du
 * tunnel de réservation. Ce qui s'affiche est ce qui est acceptable ; il n'y
 * a rien à deviner.
 */

import { useCallback, useEffect, useState } from "react";

import { dashboardFetch, DashboardError } from "@/lib/dashboard";
import { formatTime, isoDateIn } from "@/lib/format";
import { Button, GhostButton } from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { Icon } from "./icons";

export interface ReschedulableBooking {
  id: string;
  starts_at: string;
  service: string;
  service_name: string;
  staff_member: string | null;
  staff_member_name: string;
  customer_name: string;
}

interface Slot {
  starts_at: string;
  ends_at: string;
  staff_member_id: string;
}

/** Nombre de jours proposés d'un coup dans le ruban. */
const JOURS = 14;

export function ReschedulePanel({
  booking,
  tenantId,
  timeZone,
  onClose,
  onDone,
}: {
  booking: ReschedulableBooking;
  tenantId: string;
  timeZone: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();

  /*
    Le ruban part d'aujourd'hui, dans le fuseau du salon.

    `isoDateIn` fait la conversion : un salon de Guangzhou consulté depuis
    l'Europe verrait sinon le ruban commencer la veille, et son premier jour
    n'aurait aucun créneau.
  */
  const [jours] = useState(() =>
    Array.from({ length: JOURS }, (_, index) => isoDateIn(timeZone, index)),
  );
  const [jour, setJour] = useState(jours[0]);
  /*
    Les créneaux, **et le jour auquel ils appartiennent**.

    Stocker la seule liste obligeait à la remettre à `null` au début du
    chargement — un `setState` synchrone dans un effet, que le compilateur
    React refuse à juste titre : il provoque un rendu de plus à chaque
    passage. En gardant le jour à côté, l'état « en cours de lecture » se
    *déduit* (le jour affiché n'est pas celui des créneaux en mémoire) au
    lieu d'être écrit.
  */
  const [charge, setCharge] = useState<{ jour: string; slots: Slot[] } | null>(
    null,
  );
  const [choisi, setChoisi] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const slots = charge?.jour === jour ? charge.slots : null;

  /** L'adresse des disponibilités d'une journée, pour cette prestation. */
  const adresse = useCallback(
    (date: string) => {
      const params = new URLSearchParams({
        service: booking.service,
        date_from: date,
        date_to: date,
      });
      // Le même prestataire, sauf si le rendez-vous n'en désignait aucun.
      // Déplacer ne doit pas changer la personne qui reçoit : c'est chez
      // quelqu'un qu'on a pris rendez-vous.
      if (booking.staff_member) params.set("staff_member", booking.staff_member);
      return `/api/v1/public/availability?${params}`;
    },
    [booking.service, booking.staff_member],
  );

  /*
    La lecture vit dans l'effet, et son résultat arrive par `.then`.

    Deux raisons, et la seconde n'est pas cosmétique. Le compilateur React
    refuse un `setState` appelé directement depuis un effet — il provoque un
    rendu de plus à chaque passage. Et le drapeau `perime` ferme une course
    réelle : en faisant défiler le ruban, une réponse partie pour le mardi
    peut revenir après celle du mercredi et réafficher les mauvais créneaux.
  */
  const [relecture, setRelecture] = useState(0);

  useEffect(() => {
    let perime = false;

    dashboardFetch<{ slots: Slot[] }>(adresse(jour), {}, tenantId)
      .then((data) => {
        if (!perime) setCharge({ jour, slots: data.slots });
      })
      .catch(() => {
        if (perime) return;
        setCharge({ jour, slots: [] });
        setErreur("Impossible de lire les disponibilités.");
      });

    return () => {
      perime = true;
    };
  }, [adresse, jour, tenantId, relecture]);

  async function valider() {
    if (!choisi) return;

    setPending(true);
    setErreur(null);
    try {
      await dashboardFetch(
        `/api/v1/bookings/${booking.id}/reschedule/`,
        { method: "POST", body: JSON.stringify({ starts_at: choisi }) },
        tenantId,
      );
      toast.success(
        `Rendez-vous de ${booking.customer_name} déplacé. La cliente est prévenue.`,
      );
      onDone();
    } catch (caught) {
      /*
        Le créneau a pu être pris entre l'affichage et le clic.

        C'est le seul refus qui mérite une réponse plus qu'un message : on
        recharge la journée, le créneau disparaît de lui-même, et la gérante
        voit ce qui reste sans avoir à rouvrir le panneau.
      */
      const conflit =
        caught instanceof DashboardError && caught.status === 409;
      setErreur(
        conflit
          ? "Ce créneau vient d'être pris. Voici ce qui reste sur la journée."
          : caught instanceof Error
            ? caught.message
            : "Déplacement impossible.",
      );
      setChoisi(null);
      // On relit la journée : le créneau disparaît de lui-même et la
      // gérante voit ce qui reste sans rouvrir le panneau.
      if (conflit) setRelecture((valeur) => valeur + 1);
    } finally {
      setPending(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Déplacer le rendez-vous de ${booking.customer_name}`}
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 backdrop-blur-[2px] sm:items-center sm:p-4"
    >
      {/*
        Collé en bas sur téléphone, centré ensuite.

        Un panneau centré sur un écran de 812 px laisse le pouce à dix
        centimètres de ses boutons. En bas, les créneaux — la seule chose sur
        laquelle on appuie — tombent sous la main.
      */}
      <div className="flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-3xl border border-line bg-surface shadow-float sm:max-w-lg sm:rounded-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3.5 sm:px-5">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-ink sm:text-lg">
              Déplacer le rendez-vous
            </h2>
            <p className="mt-0.5 truncate text-xs text-muted sm:text-sm">
              {booking.customer_name} · {booking.service_name}
            </p>
            <p className="tabular mt-0.5 text-xs text-subtle">
              Actuellement le {formatJour(booking.starts_at, timeZone)} à{" "}
              {formatTime(booking.starts_at, timeZone)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="-mr-1 shrink-0 rounded-lg p-1.5 text-muted transition hover:bg-surface-hover hover:text-ink"
          >
            <Icon name="close" className="size-5" />
          </button>
        </header>

        {/*
          Le ruban des jours défile horizontalement.

          Quatorze jours en grille prendraient l'écran entier avant d'avoir
          montré un seul créneau. En ruban, ils tiennent sur une ligne et le
          geste — glisser du pouce — est celui qu'on fait déjà partout.
        */}
        <div className="border-b border-line px-4 py-2.5 sm:px-5">
          <ul className="-mx-1 flex snap-x gap-1.5 overflow-x-auto px-1 pb-1">
            {jours.map((date) => {
              const actif = date === jour;
              return (
                <li key={date} className="snap-start">
                  <button
                    type="button"
                    onClick={() => {
                      setJour(date);
                      setChoisi(null);
                      setErreur(null);
                    }}
                    aria-pressed={actif}
                    className={`flex w-14 shrink-0 flex-col items-center rounded-xl border px-1 py-2 transition ${
                      actif
                        ? "border-transparent bg-salon text-white"
                        : "border-line bg-surface text-muted hover:border-line-strong hover:text-ink"
                    }`}
                  >
                    <span className="text-[0.62rem] uppercase tracking-wide opacity-80">
                      {jourCourt(date, timeZone)}
                    </span>
                    <span className="tabular text-base font-semibold leading-tight">
                      {date.slice(8, 10)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
          {slots === null && (
            <p className="py-8 text-center text-sm text-muted">
              Lecture des disponibilités…
            </p>
          )}

          {slots !== null && slots.length === 0 && (
            <p className="py-8 text-center text-sm text-muted">
              Aucun créneau libre ce jour-là. Essayez un autre jour du ruban.
            </p>
          )}

          {/*
            Deux colonnes sur téléphone, quatre sur grand écran.

            Une heure tient en cinq caractères : une colonne gaspillerait la
            largeur et allongerait le défilement d'autant.
          */}
          {slots !== null && slots.length > 0 && (
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {slots.map((slot) => {
                const actif = choisi === slot.starts_at;
                return (
                  <li key={slot.starts_at}>
                    <button
                      type="button"
                      onClick={() => setChoisi(slot.starts_at)}
                      aria-pressed={actif}
                      className={`tabular w-full rounded-xl border px-2 py-2.5 text-sm font-medium transition ${
                        actif
                          ? "border-transparent bg-salon text-white"
                          : "border-line bg-surface text-ink hover:border-salon"
                      }`}
                    >
                      {formatTime(slot.starts_at, timeZone)}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {erreur && (
            <p
              role="alert"
              className="mt-4 rounded-xl bg-danger-bg p-3 text-sm font-medium text-danger"
            >
              {erreur}
            </p>
          )}
        </div>

        <footer className="flex items-center gap-2 border-t border-line px-4 py-3 sm:px-5">
          <Button
            type="button"
            pending={pending}
            disabled={!choisi}
            onClick={() => void valider()}
            className="flex-1"
          >
            {choisi
              ? `Déplacer à ${formatTime(choisi, timeZone)}`
              : "Choisissez un créneau"}
          </Button>
          <GhostButton type="button" onClick={onClose}>
            Annuler
          </GhostButton>
        </footer>
      </div>
    </div>
  );
}

/** « lun. » — l'initiale du jour, dans le fuseau du salon. */
function jourCourt(isoDate: string, timeZone: string): string {
  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    timeZone,
  }).format(new Date(`${isoDate}T12:00:00Z`));
}

function formatJour(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone,
  }).format(new Date(iso));
}
