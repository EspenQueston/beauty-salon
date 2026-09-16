"use client";

/**
 * Formulaire d'avis, atteint depuis le lien reçu par e-mail.
 *
 * Le jeton de l'URL est vérifié côté serveur avant d'afficher quoi que ce
 * soit : on montre le rendez-vous concerné — prestation, date, prestataire —
 * pour que la cliente sache exactement ce qu'elle note. Sans ce rappel, une
 * cliente venue trois fois en deux mois ne sait pas de quelle visite on
 * parle.
 *
 * La note seule suffit à valider : exiger un commentaire écarte la majorité
 * des gens, et une note sans texte reste une information utile.
 *
 * ---------------------------------------------------------------------------
 * Cinq critères, et une seule étoile obligatoire
 * ---------------------------------------------------------------------------
 *
 * Une note unique dit qu'un salon vaut 3 sur 5. Elle ne dit pas *quoi*
 * réparer — et c'est la seule chose qu'un avis apporte à une gérante. Le
 * détail sépare ce qui se corrige d'un geste (l'heure tenue, le ménage) de ce
 * qui demande du temps (le geste technique).
 *
 * Mais exiger les cinq ferait abandonner : une cliente sans opinion sur le
 * rapport qualité-prix laisse la ligne vide. Une seule étoile suffit à
 * publier, et les lignes vides ne comptent pas dans la moyenne — les compter
 * comme des zéros ferait dire à la note quelque chose que personne n'a voulu
 * dire.
 *
 * La note d'ensemble n'est pas demandée : le serveur la calcule à partir des
 * critères. Six décisions au lieu de cinq, dont une qui peut contredire les
 * autres, c'est une de trop.
 */

import { useEffect, useState } from "react";
import Link from "next/link";

import {
  ApiRequestError,
  REVIEW_CRITERIA,
  fetchReviewInvitation,
  submitReview,
  type ReviewCriterion,
  type ReviewInvitation,
} from "@/lib/api";
import { formatDate } from "@/lib/format";
import { SalonIcon } from "./icons";
import { StarInput } from "./Stars";
import { Card, PrimaryLink } from "./ui";

type State =
  | { phase: "loading" }
  | { phase: "ready"; invitation: ReviewInvitation }
  | { phase: "refused"; reason: string }
  | { phase: "done" };

export function ReviewForm({
  host,
  token,
  timeZone,
}: {
  host: string;
  token: string;
  timeZone: string;
}) {
  /*
   * L'absence de jeton se décide au premier rendu, pas dans un effet.
   *
   * On connaît déjà la réponse : sans jeton il n'y a rien à vérifier. La
   * poser dans l'état initial évite un rendu « chargement » qui ne charge
   * rien, et un second rendu pour le corriger.
   */
  const [state, setState] = useState<State>(() =>
    token
      ? { phase: "loading" }
      : { phase: "refused", reason: "Ce lien est incomplet." },
  );
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const noted = REVIEW_CRITERIA.filter((c) => ratings[c.field] > 0).length;

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    fetchReviewInvitation(host, token)
      .then((invitation) => {
        if (!cancelled) setState({ phase: "ready", invitation });
      })
      .catch((caught) => {
        if (cancelled) return;
        setState({
          phase: "refused",
          reason:
            caught instanceof ApiRequestError
              ? caught.message
              : "Ce lien n'est plus valide.",
        });
      });

    return () => {
      cancelled = true;
    };
  }, [host, token]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (noted === 0) {
      setError("Notez au moins un critère.");
      return;
    }

    setPending(true);
    setError(null);
    try {
      await submitReview({
        host,
        token,
        // Les critères non notés partent explicitement à `null` : le serveur
        // distingue « pas d'avis » de « zéro », et laisser le champ absent
        // obligerait les deux côtés à s'accorder sur ce que veut dire une
        // clé manquante.
        ratings: Object.fromEntries(
          REVIEW_CRITERIA.map((c) => [c.field, ratings[c.field] || null]),
        ) as Record<ReviewCriterion, number | null>,
        comment: comment.trim(),
      });
      setState({ phase: "done" });
    } catch (caught) {
      setError(
        caught instanceof ApiRequestError
          ? caught.message
          : "Envoi impossible. Réessayez.",
      );
    } finally {
      setPending(false);
    }
  }

  if (state.phase === "loading") {
    return (
      <Card>
        <div className="space-y-3" aria-hidden>
          <div className="skeleton h-6 w-2/3 rounded-lg" />
          <div className="skeleton h-4 w-1/2 rounded-lg" />
          <div className="skeleton h-24 rounded-xl" />
        </div>
        <span className="sr-only">Vérification du lien…</span>
      </Card>
    );
  }

  if (state.phase === "refused") {
    return (
      <Card className="text-center">
        <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-black/[0.04] text-[var(--site-subtle)]">
          <SalonIcon name="close" className="size-6" />
        </span>
        <h1 className="mt-4 text-xl font-semibold text-[var(--site-ink)]">
          Avis indisponible
        </h1>
        <p className="mx-auto mt-2 max-w-sm text-[var(--site-muted)]">
          {state.reason}
        </p>
        <div className="mt-6">
          <PrimaryLink href="/" icon="arrow">
            Retour au salon
          </PrimaryLink>
        </div>
      </Card>
    );
  }

  if (state.phase === "done") {
    return (
      <Card className="text-center">
        <span
          className="mx-auto flex size-12 items-center justify-center rounded-2xl"
          style={{
            background: "var(--salon-accent)",
            color: "var(--salon-ink)",
          }}
        >
          <SalonIcon name="check" className="size-6" />
        </span>
        <h1 className="mt-4 text-xl font-semibold text-[var(--site-ink)]">
          Merci pour votre avis
        </h1>
        <p className="mx-auto mt-2 max-w-sm leading-relaxed text-[var(--site-muted)]">
          Il est en ligne. Il aidera les prochaines clientes à choisir en
          connaissance de cause.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <PrimaryLink href="/reserver" icon="calendar">
            Reprendre rendez-vous
          </PrimaryLink>
          <Link
            href="/"
            className="inline-flex items-center rounded-full border border-[var(--site-line)] px-5 py-3 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]"
          >
            Voir le salon
          </Link>
        </div>
      </Card>
    );
  }

  const { invitation } = state;

  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--salon-ink)]">
        Votre visite
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight text-[var(--site-ink)]">
        {invitation.service_name}
      </h1>
      <p className="mt-1.5 text-[var(--site-muted)]">
        {formatDate(invitation.starts_at, timeZone)}
        {invitation.staff_member_name && ` · avec ${invitation.staff_member_name}`}
      </p>

      <form onSubmit={submit} className="mt-7">
        <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3">
          <p className="text-sm font-medium text-[var(--site-ink)]">
            Votre note, point par point
          </p>
          {/* Le compteur dit que tout n'est pas obligatoire — sans lui, une
              cliente qui saute une ligne croit son avis incomplet et referme
              la page. */}
          <p className="text-xs text-[var(--site-subtle)]">
            {noted === 0
              ? "notez ce que vous voulez, une ligne suffit"
              : `${noted} critère${noted > 1 ? "s" : ""} sur ${REVIEW_CRITERIA.length}`}
          </p>
        </div>

        <ul className="divide-y divide-[var(--site-line)]">
          {REVIEW_CRITERIA.map((critere) => (
            <li
              key={critere.field}
              // Une rangée par critère : libellé à gauche, étoiles à droite,
              // et les étoiles passent dessous quand la largeur ne suffit
              // plus plutôt que d'écraser le libellé.
              className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2.5"
            >
              <span className="min-w-0">
                <span className="block text-sm font-medium text-[var(--site-ink)]">
                  {critere.label}
                </span>
                <span className="block text-xs text-[var(--site-subtle)]">
                  {critere.hint}
                </span>
              </span>
              <span className="shrink-0">
                <StarInput
                  compact
                  name={critere.field}
                  label={critere.label}
                  value={ratings[critere.field] ?? 0}
                  onChange={(value) =>
                    setRatings((current) => ({
                      ...current,
                      [critere.field]: value,
                    }))
                  }
                />
              </span>
            </li>
          ))}
        </ul>

        <label
          htmlFor="avis-commentaire"
          className="mb-1.5 mt-6 block text-sm font-medium text-[var(--site-ink)]"
        >
          Votre commentaire{" "}
          <span className="font-normal text-[var(--site-subtle)]">
            — facultatif
          </span>
        </label>
        <textarea
          id="avis-commentaire"
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          rows={5}
          maxLength={2000}
          placeholder="Comment ça s’est passé ? Ce qui vous a plu, ce qui pourrait être mieux, ce que vous diriez à une amie…"
          className="w-full rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] px-3.5 py-2.5 text-[var(--site-ink)] transition focus:border-[var(--salon-primary)]"
        />

        {error && (
          <p
            role="alert"
            className="mt-4 rounded-lg bg-black/[0.04] p-3 text-sm text-[var(--site-ink)]"
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={pending}
          className="salon-gradient mt-6 flex w-full items-center justify-center gap-2 rounded-xl px-6 py-3.5 font-semibold text-white shadow-sm transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? "Envoi…" : "Publier mon avis"}
        </button>

        <p className="mt-3 text-center text-xs text-[var(--site-subtle)]">
          Votre avis sera signé « {invitation.customer_name} » et visible
          publiquement.
        </p>
      </form>
    </Card>
  );
}
