"use client";

/**
 * « Mot de passe oublié » de l'espace cliente, sur le mini-site du salon.
 *
 * Le lien de l'écran de connexion menait à une page de la plateforme qui
 * n'existait pas : une cliente bloquée tombait sur une erreur 404, et
 * n'avait plus aucun moyen de retrouver ses rendez-vous. Le parcours vit
 * maintenant ici, en deux temps :
 *
 *   1. `demande` — l'adresse du compte ; un lien part par e-mail, aux
 *      couleurs du salon et dans la langue du site ;
 *   2. `nouveau` — ouvert depuis ce lien : le nouveau mot de passe, deux
 *      fois, avec les critères vérifiés en direct.
 *
 * Même écran que la connexion (même coquille, même thème) : c'est la suite
 * du même geste, pas un autre site.
 */

import { useTranslations, useLocale } from "next-intl";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { SalonLogo } from "@/features/salon/SalonLogo";
import {
  AuthShell,
  authCard,
  authInput,
  authLead,
  authLink,
  authTitle,
} from "@/features/ui/AuthShell";
import { AuthShowcase } from "@/features/ui/AuthShowcase";
import { Lien } from "@/features/ui/Lien";
import { PasswordField } from "@/features/ui/PasswordField";
import { ThemeToggle } from "@/features/ui/ThemeToggle";
import type { PublicSalon } from "@/lib/types";

import { api } from "./api";

const PRIMARY =
  "inline-flex w-full items-center justify-center rounded-xl bg-[var(--salon-primary)] px-5 py-3 font-semibold text-white shadow-sm transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60";

const DELAI_RENVOI = 60;
const LONGUEUR_MIN = 10;

type Props =
  | { salon: PublicSalon; host: string; mode: "demande" }
  | { salon: PublicSalon; host: string; mode: "nouveau"; uid: string; token: string };

export function MotDePasse(props: Props) {
  const { salon } = props;
  const t = useTranslations("espace");

  // Comme l'écran de connexion : l'habillage du salon (menu, pied de page,
  // barre de réservation) disparaît le temps du formulaire.
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.authScreen = "1";
    return () => {
      delete root.dataset.authScreen;
    };
  }, []);

  return (
    <AuthShell
      homeHref="/"
      homeLabel={t("compte.retourChez", { salon: salon.name })}
      brand={
        <>
          <SalonLogo logo={salon.logo} name={salon.name} className="size-8 text-xs" />
          <span className="truncate font-semibold tracking-tight text-ink">{salon.name}</span>
        </>
      }
      action={<ThemeToggle />}
      aside={
        <AuthShowcase
          seed={salon.slug}
          title={t("mdp.asideTitre")}
          points={[
            { title: t("mdp.asideLienTitre"), body: t("mdp.asideLienCorps") },
            { title: t("mdp.asideRdvTitre"), body: t("mdp.asideRdvCorps") },
            { title: t("mdp.asideSansTitre"), body: t("mdp.asideSansCorps") },
          ]}
        />
      }
    >
      <div className={authCard}>
        {props.mode === "demande" ? (
          <Demande host={props.host} />
        ) : (
          <Nouveau salon={salon} uid={props.uid} token={props.token} host={props.host} />
        )}
      </div>

      <p className="mt-5 text-center text-sm text-ink/75">
        <Lien href="/compte" className={authLink}>
          {t("mdp.retourConnexion")}
        </Lien>
      </p>
    </AuthShell>
  );
}

// ---------------------------------------------------------------------------
// 1. La demande
// ---------------------------------------------------------------------------

function Demande({ host }: { host: string }) {
  const t = useTranslations("espace.mdp");
  const langue = useLocale();
  const [email, setEmail] = useState("");
  const [envoye, setEnvoye] = useState(false);
  const [pending, setPending] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [attente, setAttente] = useState(0);

  // Le compte à rebours du renvoi : un clic par minute, pas davantage — le
  // serveur borne de toute façon, mais un bouton grisé se comprend mieux
  // qu'un refus.
  useEffect(() => {
    if (attente <= 0) return;
    const minuterie = window.setTimeout(() => setAttente((s) => s - 1), 1000);
    return () => window.clearTimeout(minuterie);
  }, [attente]);

  async function envoyer(event?: FormEvent) {
    event?.preventDefault();
    setPending(true);
    setErreur(null);
    try {
      await api("/api/v1/public/client/password/reset", host, {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), lang: langue }),
      });
      setEnvoye(true);
      setAttente(DELAI_RENVOI);
    } catch (caught) {
      setErreur(caught instanceof Error && caught.message ? caught.message : t("erreur"));
    } finally {
      setPending(false);
    }
  }

  if (envoye) {
    return (
      <div className="text-center">
        <Pastille>
          <path d="M3.5 7.5A2 2 0 0 1 5.5 5.5h13a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />
          <path d="m4.5 7.5 7.5 5.5 7.5-5.5" />
        </Pastille>
        <h1 className={`${authTitle} mt-4`}>{t("verifiez")}</h1>
        <p className={authLead}>{t("verifiezCorps", { email: email.trim() })}</p>
        <p className="mt-4 rounded-xl bg-surface-muted px-3.5 py-3 text-left text-[13px] leading-relaxed text-muted sm:text-sm">
          {t("astuce")}
        </p>
        <div className="mt-5 grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={() => void envoyer()}
            disabled={attente > 0 || pending}
            className="rounded-xl border border-line px-3 py-2.5 text-[13px] font-medium text-ink transition hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-55 sm:text-sm"
          >
            {attente > 0 ? t("renvoyerDans", { s: attente }) : t("renvoyer")}
          </button>
          <button
            type="button"
            onClick={() => {
              setEnvoye(false);
              setAttente(0);
            }}
            className="rounded-xl border border-line px-3 py-2.5 text-[13px] font-medium text-ink transition hover:bg-surface-hover sm:text-sm"
          >
            {t("autreAdresse")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <h1 className={authTitle}>{t("titreDemande")}</h1>
      <p className={authLead}>{t("leadDemande")}</p>
      <form onSubmit={(event) => void envoyer(event)} className="mt-6 space-y-4">
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-ink">E-mail</span>
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            type="email"
            inputMode="email"
            autoComplete="email"
            autoFocus
            required
            className={authInput}
          />
        </label>
        {erreur && <Erreur>{erreur}</Erreur>}
        <button type="submit" disabled={pending} className={PRIMARY}>
          {pending ? t("envoi") : t("envoyer")}
        </button>
      </form>
    </>
  );
}

// ---------------------------------------------------------------------------
// 2. Le nouveau mot de passe
// ---------------------------------------------------------------------------

function Nouveau({
  salon,
  uid,
  token,
  host,
}: {
  salon: PublicSalon;
  uid: string;
  token: string;
  host: string;
}) {
  const t = useTranslations("espace.mdp");
  const [motDePasse, setMotDePasse] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [etat, setEtat] = useState<"saisie" | "fait" | "invalide">(
    uid && token ? "saisie" : "invalide",
  );

  const assezLong = motDePasse.length >= LONGUEUR_MIN;
  const identiques = motDePasse.length > 0 && motDePasse === confirmation;

  async function enregistrer(event: FormEvent) {
    event.preventDefault();
    if (!assezLong || !identiques) return;
    setPending(true);
    setErreur(null);
    try {
      await api("/api/v1/account/password/reset/confirm", host, {
        method: "POST",
        body: JSON.stringify({ uid, token, password: motDePasse }),
      });
      setEtat("fait");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "";
      // Jeton expiré ou déjà servi : l'écran le dit et propose la suite,
      // plutôt qu'un message d'erreur qu'on ne sait pas quoi faire.
      if (/lien|link|invalid/i.test(message)) setEtat("invalide");
      else setErreur(message || t("erreur"));
    } finally {
      setPending(false);
    }
  }

  if (etat === "fait") {
    return (
      <div className="text-center">
        <Pastille>
          <path d="M20 6 9 17l-5-5" />
        </Pastille>
        <h1 className={`${authTitle} mt-4`}>{t("succes")}</h1>
        <p className={authLead}>{t("succesCorps")}</p>
        <Lien href="/compte" className={`${PRIMARY} mt-6`}>
          {t("seConnecter")}
        </Lien>
      </div>
    );
  }

  if (etat === "invalide") {
    return (
      <div className="text-center">
        <Pastille ton="alerte">
          <path d="M12 8v5M12 16.5v.01" />
          <circle cx="12" cy="12" r="9" />
        </Pastille>
        <h1 className={`${authTitle} mt-4`}>{t("lienInvalide")}</h1>
        <p className={authLead}>{t("lienInvalideCorps")}</p>
        <Lien href="/compte/mot-de-passe-oublie" className={`${PRIMARY} mt-6`}>
          {t("nouveauLien")}
        </Lien>
      </div>
    );
  }

  return (
    <>
      <h1 className={authTitle}>{t("titreNouveau")}</h1>
      <p className={authLead}>{t("leadNouveau", { salon: salon.name })}</p>
      <form onSubmit={(event) => void enregistrer(event)} className="mt-6 space-y-4">
        <PasswordField
          label={t("nouveau")}
          value={motDePasse}
          onChange={setMotDePasse}
          autoComplete="new-password"
          autoFocus
          inputClassName={authInput}
        />
        <PasswordField
          label={t("confirmer")}
          value={confirmation}
          onChange={setConfirmation}
          autoComplete="new-password"
          inputClassName={authInput}
        />

        {/* Les deux critères, cochés en direct : on sait avant d'envoyer. */}
        <ul className="grid grid-cols-2 gap-2 text-[12px] sm:text-[13px]">
          <Critere ok={assezLong}>{t("critereLongueur")}</Critere>
          <Critere ok={identiques}>{t("critereIdentiques")}</Critere>
        </ul>

        {erreur && <Erreur>{erreur}</Erreur>}
        <button type="submit" disabled={pending || !assezLong || !identiques} className={PRIMARY}>
          {pending ? t("envoi") : t("enregistrer")}
        </button>
      </form>
    </>
  );
}

// ---------------------------------------------------------------------------
// Petits morceaux
// ---------------------------------------------------------------------------

function Pastille({ children, ton = "marque" }: { children: ReactNode; ton?: "marque" | "alerte" }) {
  return (
    <span
      className={`mx-auto flex size-14 items-center justify-center rounded-2xl ${
        ton === "alerte" ? "bg-danger-bg text-danger" : "bg-[var(--salon-primary)]/12 text-[var(--salon-primary)]"
      }`}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
        className="size-7"
      >
        {children}
      </svg>
    </span>
  );
}

function Critere({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <li
      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-2 transition-colors ${
        ok ? "bg-success-bg text-success" : "bg-surface-muted text-muted"
      }`}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
        className="size-3.5 shrink-0"
      >
        {ok ? <path d="M20 6 9 17l-5-5" /> : <circle cx="12" cy="12" r="7" />}
      </svg>
      {children}
    </li>
  );
}

function Erreur({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-xl bg-danger-bg p-3 text-sm font-medium text-danger">
      {children}
    </p>
  );
}
