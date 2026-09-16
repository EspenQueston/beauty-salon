"use client";

/**
 * Le suivi d'un rendez-vous : où j'en suis, et que faire maintenant.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi cette page existe
 * ---------------------------------------------------------------------------
 *
 * La page de règlement a une fin. Une fois l'acompte accepté, elle n'a plus
 * rien à proposer — et la laisser ouverte invite à payer une seconde fois la
 * même somme. Mais la cliente, elle, a encore des questions après : c'est
 * quand, avec qui, ai-je bien payé, que dois-je montrer en arrivant.
 *
 * Jusqu'ici la seule réponse était l'e-mail de confirmation, qu'on retrouve
 * mal trois semaines plus tard. Cette page s'ouvre avec un lien signé, tient
 * dans un signet, et ne permet rien d'autre que lire.
 *
 * ---------------------------------------------------------------------------
 * Un seul état, décidé par le serveur
 * ---------------------------------------------------------------------------
 *
 * L'API renvoie un mot — `payable`, `waiting`, `refused`, `settled`,
 * `expired`, `cancelled` — et la page s'y conforme. Recomposer cet état ici
 * à partir de quatre champs reviendrait à écrire une seconde fois la règle
 * métier, dans un langage différent, et à la voir diverger au premier
 * ajustement.
 *
 * ---------------------------------------------------------------------------
 * Deux colonnes, sur téléphone aussi
 * ---------------------------------------------------------------------------
 *
 * Les détails sont des paires courtes — « Avec : Fatou », « Total : 380 CNY ».
 * Sur une seule colonne, une moitié de l'écran reste vide et tout passe sous
 * la ligne de flottaison. Deux colonnes dès le plus petit écran font tenir
 * l'essentiel en un coup d'œil, ce qui est exactement l'usage : on ouvre
 * cette page pour vérifier une chose, pas pour la lire.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { browserRequest } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { SalonIcon } from "@/features/salon/icons";
import { mapsHref, whatsappHref } from "@/features/salon/contact";
import type { PublicSalon } from "@/lib/types";

import { CheckinCode } from "./CheckinCode";
import { Countdown } from "./Countdown";

type PaymentPhase =
  | "payable"
  | "waiting"
  | "refused"
  | "settled"
  | "expired"
  | "cancelled";

interface StatusState {
  booking: {
    id: string;
    service_name: string;
    starts_at: string;
    ends_at: string;
    status: string;
    status_label: string;
    staff_member_name: string;
    customer_name: string;
    total_amount: string;
    options_snapshot: { name: string }[];
    items_snapshot: { name: string; quantity: number; total: string }[];
    travel_zone_name: string;
    address: string;
    cancellation_reason: string;
  };
  payment: {
    state: PaymentPhase;
    expires_at: string | null;
    deposit_amount: string;
    deposit_paid: boolean;
    deposit_received: string;
    deposit_paid_at: string | null;
    deposit_method: string;
    rejection_reason: string;
    payment_token: string;
  };
  checkin_token: string;
  checkin_code: string;
}

const CARD =
  "rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-[0_1px_3px_rgb(23_23_28_/_0.06)]";
const PRIMARY =
  "salon-gradient inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:brightness-110";
const GHOST =
  "inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--site-line)] px-4 py-2.5 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]";

/**
 * Le bandeau du haut, et le ton qu'il prend.
 *
 * Chaque état dit **ce qui se passe** puis **ce qu'il reste à faire**. Un
 * bandeau qui se contente de nommer un statut — « en attente » — laisse
 * exactement la question qu'on venait poser.
 */
type BannerKey = PaymentPhase | "honoured" | "arrived" | "missed";

/**
 * Le bandeau à afficher, d'après l'état du règlement **et** celui du
 * rendez-vous.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi les deux, et pas seulement le règlement
 * ---------------------------------------------------------------------------
 *
 * « Réglé » recouvre trois moments très différents : la veille du
 * rendez-vous, pendant la prestation, et trois semaines après. La page les
 * confondait, et disait à une cliente dont la visite était terminée de
 * présenter un code d'arrivée qui, à juste titre, n'était plus affiché.
 *
 * On ne fait cette distinction que sur un rendez-vous réglé : tant qu'il
 * reste quelque chose à payer, c'est le règlement qui commande, et son
 * statut est ce qu'il faut lire en premier.
 */
function banniere(phase: PaymentPhase, status: string): BannerKey {
  if (phase !== "settled") return phase;
  if (status === "completed") return "honoured";
  if (status === "checked_in") return "arrived";
  if (status === "no_show") return "missed";
  return "settled";
}

const BANNERS: Record<
  BannerKey,
  { title: string; body: string; tone: "ok" | "warn" | "wait" | "off" }
> = {
  payable: {
    title: "Acompte à régler",
    body: "Votre créneau est réservé le temps que vous régliez.",
    tone: "warn",
  },
  waiting: {
    title: "En attente de confirmation",
    body: "Le salon vérifie votre versement. Vous recevrez un e-mail dès que c'est fait.",
    tone: "wait",
  },
  refused: {
    title: "Versement introuvable",
    body: "Le salon n'a pas retrouvé votre paiement. Votre créneau est toujours gardé.",
    tone: "warn",
  },
  settled: {
    title: "Rendez-vous confirmé",
    body: "Tout est réglé. Présentez votre code d'arrivée en arrivant au salon.",
    tone: "ok",
  },
  // Le rendez-vous a eu lieu, ou n'aura plus lieu. Voir `banniere()` :
  // « réglé » ne suffit pas à décrire ces trois moments.
  honoured: {
    title: "Rendez-vous honoré",
    body: "Merci de votre visite. Tout est réglé, il n'y a rien à faire.",
    tone: "ok",
  },
  arrived: {
    title: "Vous êtes arrivée",
    body: "Le salon vous a enregistrée. Bonne séance.",
    tone: "ok",
  },
  missed: {
    title: "Vous n'êtes pas venue",
    body: "Le salon a noté votre absence. Contactez-le pour reprendre rendez-vous.",
    tone: "off",
  },
  expired: {
    title: "Délai de règlement dépassé",
    body: "Le créneau a été remis à disposition. Vous pouvez en choisir un autre.",
    tone: "off",
  },
  cancelled: {
    title: "Rendez-vous annulé",
    body: "Ce rendez-vous n'aura pas lieu.",
    tone: "off",
  },
};

const TONES: Record<string, string> = {
  ok: "border-l-emerald-500",
  warn: "border-l-amber-500",
  wait: "border-l-sky-500",
  off: "border-l-[var(--site-subtle)]",
};

export function BookingStatus({
  salon,
  host,
  token,
}: {
  salon: PublicSalon;
  host: string;
  token: string;
}) {
  const [state, setState] = useState<StatusState | null>(null);
  const [failed, setFailed] = useState(false);

  // Un compteur plutôt qu'un appel direct : `reload()` l'incrémente, ce qui
  // relance l'effet. Poser l'état depuis le corps de l'effet déclencherait
  // des rendus en cascade.
  const [round, setRound] = useState(0);
  const reload = useCallback(() => setRound((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;

    browserRequest<StatusState>(
      `/api/v1/public/booking-status?token=${encodeURIComponent(token)}`,
      host,
    )
      .then((data) => !cancelled && setState(data))
      .catch(() => !cancelled && setFailed(true));

    return () => {
      cancelled = true;
    };
  }, [host, token, round]);

  if (failed) {
    return (
      <div className={`${CARD} mx-auto max-w-md p-6 text-center`}>
        <p className="text-sm text-[var(--site-ink)]">
          Ce lien n&apos;est plus valable.
        </p>
        <Link href="/reserver" className={`${PRIMARY} mt-4`}>
          Prendre rendez-vous
        </Link>
      </div>
    );
  }

  if (!state) {
    return (
      <div className="mx-auto max-w-md space-y-3">
        <div className="h-28 animate-pulse rounded-2xl bg-black/[0.05]" />
        <div className="h-56 animate-pulse rounded-2xl bg-black/[0.05]" />
      </div>
    );
  }

  const { booking, payment, checkin_token: checkin, checkin_code: shortCode } = state;
  const banner =
    BANNERS[banniere(payment.state, booking.status)] ?? BANNERS.payable;
  const start = new Date(booking.starts_at);
  const when = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: salon.timezone,
  }).format(start);

  const maps = mapsHref(salon);
  const whatsapp = whatsappHref(salon.whatsapp_number);
  const overdue = payment.state === "expired" || payment.state === "cancelled";

  return (
    <div className="mx-auto max-w-md">
      {/* ----- Ce qui se passe, en premier ---------------------------- */}
      <div
        className={`${CARD} border-l-4 ${TONES[banner.tone]} p-4 sm:p-5`}
      >
        <p className="text-base font-semibold text-[var(--site-ink)]">
          {banner.title}
        </p>
        <p className="mt-1 text-sm text-[var(--site-muted)]">{banner.body}</p>

        {/* Le motif vient du salon : il explique ce que le bandeau ne peut
            pas deviner. */}
        {payment.state === "refused" && payment.rejection_reason && (
          <p className="mt-2 text-sm text-[var(--site-ink)]">
            « {payment.rejection_reason} »
          </p>
        )}
        {overdue && booking.cancellation_reason && (
          <p className="mt-2 text-sm text-[var(--site-ink)]">
            {booking.cancellation_reason}
          </p>
        )}

        {/* Un délai se comprend, une heure limite se calcule. */}
        {payment.expires_at && payment.state === "payable" && (
          <Countdown
            deadline={payment.expires_at}
            onElapsed={reload}
            className="mt-3"
          />
        )}
      </div>

      {/* ----- Le rendez-vous ----------------------------------------- */}
      <section className={`${CARD} mt-3 overflow-hidden`}>
        <div className="salon-gradient px-4 py-2.5 text-white sm:px-5">
          <p className="text-sm font-medium">{salon.name}</p>
        </div>

        <div className="p-4 sm:p-5">
          <h1 className="text-lg font-semibold text-[var(--site-ink)] sm:text-xl">
            {booking.service_name}
          </h1>
          {/* `first-letter` et non `capitalize` : ce dernier met une majuscule
              à chaque mot — « Vendredi 11 Septembre À 11:15 ». */}
          <p className="mt-0.5 text-sm text-[var(--site-muted)] first-letter:uppercase">
            {when}
          </p>

          <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2.5 text-sm">
            <Pair label="Au nom de" value={booking.customer_name} />
            {booking.staff_member_name && (
              <Pair label="Avec" value={booking.staff_member_name} />
            )}
            <Pair
              label="Total"
              value={formatPrice(booking.total_amount, salon.currency)}
              strong
            />
            {Number(payment.deposit_amount) > 0 && (
              <Pair
                label={payment.deposit_paid ? "Acompte reçu" : "Acompte"}
                value={formatPrice(
                  payment.deposit_paid
                    ? payment.deposit_received
                    : payment.deposit_amount,
                  salon.currency,
                )}
              />
            )}
            {booking.travel_zone_name && (
              <Pair label="À domicile" value={booking.travel_zone_name} />
            )}
            {payment.deposit_method && payment.deposit_paid && (
              <Pair label="Réglé par" value={payment.deposit_method} />
            )}
          </dl>

          {booking.options_snapshot?.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {booking.options_snapshot.map((option) => (
                <li
                  key={option.name}
                  className="rounded-full bg-[var(--salon-primary)]/10 px-2.5 py-1 text-xs text-[var(--site-ink)]"
                >
                  {option.name}
                </li>
              ))}
            </ul>
          )}

          {booking.items_snapshot?.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm">
              {booking.items_snapshot.map((item) => (
                <li
                  key={item.name}
                  className="flex justify-between gap-3 text-[var(--site-muted)]"
                >
                  <span className="min-w-0 truncate">
                    {item.name} × {item.quantity}
                  </span>
                  <span className="tabular shrink-0">
                    {formatPrice(item.total, salon.currency)}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {booking.address && (
            <p className="mt-3 flex items-start gap-2 text-sm text-[var(--site-muted)]">
              <SalonIcon name="pin" className="mt-0.5 size-4 shrink-0" />
              <span>{booking.address}</span>
            </p>
          )}

          {/* Le laissez-passer d'arrivée, une fois le salon d'accord.

              Déplié d'emblée ici : sur cette page, c'est l'objet de la
              visite. Replié, il se lit comme absent — et une cliente qui ne
              trouve pas son code se présente sans, ce qui fait retomber le
              salon sur la saisie manuelle que le QR devait éviter. */}
          {checkin && (
            <CheckinCode token={checkin} code={shortCode} defaultOpen />
          )}

          {/* ----- Ce qu'on peut faire d'ici ------------------------- */}
          <div className="mt-4 flex flex-wrap gap-2">
            {payment.payment_token && (
              <Link
                href={`/paiement?token=${encodeURIComponent(payment.payment_token)}`}
                className={PRIMARY}
              >
                <SalonIcon name="sparkle" className="size-4" />
                {payment.state === "refused"
                  ? "Renvoyer ma preuve"
                  : "Régler l'acompte"}
              </Link>
            )}

            {overdue && (
              <Link href="/reserver" className={PRIMARY}>
                Reprendre rendez-vous
              </Link>
            )}

            {maps && !overdue && (
              <a
                href={maps}
                target="_blank"
                rel="noreferrer noopener"
                className={GHOST}
              >
                <SalonIcon name="pin" className="size-4" />
                Itinéraire
              </a>
            )}

            {whatsapp && (
              <a
                href={whatsapp}
                target="_blank"
                rel="noreferrer noopener"
                className={GHOST}
              >
                <SalonIcon name="whatsapp" className="size-4" />
                Écrire au salon
              </a>
            )}

            {salon.phone && (
              <a href={`tel:${salon.phone.replace(/\s/g, "")}`} className={GHOST}>
                <SalonIcon name="phone" className="size-4" />
                Appeler
              </a>
            )}
          </div>
        </div>
      </section>

      <p className="mt-4 px-2 text-center text-xs text-[var(--site-subtle)]">
        Gardez ce lien : il rouvre cette page à tout moment.
      </p>
    </div>
  );
}

/** Une paire libellé / valeur du tableau de détails. */
function Pair({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-[var(--site-subtle)]">{label}</dt>
      <dd
        className={`truncate text-[var(--site-ink)] ${
          strong ? "tabular font-medium" : ""
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
