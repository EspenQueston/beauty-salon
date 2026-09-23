"use client";

/**
 * L'espace d'une cliente : ses rendez-vous, son salon favori, son compte.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi il s'ouvre depuis le mini-site
 * ---------------------------------------------------------------------------
 *
 * Une cliente ne connaît pas la plateforme, elle connaît son salon. Le compte
 * se crée donc là où elle est déjà — sur `blondrose.example.com/compte` — et
 * il la suit ensuite chez les autres salons qu'elle fréquente. C'est le même
 * compte partout, mais l'entrée est toujours locale.
 *
 * ---------------------------------------------------------------------------
 * Annuler, oui. Déplacer, non.
 * ---------------------------------------------------------------------------
 *
 * Cet écran a longtemps ne rien permis des deux, au motif qu'un bouton
 * « annuler » donnerait un pouvoir que la politique du salon ne prévoit pas.
 * C'était se tromper de conclusion : le salon *publie* sa politique —
 * « annulation gratuite jusqu'à 24 h avant » — et n'offrait aucune façon de
 * l'exercer. La promesse existait, pas le geste.
 *
 * L'annulation est donc possible, mais **dans la fenêtre annoncée par le
 * salon, et pas au-delà**. Le serveur en est seul juge et revalide la règle
 * au moment de l'exécuter ; cet écran ne fait que lire `can_cancel`. Passé
 * le délai, le bouton cède la place aux coordonnées du salon — c'est la
 * seule réponse honnête quand la politique demande de parler à quelqu'un.
 *
 * Déplacer reste chez le salon. Choisir un autre créneau suppose de voir les
 * disponibilités d'une prestataire, d'arbitrer avec les rendez-vous voisins,
 * parfois de rappeler quelqu'un d'autre : c'est un travail d'agenda, pas un
 * bouton.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { Lien } from "@/features/ui/Lien";

import { formatPrice } from "@/lib/format";
import type { PublicSalon } from "@/lib/types";
import { SalonIcon } from "@/features/salon/icons";
import { CheckinCode } from "@/features/booking/CheckinCode";
import {
  AuthShell,
  authCard,
  authInput,
  authLead,
  authLink,
  authTitle,
} from "@/features/ui/AuthShell";
import { PasswordField } from "@/features/ui/PasswordField";
import { SalonLogo } from "@/features/salon/SalonLogo";
import { platformUrl } from "@/lib/site";

import { AuthShowcase } from "@/features/ui/AuthShowcase";
// Les appels API de l'espace vivent à part : l'annulation en a besoin elle
// aussi, et l'importer depuis ce fichier refermerait un cycle.
import { api } from "./api";
import { Annuler } from "./Annuler";
import { ThemeToggle } from "@/features/ui/ThemeToggle";
import { Tracker } from "./Tracker";
import type { ClientBooking } from "./types";

const CARD =
  "rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-[0_1px_3px_rgb(23_23_28_/_0.06)]";

const INPUT =
  "w-full rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] px-3.5 py-2.5 text-[var(--site-ink)] transition focus:border-[var(--salon-primary)]";

const PRIMARY =
  "inline-flex items-center justify-center rounded-xl bg-[var(--salon-primary)] px-5 py-3 font-semibold text-white shadow-sm transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60";

/*
 * Classes de l'écran d'identification.
 *
 * Elles viennent maintenant d'`AuthShell`, partagées avec l'écran
 * professionnel : deux copies locales avaient déjà divergé — champs de
 * 2,5 rem ici, de 2,75 là, titre dans la carte d'un côté, dehors de
 * l'autre. Un seul geste, une seule mise en page.
 *
 * Elles prennent les variables du **produit** (`--ui-*` via les utilitaires
 * Tailwind) et non celles du mini-site : voir le commentaire dans `Gate`.
 */

interface Session {
  email: string;
  display_name: string;
  is_client: boolean;
  is_staff_member: boolean;
  client: ClientProfile | null;
}

interface ClientProfile {
  full_name: string;
  email: string;
  phone: string;
  whatsapp: string;
  wechat: string;
  preferred_salon: string | null;
  preferred_salon_name: string;
  preferred_salon_slug: string;
}

/*
  La table des états est une **fonction** de la langue.

  En constante de module, ses libellés se fixaient au démarrage du serveur —
  en français, pour toutes les pages. Construite à l'appel, elle suit la
  langue de la requête.
*/
function etats(
  t: (cle: string) => string,
): Record<string, { label: string; className: string }> {
  return {
    pending_payment: {
      label: t("etat.acompte"),
      className: "bg-amber-500/20 text-amber-800 dark:text-amber-300",
    },
    requested: {
      label: t("etat.demande"),
      className: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
    },
    confirmed: {
      label: t("etat.confirme"),
      className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
    },
    checked_in: {
      label: t("etat.arrivee"),
      className: "bg-sky-500/15 text-sky-700 dark:text-sky-400",
    },
    completed: {
      label: t("etat.termine"),
      className: "bg-black/[0.06] text-[var(--site-muted)] dark:bg-white/10",
    },
    cancelled: {
      label: t("etat.annule"),
      className: "bg-black/[0.06] text-[var(--site-muted)] dark:bg-white/10",
    },
    no_show: {
      label: t("etat.nonHonore"),
      className: "bg-red-500/15 text-red-700 dark:text-red-400",
    },
  };
}

export function ClientSpace({
  salon,
  host,
}: {
  salon: PublicSalon;
  host: string;
}) {
  const t = useTranslations("espace");
  const [session, setSession] = useState<Session | null | "anonymous">(null);

  // Un jeton plutôt qu'un rappel : après une connexion ou une déconnexion,
  // il faut relire la session. L'incrémenter relance l'effet, ce qui garde
  // la lecture *dans* l'effet — un `setState` appelé depuis un rappel de
  // rendu déclencherait des rendus en cascade.
  const [token, setToken] = useState(0);
  const refresh = useCallback(() => setToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;

    api<Session>("/api/v1/public/client/session", host)
      .then((data) => !cancelled && setSession(data))
      .catch(() => !cancelled && setSession("anonymous"));

    return () => {
      cancelled = true;
    };
  }, [token, host]);

  if (session === null) {
    return (
      <div className="flex min-h-svh items-center justify-center text-[var(--site-muted)]">
        Chargement…
      </div>
    );
  }

  if (session === "anonymous") {
    return <Gate salon={salon} host={host} onDone={refresh} />;
  }

  // Un membre d'équipe sans profil cliente est renvoyé vers son tableau de
  // bord : lui montrer un espace vide n'aurait aucun sens.
  if (!session.is_client) {
    return (
      <div className={`${CARD} mx-auto max-w-md p-6 text-center`}>
        <p className="font-medium text-[var(--site-ink)]">{t("pro.titre")}</p>
        <p className="mt-1.5 text-sm text-[var(--site-muted)]">
          {t("pro.corps")}
        </p>
        <Lien href="/dashboard" className={`${PRIMARY} mt-4`}>
          {t("pro.tableau")}
        </Lien>
      </div>
    );
  }

  return (
    <Space session={session} salon={salon} host={host} onChange={refresh} />
  );
}

/* --------------------------------------------------------------------------
 * Connexion et inscription
 * ---------------------------------------------------------------------- */

/**
 * Une seule page pour les deux gestes.
 *
 * Deux pages séparées obligent à deviner laquelle on veut avant de savoir si
 * on a déjà un compte — et la moitié des gens se trompent. Ici, la bascule
 * est un lien, et rien n'est perdu en passant de l'une à l'autre.
 */
function Gate({
  salon,
  host,
  onDone,
}: {
  salon: PublicSalon;
  host: string;
  onDone: () => void;
}) {
  const t = useTranslations("espace");
  /*
    Tant qu'on n'est pas connectée, l'habillage du salon disparaît.

    Menu, pied de page, barre de réservation : sur un écran
    d'identification, chaque élément cliquable qui n'est pas le formulaire
    est une occasion de partir sans le remplir. Le marqueur est posé sur
    <html> parce que cet habillage est rendu par un composant serveur, qui
    ne peut pas connaître l'état de session.
  */
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.authScreen = "1";
    return () => {
      delete root.dataset.authScreen;
    };
  }, []);

  const [mode, setMode] = useState<"login" | "signup">("login");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [wechat, setWechat] = useState("");
  const [password, setPassword] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setFailure(null);

    try {
      if (mode === "signup") {
        await api("/api/v1/public/client/signup", host, {
          method: "POST",
          body: JSON.stringify({
            full_name: fullName,
            email,
            phone,
            password,
            whatsapp,
            wechat,
          }),
        });
      } else {
        await api("/api/v1/auth/login", host, {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
      }
      onDone();
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : t("compte.echec"));
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthShell
      homeHref="/"
      homeLabel={t("compte.retourChez", { salon: salon.name })}
      brand={
        <>
          <SalonLogo
            logo={salon.logo}
            name={salon.name}
            className="size-8 text-xs"
          />
          <span className="truncate font-semibold tracking-tight text-ink">
            {salon.name}
          </span>
        </>
      }
      /*
        Le même sélecteur que l'espace professionnel.

        Cet écran suit le thème du **produit** — l'habillage du salon est
        retiré ici — donc c'est celui-là qu'il faut piloter, pas le mode
        du mini-site. Les deux cohabitaient et c'est ce qui donnait une
        carte blanche sur fond sombre.
      */
      action={<ThemeToggle />}
      aside={
        /*
          Ce qui décide vraiment devant un formulaire de compte.

          Pas des arguments de vente : les trois questions qu'on se pose —
          à quoi ça sert, est-ce que ça m'engage, est-ce que je peux faire
          sans. La dernière est volontairement honnête, et c'est elle qui
          met en confiance.
        */
        <AuthShowcase
          seed={salon.slug}
          title={t("compte.unCompte")}
          points={[
            {
              title: t("compte.rdvAuMemeEndroit"),
              body: t("compte.ceuxDeListe", { salon: salon.name }),
            },
            {
              title: t("compte.plusRienARessaisir"),
              body: t("compte.plusRienCorps"),
            },
            {
              title: t("compte.sansCompteTitre"),
              body: t("compte.sansCompteCorps"),
            },
          ]}
        />
      }
    >
      {/*
        Cet écran suit le thème du **produit**, pas celui du mini-site.

        Les deux cohabitaient : la coquille prenait `--ui-*`, la carte
        prenait `--site-*`. Quand la visiteuse était en sombre côté système
        mais que le mini-site restait en clair, on obtenait une carte blanche
        sur un fond noir, et le titre de droite devenait illisible.

        L'habillage du salon est de toute façon retiré ici — menu, pied de
        page, couleurs de marque — donc suivre le thème du produit est aussi
        le choix cohérent.
      */}
      <div className={authCard}>
        <h1 className={authTitle}>
          {mode === "login"
            ? t("compte.retrouvez")
            : t("compte.creerVotreCompte")}
        </h1>
        <p className={authLead}>
          {mode === "login"
            ? t("compte.ceuxDeMemeEndroit", { salon: salon.name })
            : t("compte.unSeulCompte")}
        </p>

        <form
          onSubmit={(event) => void submit(event)}
          className="mt-6 space-y-4"
        >
          {mode === "signup" && (
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">
                {t("compte.nom")}
              </span>
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                className={authInput}
                autoComplete="name"
                required
              />
            </label>
          )}

          {/* L'adresse et le mot de passe restent sur une colonne, même à
              l'inscription. Deux colonnes conviennent à des cartes courtes,
              pas à un identifiant qu'on relit caractère par caractère. */}
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-ink">
              E-mail
            </span>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              inputMode="email"
              autoComplete="email"
              className={authInput}
              required
            />
          </label>

          {mode === "signup" && (
            <>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink">
                  {t("compte.telephone")}
                </span>
                <input
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  className={authInput}
                  required
                />
              </label>

              {/* WhatsApp et WeChat sont facultatifs : ce sont des
                  préférences de contact, pas des identifiants. Deux
                  colonnes leur vont — ce sont des champs courts, et les
                  mettre côte à côte dit qu'on peut sauter les deux. */}
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium text-ink">
                    WhatsApp
                  </span>
                  <input
                    value={whatsapp}
                    onChange={(event) => setWhatsapp(event.target.value)}
                    type="tel"
                    inputMode="tel"
                    placeholder="Facultatif"
                    className={authInput}
                  />
                </label>

                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium text-ink">
                    WeChat
                  </span>
                  <input
                    value={wechat}
                    onChange={(event) => setWechat(event.target.value)}
                    placeholder="Facultatif"
                    className={authInput}
                  />
                </label>
              </div>
            </>
          )}

          <PasswordField
            label={t("compte.motDePasse")}
            value={password}
            onChange={setPassword}
            autoComplete={
              mode === "signup" ? "new-password" : "current-password"
            }
            inputClassName={authInput}
            action={
              mode === "login" ? (
                /*
                  La réinitialisation mène au domaine de la plateforme, et
                  c'est volontaire : l'e-mail de réinitialisation y renvoie
                  de toute façon. Reconstruire ici un formulaire qui aboutit
                  au même endroit donnerait deux chemins à maintenir pour un
                  seul parcours.
                */
                <a
                  href={`${platformUrl}/mot-de-passe-oublie`}
                  className={`${authLink} text-sm`}
                >
                  {t("compte.motDePasseOublie")}
                </a>
              ) : undefined
            }
          />

          {failure && (
            <p
              role="alert"
              className="rounded-xl bg-danger-bg p-3 text-sm font-medium text-danger"
            >
              {failure}
            </p>
          )}

          <button
            type="submit"
            disabled={pending}
            className={`${PRIMARY} w-full`}
          >
            {pending
              ? t("compte.unInstant")
              : mode === "login"
                ? t("compte.seConnecter")
                : t("compte.creerMonCompte")}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-ink/75">
          {mode === "login" ? t("compte.pasEncore") : t("compte.dejaUn")}{" "}
          <button
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setFailure(null);
            }}
            className={authLink}
          >
            {mode === "login"
              ? t("compte.creerUnCompte")
              : t("compte.seConnecter")}
          </button>
        </p>
      </div>

      {/*
        La sortie honnête, et elle est visible.

        Réserver ne demande pas de compte — le dire en petit sous le
        formulaire, et seulement sur téléphone, revenait à le cacher à celles
        pour qui l'information change tout : celles qui allaient renoncer
        plutôt que de s'inscrire. C'est un lien, pas une phrase.
      */}
      <p className="mt-5 text-center text-sm text-ink/75">
        <Lien href="/reserver" className={authLink}>
          {t("compte.reserverSansCompte")}
        </Lien>
        <span className="mt-1 block text-xs text-muted">
          {t("compte.sansCompteCorps")}
        </span>
      </p>
    </AuthShell>
  );
}

/* --------------------------------------------------------------------------
 * L'espace lui-même
 * ---------------------------------------------------------------------- */

function Space({
  session,
  salon,
  host,
  onChange,
}: {
  session: Session;
  salon: PublicSalon;
  host: string;
  onChange: () => void;
}) {
  const t = useTranslations("espace");
  const [data, setData] = useState<{
    salons: { slug: string; name: string }[];
    bookings: ClientBooking[];
  } | null>(null);
  const [failed, setFailed] = useState(false);
  /*
    Ce qui déclenche une relecture de la liste.

    Une annulation change l'état d'une ligne *et* sa place — elle quitte
    « à venir » pour l'historique. Retirer la carte à la main dans le
    navigateur donnerait un écran qui ne dit plus la même chose que le
    serveur ; on relit, c'est une requête et la vérité.
  */
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api<{
      salons: { slug: string; name: string }[];
      bookings: ClientBooking[];
    }>("/api/v1/public/client/bookings", host)
      .then((result) => !cancelled && setData(result))
      .catch(() => !cancelled && setFailed(true));

    return () => {
      cancelled = true;
    };
  }, [host, reloadToken]);

  const relire = useCallback(() => setReloadToken((value) => value + 1), []);

  // Lu une fois au montage : appeler `Date.now()` pendant le rendu rend le
  // résultat instable d'un rendu à l'autre, et le classement d'un
  // rendez-vous pourrait changer sans qu'aucune donnée n'ait bougé.
  const [now] = useState(() => Date.now());
  const upcoming =
    data?.bookings.filter(
      (booking) =>
        new Date(booking.starts_at).getTime() >= now &&
        !["cancelled", "no_show", "completed"].includes(booking.status),
    ) ?? [];
  const past =
    data?.bookings.filter((booking) => !upcoming.includes(booking)) ?? [];

  async function logout() {
    await api("/api/v1/auth/logout", host, { method: "POST" }).catch(() => {});
    onChange();
  }

  const nextOne = upcoming[0];
  const rest = upcoming.slice(1);

  // Ce qui attend un geste de la cliente. Compté séparément parce que c'est
  // la seule chose de cette page qui coûte quelque chose tant qu'on ne la
  // fait pas : un acompte non réglé finit par libérer le créneau.
  const toSettle = upcoming.filter((booking) => booking.payment_token);

  const visits = (data?.bookings ?? []).filter(
    (booking) => booking.status === "completed",
  ).length;

  /*
    Les visites qu'on peut encore noter.

    C'est le serveur qui tranche — honorée, moins de trente jours, pas encore
    notée — et l'écran ne fait que lire `can_review`. Refaire le calcul ici
    produirait tôt ou tard deux verdicts différents : un bouton proposé sur
    une visite déjà notée, ou refusé sur une visite qui l'accepte encore.
  */
  const toReview = (data?.bookings ?? []).filter(
    (booking) => booking.can_review,
  );

  /*
    Deux listes, deux onglets.

    L'historique et les rendez-vous à venir ne se consultent pas dans le même
    état d'esprit : on vient vérifier une heure, ou on vient retrouver ce
    qu'on a payé. Empilés, le second poussait le premier hors de l'écran dès
    la quatrième visite — et c'est le premier qu'on ouvre neuf fois sur dix.
  */
  const [tab, setTab] = useState<"avenir" | "passe">("avenir");

  const firstName = session.client?.full_name?.split(" ")[0] ?? "";

  return (
    <main className="mx-auto w-full max-w-3xl px-4 pb-12 pt-24 sm:px-6 sm:pb-16 sm:pt-28">
      {/*
        L'en-tête porte l'identité, pas seulement un bonjour.

        L'initiale sur pastille de marque ancre la page : on sait chez qui on
        est, et le compte se distingue du mini-site public qu'on vient de
        quitter.
      */}
      <header className="mb-6 flex flex-wrap items-center gap-3">
        <span
          aria-hidden
          className="salon-gradient flex size-12 shrink-0 items-center justify-center rounded-2xl text-lg font-semibold text-white"
        >
          {(firstName || session.email)[0]?.toUpperCase()}
        </span>

        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-semibold tracking-tight text-[var(--site-ink)] sm:text-2xl">
            Bonjour {firstName}
          </h1>
          <p className="truncate text-sm text-[var(--site-muted)]">
            {session.email}
          </p>
        </div>

        <button
          type="button"
          onClick={() => void logout()}
          className="shrink-0 rounded-xl border border-[var(--site-line)] px-3 py-2 text-sm text-[var(--site-muted)] transition hover:text-[var(--site-ink)]"
        >
          {t("compte.seDeconnecter")}
        </button>
      </header>

      {/* Quatre chiffres, en deux colonnes dès le téléphone. Ils répondent à
          « où j'en suis » sans faire défiler.

          « À noter » a rejoint les trois autres parce que c'est le seul qui
          appelle un geste : les trois premiers décrivent, celui-là demande. */}
      <dl className="mb-6 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Tile label={t("liste.aVenir")} value={String(upcoming.length)} />
        <Tile
          label={visits > 1 ? "Visites" : "Visite"}
          value={String(visits)}
        />
        <Tile
          label={t("liste.aNoter")}
          value={String(toReview.length)}
          accent={toReview.length > 0}
        />
        <Tile
          label="Salon"
          value={session.client?.preferred_salon_name || salon.name}
          small
        />
      </dl>

      {failed && (
        <p className="mb-6 rounded-xl bg-red-500/10 p-3.5 text-sm text-red-700">
          {t("liste.echec")}
        </p>
      )}

      {/* Ce qui attend un geste passe avant tout le reste. */}
      {toSettle.length > 0 && (
        <div className="mb-6 rounded-2xl border-l-4 border-l-amber-500 border-y border-r border-[var(--site-line)] bg-[var(--site-surface)] p-4">
          <p className="font-medium text-[var(--site-ink)]">
            {toSettle.length === 1
              ? t("liste.acompteRestant")
              : t("liste.acomptesRestants", { n: toSettle.length })}
          </p>
          <p className="mt-1 text-sm text-[var(--site-muted)]">
            {t("liste.acompteRappel")}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {toSettle.map((booking) => (
              <Lien
                key={booking.id}
                href={`/paiement?token=${encodeURIComponent(booking.payment_token)}`}
                className={`${PRIMARY} px-4 py-2.5 text-sm`}
              >
                Régler {booking.service_name}
              </Lien>
            ))}
          </div>
        </div>
      )}

      {/*
        Les avis en attente, juste après les acomptes.

        Ils ne coûtent rien à la cliente si elle les ignore — d'où la place
        après l'argent — mais l'échéance est réelle : au-delà de trente jours
        le lien ne fonctionne plus. Le dire en jours plutôt qu'en date,
        parce que « il vous reste 6 jours » se comprend sans calcul.
      */}
      {toReview.length > 0 && (
        <div className="mb-6 rounded-2xl border-y border-r border-l-4 border-[var(--site-line)] border-l-[var(--salon-primary)] bg-[var(--site-surface)] p-4">
          <p className="flex flex-wrap items-center gap-2 font-medium text-[var(--site-ink)]">
            <SalonIcon name="star" className="size-4 text-[var(--salon-ink)]" />
            {toReview.length === 1
              ? t("liste.visiteAttendAvis")
              : t("liste.visitesAvis", { n: toReview.length })}
          </p>
          <p className="mt-1 text-sm text-[var(--site-muted)]">
            {t("liste.avisInvitation")}
          </p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {toReview.map((booking) => (
              <li key={booking.id}>
                <a
                  href={`${salonOrigin(booking.salon_slug, host)}/avis?token=${encodeURIComponent(booking.review_token)}`}
                  className={`${PRIMARY} px-4 py-2.5 text-sm`}
                >
                  Noter {booking.service_name}
                  <span className="ml-1.5 font-normal opacity-80">
                    · {remaining(booking.review_until, t)}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data === null && !failed && (
        <div className={`${CARD} mb-6 h-32 animate-pulse`} />
      )}

      {/* Le prochain rendez-vous, en grand : c'est la seule chose qu'on
          vient vérifier neuf fois sur dix. */}
      {nextOne && (
        <NextBooking booking={nextOne} host={host} onCancelled={relire} />
      )}

      {data !== null && upcoming.length === 0 && (
        <div className={`${CARD} p-6 text-center`}>
          <p className="font-medium text-[var(--site-ink)]">
            {t("liste.aucunAVenir")}
          </p>
          <p className="mt-1 text-sm text-[var(--site-muted)]">
            {visits > 0
              ? t("liste.reprenezLa")
              : t("liste.choisissezPrestation")}
          </p>
          <Lien href="/reserver" className={`${PRIMARY} mt-4`}>
            Réserver chez {salon.name}
          </Lien>
        </div>
      )}

      {(rest.length > 0 || past.length > 0) && (
        <section className="mb-8">
          {/* Deux onglets plutôt que deux sections empilées : l'historique
              d'une cliente fidèle poussait les rendez-vous suivants hors de
              l'écran, et ce sont eux qu'on vient voir. */}
          <div
            role="tablist"
            aria-label={t("liste.vosRdv")}
            className="mb-3 flex rounded-xl border border-[var(--site-line)] bg-[var(--site-surface)] p-1"
          >
            {(
              [
                ["avenir", "Ensuite", rest.length],
                ["passe", "Historique", past.length],
              ] as ["avenir" | "passe", string, number][]
            ).map(([key, label, count]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm transition ${
                  tab === key
                    ? "salon-gradient font-medium text-white shadow-sm"
                    : "text-[var(--site-muted)] hover:text-[var(--site-ink)]"
                }`}
              >
                {label}
                {count > 0 && (
                  <span
                    className={`tabular text-xs ${
                      tab === key
                        ? "text-white/75"
                        : "text-[var(--site-subtle)]"
                    }`}
                  >
                    {count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {tab === "avenir" ? (
            rest.length > 0 ? (
              <ul className="grid gap-2.5 sm:grid-cols-2">
                {rest.map((booking) => (
                  <BookingCard key={booking.id} booking={booking} host={host} />
                ))}
              </ul>
            ) : (
              <p
                className={`${CARD} p-4 text-center text-sm text-[var(--site-muted)]`}
              >
                {t("liste.rienApres")}
              </p>
            )
          ) : past.length > 0 ? (
            /* Deux colonnes dès le téléphone : ces cartes sont courtes, et
               une seule colonne transformait dix visites en défilement. */
            <ul className="grid grid-cols-2 gap-2.5">
              {past.map((booking) => (
                <BookingCard
                  key={booking.id}
                  booking={booking}
                  host={host}
                  compact
                />
              ))}
            </ul>
          ) : (
            <p
              className={`${CARD} p-4 text-center text-sm text-[var(--site-muted)]`}
            >
              {t("liste.passeesIci")}
            </p>
          )}
        </section>
      )}

      <Preferences
        session={session}
        host={host}
        salons={data?.salons ?? []}
        onSaved={onChange}
      />
    </main>
  );
}

function Tile({
  label,
  value,
  small = false,
  accent = false,
}: {
  label: string;
  value: string;
  small?: boolean;
  /** Le chiffre appelle un geste. Les autres tuiles décrivent, celle-ci
   *  demande — et un zéro n'a rien à demander, d'où le drapeau plutôt qu'un
   *  test sur la valeur. */
  accent?: boolean;
}) {
  return (
    <div
      className={`${CARD} px-3 py-2.5 ${
        accent ? "border-[var(--salon-primary)]" : ""
      }`}
    >
      <dt className="text-xs text-[var(--site-subtle)]">{label}</dt>
      <dd
        className={`mt-0.5 truncate font-semibold ${
          accent ? "text-[var(--salon-ink)]" : "text-[var(--site-ink)]"
        } ${small ? "text-sm" : "tabular text-xl"}`}
      >
        {value}
      </dd>
    </div>
  );
}

/**
 * Un rendez-vous secondaire : les suivants, et l'historique.
 *
 * `compact` sert l'historique, affiché en deux colonnes dès le téléphone.
 * On n'y relit pas les détails — on vérifie « quoi, quand, combien » — donc
 * la carte se réduit à cela plutôt que de répéter la mise en page du
 * prochain rendez-vous en plus petit.
 */
function BookingCard({
  booking,
  host,
  highlight = false,
  compact = false,
}: {
  booking: ClientBooking;
  host: string;
  highlight?: boolean;
  compact?: boolean;
}) {
  const t = useTranslations("espace");
  const status = etats(t)[booking.status] ?? {
    label: booking.status,
    className: "bg-black/[0.06] text-[var(--site-muted)]",
  };

  const when = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(booking.starts_at));

  // Le salon d'origine reste joignable : c'est chez lui qu'on annule ou
  // qu'on déplace, jamais depuis cet écran.
  const salonUrl = host.includes("localhost")
    ? `http://${booking.salon_slug}.localhost:3100`
    : `https://${booking.salon_slug}.${host.split(".").slice(1).join(".")}`;

  if (compact) {
    return (
      <li className={`${CARD} flex flex-col p-3`}>
        <p className="truncate text-sm font-medium text-[var(--site-ink)]">
          {booking.service_name}
        </p>
        <p className="mt-0.5 truncate text-xs text-[var(--site-muted)] first-letter:uppercase">
          {shortDate(booking.starts_at)}
        </p>
        <p className="mt-1.5 flex flex-wrap items-baseline justify-between gap-x-2">
          <span className="tabular text-sm text-[var(--site-ink)]">
            {formatPrice(booking.total_amount, booking.currency)}
          </span>
          <span className="truncate text-xs text-[var(--site-subtle)]">
            {booking.salon_name}
          </span>
        </p>

        {/*
          Ce qu'on peut encore faire de cette visite.

          Trois états, un seul visible à la fois — une carte d'historique de
          la largeur d'un demi-téléphone ne supporte pas deux boutons.

            · notable      → le bouton, avec le temps qu'il reste ;
            · déjà notée   → un mot, pour que le geste ne se redemande pas ;
            · rien à faire → le lien de reprise, qui est l'action utile sur
                             une visite qu'on a aimée.
        */}
        <div className="mt-2 border-t border-[var(--site-line)] pt-2">
          {booking.can_review ? (
            <a
              href={`${salonUrl}/avis?token=${encodeURIComponent(booking.review_token)}`}
              className="flex items-center gap-1.5 text-xs font-semibold text-[var(--salon-ink)] underline-offset-2 hover:underline"
            >
              <SalonIcon name="star" className="size-3.5 shrink-0" />
              <span className="truncate">
                Noter · {remaining(booking.review_until, t)}
              </span>
            </a>
          ) : booking.reviewed ? (
            <p className="flex items-center gap-1.5 text-xs text-[var(--site-subtle)]">
              <SalonIcon name="check" className="size-3.5 shrink-0" />
              {t("liste.avisDepose")}
            </p>
          ) : (
            <a
              href={`${salonUrl}/reserver`}
              className="flex items-center gap-1.5 text-xs font-medium text-[var(--site-muted)] underline-offset-2 hover:text-[var(--site-ink)] hover:underline"
            >
              <SalonIcon name="calendar" className="size-3.5 shrink-0" />
              {t("liste.reprendre")}
            </a>
          )}
        </div>
      </li>
    );
  }

  return (
    <li
      className={`${CARD} p-4 ${
        highlight ? "border-l-4 border-l-[var(--salon-primary)]" : ""
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium text-[var(--site-ink)]">
            {booking.service_name}
          </p>
          {/* `first-letter` et non `capitalize` : ce dernier met une
              majuscule à *chaque* mot, ce qui donnait « Vendredi 11
              Septembre À 11:15 ». */}
          <p className="mt-0.5 text-sm text-[var(--site-muted)] first-letter:uppercase">
            {when}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${status.className}`}
        >
          {status.label}
        </span>
      </div>

      {/*
        Le motif, sous l'étiquette.

        « Annulé » tout court fait chercher : on se demande si on a annulé
        soi-même, si le salon a fermé, ou si l'acompte est arrivé trop tard.
        Le salon écrit ce motif à chaque annulation ; il ne remontait
        simplement pas jusqu'ici.
      */}
      {booking.status === "cancelled" && booking.cancellation_reason && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-[var(--site-muted)]">
          <SalonIcon name="clock" className="mt-0.5 size-3.5 shrink-0" />
          <span>{booking.cancellation_reason}</span>
        </p>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[var(--site-muted)]">
        <a
          href={salonUrl}
          className="inline-flex items-center gap-1.5 font-medium text-[var(--salon-ink)] hover:underline"
        >
          <SalonIcon name="store" className="size-3.5" />
          {booking.salon_name}
        </a>
        {booking.staff_member_name && (
          <span>avec {booking.staff_member_name}</span>
        )}
        <span className="tabular">
          {formatPrice(booking.total_amount, booking.currency)}
        </span>
      </div>

      {booking.options_snapshot?.length > 0 && (
        <p className="mt-1.5 text-xs text-[var(--site-subtle)]">
          {booking.options_snapshot.map((option) => option.name).join(" · ")}
        </p>
      )}

      {booking.travel_zone_name && (
        <p className="mt-1.5 text-xs text-[var(--site-subtle)]">
          À domicile · {booking.travel_zone_name}
        </p>
      )}

      {/* Discret : sur une carte secondaire, un bouton plein ferait
          concurrence au prochain rendez-vous, qui est ce qu'on vient voir. */}
      <a
        href={`${salonUrl}/rendez-vous?token=${encodeURIComponent(booking.status_token)}`}
        className="mt-2.5 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--salon-ink)] underline-offset-2 hover:underline"
      >
        {t("liste.voirDetail")}
        <SalonIcon name="arrow" className="size-3.5" />
      </a>
    </li>
  );
}

/**
 * Salon favori et coordonnées.
 *
 * Le salon favori n'est pas décoratif : il décide de la page d'accueil de
 * l'espace et de ce qu'on propose de réserver en premier. Il se change ici
 * plutôt que dans un menu caché, parce qu'il change réellement — on
 * déménage, on essaie ailleurs.
 */
function Preferences({
  session,
  host,
  salons,
  onSaved,
}: {
  session: Session;
  host: string;
  salons: { slug: string; name: string }[];
  onSaved: () => void;
}) {
  const t = useTranslations("espace");
  const profile = session.client;
  const [whatsapp, setWhatsapp] = useState(profile?.whatsapp ?? "");
  const [wechat, setWechat] = useState(profile?.wechat ?? "");
  const [phone, setPhone] = useState(profile?.phone ?? "");
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    try {
      await api("/api/v1/public/client/me", host, {
        method: "PATCH",
        body: JSON.stringify({ phone, whatsapp, wechat }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2400);
      onSaved();
    } finally {
      setPending(false);
    }
  }

  return (
    <section className={`${CARD} p-5 sm:p-6`}>
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--site-subtle)]">
        Mon compte
      </h2>

      {profile?.preferred_salon_name && (
        <p className="mb-4 text-sm text-[var(--site-muted)]">
          Salon favori :{" "}
          <span className="font-medium text-[var(--site-ink)]">
            {profile.preferred_salon_name}
          </span>
          {salons.length > 1 && (
            <span className="text-[var(--site-subtle)]">
              {" "}
              · vous fréquentez {salons.length} salons
            </span>
          )}
        </p>
      )}

      <form onSubmit={(event) => void save(event)}>
        <div className="grid grid-cols-2 gap-3">
          <label className="col-span-2 block">
            <span className="mb-1 block text-xs text-[var(--site-muted)]">
              {t("compte.telephone")}
            </span>
            <input
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              type="tel"
              className={INPUT}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-[var(--site-muted)]">
              WhatsApp
            </span>
            <input
              value={whatsapp}
              onChange={(event) => setWhatsapp(event.target.value)}
              type="tel"
              className={INPUT}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-[var(--site-muted)]">
              WeChat
            </span>
            <input
              value={wechat}
              onChange={(event) => setWechat(event.target.value)}
              className={INPUT}
            />
          </label>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button type="submit" disabled={pending} className={PRIMARY}>
            {pending ? "Enregistrement…" : "Enregistrer"}
          </button>
          {saved && (
            <span role="status" className="text-sm text-emerald-600">
              {t("liste.enregistre")}
            </span>
          )}
        </div>
      </form>
    </section>
  );
}

/**
 * Le prochain rendez-vous, en grand.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi il mérite son propre composant
 * ---------------------------------------------------------------------------
 *
 * Parce qu'on ouvre cet espace pour lui. Neuf visites sur dix se résument à
 * « c'est quand déjà, et chez qui ». Le noyer dans une liste où il ressemble
 * aux visites d'il y a six mois oblige à chercher ce qu'on est venu voir.
 *
 * Le compte à rebours en clair — « dans 3 jours » — plutôt qu'une date seule :
 * une date se lit, un délai se comprend. C'est aussi ce qui fait remarquer
 * qu'un rendez-vous est demain, et non la semaine prochaine.
 */
function NextBooking({
  booking,
  host,
  onCancelled,
}: {
  booking: ClientBooking;
  host: string;
  onCancelled: () => void;
}) {
  const t = useTranslations("espace");
  const status = etats(t)[booking.status] ?? {
    label: booking.status,
    className: "bg-black/[0.06] text-[var(--site-muted)]",
  };

  const start = new Date(booking.starts_at);
  const when = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).format(start);

  const salonUrl = salonOrigin(booking.salon_slug, host);
  const maps = booking.address
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(booking.address)}`
    : null;

  return (
    <section className={`${CARD} mb-6 overflow-hidden`}>
      {/* Bandeau de marque : on sait chez qui on va avant même de lire. */}
      <div className="salon-gradient px-4 py-2.5 text-white sm:px-5">
        <p className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="font-medium">{countdown(start, t)}</span>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
              booking.payment_token ? "bg-white text-amber-700" : "bg-white/20"
            }`}
          >
            {status.label}
          </span>
        </p>
      </div>

      {/*
        Le suivi, tout en haut de la carte.

        La pastille du bandeau dit l'état ; le chemin dit ce qui reste. Sans
        lui, une cliente qui vient de régler son acompte ne sait pas si le
        salon doit encore valider, et elle rappelle le salon pour le demander.
      */}
      <div className="border-b border-[var(--site-line)] px-4 pb-4 pt-4 sm:px-5">
        <Tracker booking={booking} />
      </div>

      <div className="p-4 sm:p-5">
        <h2 className="text-lg font-semibold text-[var(--site-ink)] sm:text-xl">
          {booking.service_name}
        </h2>
        {/* `first-letter` et non `capitalize` : ce dernier met une majuscule
            à chaque mot — « Vendredi 11 Septembre À 11:15 ». */}
        <p className="mt-0.5 text-sm text-[var(--site-muted)] first-letter:uppercase">
          {when}
        </p>

        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
          <div className="min-w-0">
            <dt className="text-xs text-[var(--site-subtle)]">Salon</dt>
            <dd className="truncate">
              <a
                href={salonUrl}
                className="font-medium text-[var(--salon-ink)] hover:underline"
              >
                {booking.salon_name}
              </a>
            </dd>
          </div>

          {booking.staff_member_name && (
            <div className="min-w-0">
              <dt className="text-xs text-[var(--site-subtle)]">
                {t("liste.avec")}
              </dt>
              <dd className="truncate text-[var(--site-ink)]">
                {booking.staff_member_name}
              </dd>
            </div>
          )}

          <div>
            <dt className="text-xs text-[var(--site-subtle)]">Total</dt>
            <dd className="tabular font-medium text-[var(--site-ink)]">
              {formatPrice(booking.total_amount, booking.currency)}
            </dd>
          </div>

          {Number(booking.deposit_amount) > 0 && (
            <div>
              <dt className="text-xs text-[var(--site-subtle)]">Acompte</dt>
              <dd className="tabular text-[var(--site-ink)]">
                {formatPrice(booking.deposit_amount, booking.currency)}
              </dd>
            </div>
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

        {booking.travel_zone_name && (
          <p className="mt-3 flex items-start gap-2 text-sm text-[var(--site-muted)]">
            <SalonIcon name="pin" className="mt-0.5 size-4 shrink-0" />
            <span>
              À domicile · {booking.travel_zone_name}
              {booking.address && (
                <span className="block">{booking.address}</span>
              )}
            </span>
          </p>
        )}

        {/* Le laissez-passer d'arrivée.

            Il n'apparaît qu'une fois le salon d'accord : le montrer avant
            laisserait croire qu'il vaut confirmation, et on se présenterait
            pour un créneau que personne n'a accepté. */}
        {booking.checkin_token && (
          <CheckinCode
            token={booking.checkin_token}
            code={booking.checkin_code}
          />
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          {booking.payment_token && (
            <Lien
              href={`/paiement?token=${encodeURIComponent(booking.payment_token)}`}
              className={`${PRIMARY} px-4 py-2.5 text-sm`}
            >
              {t("liste.reglerAcompte")}
            </Lien>
          )}

          {/*
            Le suivi détaillé.

            Cette carte montre l'essentiel ; elle ne peut pas montrer ce que
            le salon a réellement encaissé, par quel moyen, ni le motif d'un
            refus, sans devenir la page qu'elle remplace. Le lien part vers
            le sous-domaine du salon concerné : une cliente peut avoir des
            rendez-vous dans plusieurs salons, et chaque page de suivi
            n'existe que chez le sien.
          */}
          <a
            href={`${salonUrl}/rendez-vous?token=${encodeURIComponent(booking.status_token)}`}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--site-line)] px-4 py-2.5 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]"
          >
            <SalonIcon name="sparkle" className="size-4" />
            {t("liste.suivre")}
          </a>

          {maps && (
            <a
              href={maps}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--site-line)] px-4 py-2.5 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]"
            >
              <SalonIcon name="pin" className="size-4" />
              {t("liste.itineraire")}
            </a>
          )}
          <a
            href={salonUrl}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--site-line)] px-4 py-2.5 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]"
          >
            <SalonIcon name="store" className="size-4" />
            {t("liste.leSalon")}
          </a>
        </div>

        {/*
          L'annulation, en bas et en retrait.

          Elle est la dernière chose de la carte, et volontairement la moins
          voyante : c'est une sortie, pas une action qu'on propose. Mais
          elle est là — la cacher revenait à obliger à téléphoner pour un
          geste que le salon autorise par écrit.
        */}
        <Annuler
          booking={booking}
          host={host}
          salonUrl={salonUrl}
          onDone={onCancelled}
        />
      </div>
    </section>
  );
}

/** Adresse du mini-site d'un salon, en développement comme en production. */
function salonOrigin(slug: string, host: string): string {
  return host.includes("localhost")
    ? `http://${slug}.localhost:3100`
    : `https://${slug}.${host.split(".").slice(1).join(".")}`;
}

/**
 * « demain », « dans 3 jours », « dans 2 semaines ».
 *
 * Une date se lit, un délai se comprend — et c'est le délai qui fait
 * remarquer qu'un rendez-vous est demain plutôt que la semaine prochaine.
 */
/* Le traducteur arrive en paramètre : ce n'est pas un composant, et un
   crochet React n'a rien à faire dans une fonction ordinaire. */
function countdown(
  start: Date,
  t: (cle: string, vars?: Record<string, string | number | Date>) => string,
): string {
  const days = Math.round((start.getTime() - Date.now()) / 86_400_000);

  if (days < 0) return t("liste.passe");
  if (days === 0) return t("liste.aujourdhui");
  if (days === 1) return t("liste.demain");
  if (days < 7) return t("liste.dansJours", { n: days });
  if (days < 14) return t("liste.dansUneSemaine");
  if (days < 31) return t("liste.dansSemaines", { n: Math.round(days / 7) });
  return t("liste.dansMois", { n: Math.round(days / 30) });
}

/** « ven. 11 sept. · 14:00 » — assez pour reconnaître une visite passée. */
/**
 * Ce qu'il reste avant la date limite, en jours.
 *
 * En jours et non en date : « il vous reste 6 jours » se comprend sans
 * calcul, « jusqu'au 16 octobre » demande de savoir quel jour on est. Au
 * dernier jour on le dit autrement — « dernier jour » porte l'urgence que
 * « 1 jour » ne porte pas.
 *
 * Le décompte est arrondi au supérieur : une échéance à 6 h ce soir est
 * encore « aujourd'hui », pas « 0 jour ».
 */
function remaining(
  iso: string,
  t: (cle: string, vars?: Record<string, string | number | Date>) => string,
): string {
  if (!iso) return "";
  const days = Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
  if (days <= 0) return t("liste.dernieresHeures");
  if (days === 1) return t("liste.dernierJour");
  return t("liste.joursRestants", { n: days });
}

function shortDate(iso: string): string {
  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}
