"use client";

/**
 * Régler l'acompte : scanner, payer, envoyer la preuve.
 *
 * ---------------------------------------------------------------------------
 * Ce que cette page n'est pas
 * ---------------------------------------------------------------------------
 *
 * Ce n'est pas une page de paiement en ligne. Rien n'est débité ici, aucune
 * carte n'est saisie, aucun numéro ne transite. L'argent va **directement**
 * du téléphone de la cliente au compte du salon, par WeChat Pay ou Alipay —
 * exactement comme si elle payait au comptoir.
 *
 * Nous ne voyons donc jamais le versement. C'est pour cela que la page se
 * termine par un envoi de capture d'écran et non par un « paiement réussi » :
 * personne ici ne peut honnêtement l'affirmer.
 *
 * ---------------------------------------------------------------------------
 * L'ordre des trois temps
 * ---------------------------------------------------------------------------
 *
 *   1. **Le montant**, en premier et en grand. C'est la seule chose qu'on
 *      vient vérifier avant d'ouvrir son application de paiement.
 *   2. **Le QR code**, assez large pour être scanné depuis un second
 *      téléphone, et sur fond blanc quel que soit le thème — un lecteur de
 *      code a besoin du contraste maximal, et l'inverser en mode sombre rend
 *      le code illisible pour la moitié des appareils.
 *   3. **La preuve**, seulement après. La proposer avant reviendrait à
 *      demander une capture d'écran d'un paiement qui n'a pas eu lieu.
 *
 * Le créneau reste réservé pendant tout ce temps, et la page le dit : une
 * cliente qui cherche son mot de passe ne doit pas craindre de le perdre.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { Lien } from "@/features/ui/Lien";
import { useRouter } from "next/navigation";

import { browserRequest, postForm } from "@/lib/api";
import { formatDate, formatPrice, formatTime } from "@/lib/format";
import { SalonIcon } from "@/features/salon/icons";

import { Countdown } from "./Countdown";

interface Channel {
  id: string;
  kind: string;
  kind_label: string;
  qr_url: string;
  account_name: string;
  instructions: string;
}

/**
 * Où en est le règlement, selon le serveur.
 *
 * Un seul mot, et la page s'y conforme. Le recomposer ici à partir du statut
 * du rendez-vous, de l'acompte encaissé et de l'état de la preuve
 * reviendrait à réécrire la règle métier dans un second langage — et à la
 * voir diverger au premier ajustement, du côté où personne ne regarde.
 */
type PaymentPhase =
  "payable" | "waiting" | "refused" | "settled" | "expired" | "cancelled";

interface PaymentState {
  state: PaymentPhase;
  /** Instant où le créneau se libère, ou `null` s'il ne se libère plus. */
  expires_at: string | null;
  /** Laissez-passer vers la page de suivi, où mène la sortie de celle-ci. */
  status_token: string;
  booking: {
    id: string;
    service_name: string;
    starts_at: string;
    status: string;
    deposit_amount: string;
    total_amount: string;
  };
  channels: Channel[];
  proof: {
    status: string;
    submitted_at: string;
    rejection_reason: string;
  } | null;
}

const CARD =
  "rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-[0_1px_3px_rgb(23_23_28_/_0.06)]";
const PRIMARY =
  "salon-gradient inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3 font-semibold text-white shadow-sm transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60";
const GHOST =
  "inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--site-line)] px-5 py-3 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]";

/** Poids maximal d'une capture d'écran. Aligné sur le serveur. */
const MAX_BYTES = 15 * 1024 * 1024;

export function PaymentPage({
  host,
  token,
  currency,
  timeZone,
  salonName,
}: {
  host: string;
  token: string;
  currency: string;
  timeZone: string;
  salonName: string;
}) {
  const t = useTranslations("reservation");
  const [state, setState] = useState<PaymentState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);

  // Un compteur plutôt qu'un appel direct : `reload()` l'incrémente, ce qui
  // relance l'effet. Appeler la fonction de chargement depuis le corps de
  // l'effet poserait un état de façon synchrone et déclencherait des rendus
  // en cascade.
  const [round, setRound] = useState(0);
  const reload = useCallback(() => setRound((value) => value + 1), []);

  // On arrive ici depuis le bas du formulaire de réservation : sans cela, la
  // page de paiement s'ouvre à la hauteur qu'on venait de quitter.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  useEffect(() => {
    let cancelled = false;

    browserRequest<PaymentState>(
      `/api/v1/public/payment?token=${encodeURIComponent(token)}`,
      host,
    )
      .then((data) => !cancelled && setState(data))
      .catch(() => !cancelled && setError(t("paiement.lienMort")));

    return () => {
      cancelled = true;
    };
    // `t` : stable tant que la langue ne change pas, et une bascule recharge
    // la page entière — le linter, lui, ne peut pas le savoir.
  }, [host, token, round, t]);

  /*
   * Pendant l'attente, on redemande périodiquement.
   *
   * C'est le seul moment du parcours où quelqu'un d'autre fait avancer
   * l'état : la cliente a envoyé sa capture, et quelque part le salon
   * l'accepte. Sans ce rappel, elle reste devant « en attente » jusqu'à ce
   * qu'elle pense à rafraîchir — alors que son rendez-vous est confirmé
   * depuis dix minutes.
   *
   * Vingt secondes : assez rare pour ne rien coûter, assez fréquent pour que
   * la bascule paraisse immédiate. Et l'intervalle ne tourne que dans cet
   * état précis, jamais sur une page qui n'attend rien.
   */
  const waitingForSalon = state?.state === "waiting";
  useEffect(() => {
    if (!waitingForSalon) return;
    const timer = setInterval(reload, 20_000);
    return () => clearInterval(timer);
  }, [waitingForSalon, reload]);

  if (error) {
    return (
      <div className={`${CARD} mx-auto max-w-md p-6 text-center`}>
        <p className="text-sm text-[var(--site-ink)]">{error}</p>
      </div>
    );
  }

  if (!state) {
    return (
      <div className="mx-auto max-w-md space-y-3">
        <div className="h-24 animate-pulse rounded-2xl bg-black/[0.05] dark:bg-white/5" />
        <div className="h-64 animate-pulse rounded-2xl bg-black/[0.05] dark:bg-white/5" />
      </div>
    );
  }

  const { booking, channels, proof } = state;
  const phase = state.state;
  const statusHref = `/rendez-vous?token=${encodeURIComponent(state.status_token)}`;
  const refused = phase === "refused";
  const channel = channels[active];

  /*
   * Le salon a confirmé : cette page n'a plus rien à proposer.
   *
   * La laisser ouverte inviterait à régler une seconde fois la même somme —
   * et nous ne verrions même pas le second versement, puisque l'argent ne
   * passe pas par nous. On renvoie donc vers le suivi, qui lui a encore
   * quelque chose à montrer : le montant reçu, et le code d'arrivée.
   */
  if (phase === "settled") {
    return <Settled href={statusHref} />;
  }

  if (phase === "expired" || phase === "cancelled") {
    return <Lapsed cancelled={phase === "cancelled"} />;
  }

  if (phase === "waiting") {
    return <Waiting salonName={salonName} statusHref={statusHref} />;
  }

  return (
    <div className="mx-auto max-w-md">
      {/* 1. Le montant, en premier et en grand. */}
      <div className={`${CARD} p-5 text-center`}>
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--site-subtle)]">
          {t("paiement.titre")}
        </p>
        <p className="tabular mt-1 text-3xl font-semibold text-[var(--site-ink)]">
          {formatPrice(booking.deposit_amount, currency)}
        </p>
        <p className="mt-1.5 text-sm text-[var(--site-muted)]">
          {booking.service_name} · {formatDate(booking.starts_at, timeZone)} à{" "}
          {formatTime(booking.starts_at, timeZone)}
        </p>
        <p className="tabular mt-2 text-xs text-[var(--site-subtle)]">
          Sur un total de {formatPrice(booking.total_amount, currency)}
        </p>
      </div>

      {refused && proof && (
        <div className="mt-3 rounded-xl border-l-4 border-l-amber-500 border-y border-r border-[var(--site-line)] bg-[var(--site-surface)] p-3.5">
          <p className="text-sm font-medium text-[var(--site-ink)]">
            {t("paiement.refuseTitre")}
          </p>
          {proof.rejection_reason && (
            <p className="mt-1 text-sm text-[var(--site-muted)]">
              {proof.rejection_reason}
            </p>
          )}
          <p className="mt-1 text-sm text-[var(--site-muted)]">
            {t("paiement.refuseCorps")}
          </p>
        </div>
      )}

      {channels.length === 0 ? (
        <div
          className={`${CARD} mt-3 p-5 text-center text-sm text-[var(--site-muted)]`}
        >
          {t("paiement.aucunMoyen")}
        </div>
      ) : (
        <>
          {/* 2. Le QR code. Deux onglets seulement s'il y a deux moyens :
                un onglet unique n'est pas un choix, c'est du bruit. */}
          {channels.length > 1 && (
            <div
              role="tablist"
              aria-label={t("paiement.moyenDePaiement")}
              className="mt-4 flex rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] p-0.5"
            >
              {channels.map((entry, index) => (
                <button
                  key={entry.id}
                  type="button"
                  role="tab"
                  aria-selected={index === active}
                  onClick={() => setActive(index)}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm transition ${
                    index === active
                      ? "salon-gradient font-medium text-white"
                      : "text-[var(--site-muted)] hover:text-[var(--site-ink)]"
                  }`}
                >
                  {entry.kind_label}
                </button>
              ))}
            </div>
          )}

          {channel && (
            <QrPanel channel={channel} single={channels.length === 1} />
          )}

          {/* 3. La preuve, seulement après. */}
          <ProofForm
            host={host}
            token={token}
            channel={channel?.kind ?? ""}
            onSent={reload}
          />
        </>
      )}

      {/*
        Le créneau est gardé, mais pas indéfiniment — et le dire avec une
        échéance vaut mieux que de le laisser croire sans limite. Une cliente
        qui voit « encore 22 min » sait qu'elle a le temps de chercher son
        mot de passe ; sans le compteur, elle l'apprend en revenant sur un
        créneau reperdu.
      */}
      {state.expires_at ? (
        <div className="mt-5 flex justify-center">
          <Countdown deadline={state.expires_at} onElapsed={reload} />
        </div>
      ) : (
        <p className="mt-5 flex items-start justify-center gap-2 px-2 text-center text-xs text-[var(--site-subtle)]">
          <SalonIcon name="clock" className="mt-0.5 size-3.5 shrink-0" />
          <span>{t("paiement.creneauGarde")}</span>
        </p>
      )}
    </div>
  );
}

/**
 * Le salon a confirmé : on s'efface au profit du suivi.
 *
 * La redirection est automatique, mais le lien reste visible. Une redirection
 * qui n'aboutit pas — connexion coupée, navigateur qui la bloque — laisserait
 * sinon une page vide en guise de réponse à « ai-je bien payé ».
 */
function Settled({ href }: { href: string }) {
  const t = useTranslations("reservation");
  const router = useRouter();

  useEffect(() => {
    router.replace(href);
  }, [router, href]);

  return (
    <div className={`${CARD} mx-auto max-w-md p-6 text-center`}>
      <span className="mx-auto mb-4 flex size-14 items-center justify-center rounded-full bg-emerald-500/15">
        <SalonIcon name="check" className="size-7 text-emerald-600" />
      </span>

      <h1 className="text-xl font-semibold text-[var(--site-ink)]">
        {t("paiement.recuTitre")}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-[var(--site-muted)]">
        {t("paiement.recuCorps")}
      </p>

      <Lien href={href} className={`${PRIMARY} mt-5 w-full`}>
        {t("paiement.voirRdv")}
      </Lien>
    </div>
  );
}

/**
 * Le délai est passé, ou le rendez-vous a été annulé.
 *
 * Dire « ce lien n'est plus valable » laisserait la seule question qui
 * compte sans réponse : le créneau est-il perdu ? Il l'est, on le dit, et on
 * ouvre immédiatement la seule suite utile.
 */
function Lapsed({ cancelled }: { cancelled: boolean }) {
  const t = useTranslations("reservation");
  return (
    <div className={`${CARD} mx-auto max-w-md p-6 text-center`}>
      <span className="mx-auto mb-4 flex size-14 items-center justify-center rounded-full bg-black/[0.06]">
        <SalonIcon name="clock" className="size-7 text-[var(--site-muted)]" />
      </span>

      <h1 className="text-xl font-semibold text-[var(--site-ink)]">
        {cancelled ? t("paiement.annuleTitre") : t("paiement.delaiTitre")}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-[var(--site-muted)]">
        {cancelled ? t("paiement.plusDAcompte") : t("paiement.delaiCorps")}
      </p>

      <Lien href="/reserver" className={`${PRIMARY} mt-5 w-full`}>
        {t("paiement.nouveauCreneau")}
      </Lien>
    </div>
  );
}

function QrPanel({ channel, single }: { channel: Channel; single: boolean }) {
  return (
    <div className={`${CARD} mt-3 p-5 text-center`}>
      {single && (
        <p className="mb-3 text-sm font-medium text-[var(--site-ink)]">
          {channel.kind_label}
        </p>
      )}

      {channel.qr_url ? (
        <>
          {/* Fond blanc quel que soit le thème : un lecteur de code a besoin
              du contraste maximal, et l'inverser en mode sombre rend le code
              illisible pour la moitié des téléphones. */}
          <span className="mx-auto block w-fit rounded-2xl bg-white p-3 ring-1 ring-[var(--site-line)]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={channel.qr_url}
              alt={`QR code ${channel.kind_label}`}
              className="size-48 object-contain sm:size-56"
            />
          </span>
          <p className="mt-3 text-sm text-[var(--site-muted)]">
            Scannez ce code depuis {channel.kind_label}
          </p>
        </>
      ) : (
        <p className="text-sm text-[var(--site-muted)]">
          Le salon n&apos;a pas mis de QR code pour {channel.kind_label}.
        </p>
      )}

      {channel.account_name && (
        <p className="mt-2 text-sm font-medium text-[var(--site-ink)]">
          {channel.account_name}
        </p>
      )}
      {channel.instructions && (
        <p className="mt-1 text-sm text-[var(--site-muted)]">
          {channel.instructions}
        </p>
      )}
    </div>
  );
}

/**
 * L'envoi de la capture d'écran.
 *
 * La photo est facultative : une cliente peut avoir payé sans pouvoir faire
 * de capture — téléphone plein, application qui l'interdit. Lui refuser
 * d'avancer pour cela la laisserait bloquée alors qu'elle a payé. La
 * référence de transaction suffit au salon pour retrouver le versement.
 */
function ProofForm({
  host,
  token,
  channel,
  onSent,
}: {
  host: string;
  token: string;
  channel: string;
  onSent: () => void;
}) {
  const t = useTranslations("reservation");
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  function choose(chosen: File | null) {
    if (!chosen) return;
    if (chosen.size > MAX_BYTES) {
      setProblem(t("paiement.imageTropGrande"));
      return;
    }
    setProblem(null);
    setFile(chosen);
    setPreview(URL.createObjectURL(chosen));
  }

  async function submit() {
    setBusy(true);
    setProblem(null);

    const form = new FormData();
    form.append("token", token);
    if (channel) form.append("channel", channel);
    if (reference.trim()) form.append("reference", reference.trim());
    if (note.trim()) form.append("note", note.trim());
    if (file) form.append("image", file);

    try {
      await postForm("/api/v1/public/payment/proof", host, form);
      onSent();
    } catch (caught) {
      setProblem(
        caught instanceof Error ? caught.message : "Envoi impossible.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`${CARD} mt-3 p-4`}>
      <p className="font-medium text-[var(--site-ink)]">
        {t("paiement.apresPaiement")}
      </p>
      <p className="mt-1 text-sm text-[var(--site-muted)]">
        {t("paiement.apresPaiementCorps")}
      </p>

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className={`mt-3 flex w-full items-center gap-3 rounded-xl border-2 border-dashed p-3 text-left transition ${
          preview
            ? "border-[var(--salon-primary)]"
            : "border-[var(--site-line)] hover:border-[var(--salon-primary)]/60"
        }`}
      >
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={preview}
            alt=""
            className="size-16 shrink-0 rounded-lg object-cover"
          />
        ) : (
          <span className="flex size-16 shrink-0 items-center justify-center rounded-lg bg-black/[0.04] dark:bg-white/5">
            <SalonIcon
              name="sparkle"
              className="size-6 text-[var(--site-subtle)]"
            />
          </span>
        )}
        <span className="min-w-0">
          <span className="block text-sm font-medium text-[var(--site-ink)]">
            {file ? t("paiement.changerCapture") : t("paiement.choisirCapture")}
          </span>
          <span className="block truncate text-xs text-[var(--site-subtle)]">
            {file ? file.name : "JPEG ou PNG, facultatif"}
          </span>
        </span>
      </button>

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={(event) => choose(event.target.files?.[0] ?? null)}
        className="sr-only"
      />

      {/* Deux colonnes dès le téléphone : ces champs sont courts, et les
          empiler éloignerait le bouton d'envoi de la ligne de flottaison. */}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <label className="col-span-2 sm:col-span-1">
          <span className="mb-1 block text-xs text-[var(--site-muted)]">
            {t("paiement.numeroTransaction")}
          </span>
          <input
            value={reference}
            onChange={(event) => setReference(event.target.value)}
            placeholder="Facultatif"
            className="w-full rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] px-3 py-2.5 text-sm text-[var(--site-ink)]"
          />
        </label>
        <label className="col-span-2 sm:col-span-1">
          <span className="mb-1 block text-xs text-[var(--site-muted)]">
            {t("paiement.messageAuSalon")}
          </span>
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Facultatif"
            className="w-full rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] px-3 py-2.5 text-sm text-[var(--site-ink)]"
          />
        </label>
      </div>

      {problem && (
        <p role="alert" className="mt-2 text-sm font-medium text-red-600">
          {problem}
        </p>
      )}

      <button
        type="button"
        onClick={() => void submit()}
        disabled={busy}
        className={`${PRIMARY} mt-3 w-full`}
      >
        {busy ? "Envoi…" : t("paiement.envoyerPreuve")}
      </button>
    </div>
  );
}

function Waiting({
  salonName,
  statusHref,
}: {
  salonName: string;
  statusHref: string;
}) {
  const t = useTranslations("reservation");
  return (
    <div className={`${CARD} mx-auto max-w-md p-6 text-center`}>
      <span className="mx-auto mb-4 flex size-14 items-center justify-center rounded-full bg-[var(--salon-primary)]/15">
        <SalonIcon name="clock" className="size-7 text-[var(--salon-ink)]" />
      </span>

      <h1 className="text-xl font-semibold text-[var(--site-ink)]">
        {t("paiement.attenteTitre")}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-[var(--site-muted)]">
        {salonName} a reçu votre preuve de versement. Le salon vérifie le
        paiement et confirme votre rendez-vous — vous recevrez un e-mail dès que
        c&apos;est fait.
      </p>
      <p className="mt-3 text-sm text-[var(--site-muted)]">
        {t("paiement.creneauReserve")}
      </p>

      {/* La vérification peut prendre l'après-midi entier : personne ne
          garde cet onglet ouvert jusque-là. Ce lien est celui qu'on met en
          signet, et c'est aussi celui de l'espace cliente. */}
      <Lien href={statusHref} className={`${GHOST} mt-5 w-full`}>
        {t("paiement.suivreRdv")}
      </Lien>
    </div>
  );
}
