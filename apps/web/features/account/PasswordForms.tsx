"use client";

/**
 * Mot de passe oublié, puis choix d'un nouveau mot de passe.
 *
 * Le premier écran répond toujours la même chose, que l'adresse existe ou
 * non : afficher « compte inconnu » transformerait ce formulaire en
 * annuaire des salons inscrits.
 */

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { confirmPasswordReset, requestPasswordReset } from "@/lib/dashboard";
import { Button, Card, Field, inputClass } from "@/features/ui";
import { PasswordField } from "@/features/ui/PasswordField";
import { useToast } from "@/features/ui/Toast";

export function ForgotPasswordForm() {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);

    const ok = await toast.run(() => requestPasswordReset(email), {
      success: "Lien envoyé. Vérifiez votre boîte mail.",
      error: "Envoi impossible. Réessayez dans un instant.",
    });

    setPending(false);
    if (ok) setSent(true);
  }

  if (sent) {
    return (
      <Card>
        <h1 className="text-xl font-semibold tracking-tight text-ink">
          Vérifiez votre boîte mail
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Si un compte existe pour <strong className="text-ink">{email}</strong>
          , un lien vient d&apos;être envoyé. Il est valable 24 heures et ne
          fonctionne qu&apos;une fois.
        </p>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Rien reçu ? Regardez dans les indésirables, puis vérifiez
          l&apos;orthographe de votre adresse.
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-lg bg-salon px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:brightness-110"
          >
            Retour à la connexion
          </Link>
          <button
            type="button"
            onClick={() => setSent(false)}
            className="inline-flex items-center justify-center rounded-lg border border-line bg-surface px-3.5 py-2 text-sm font-medium text-ink transition hover:bg-surface-hover"
          >
            Corriger mon adresse
          </button>
        </div>
      </Card>
    );
  }

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Mot de passe oublié
        </h1>
        <p className="mt-1.5 text-sm text-muted">
          Indiquez votre adresse e-mail, nous vous enverrons un lien.
        </p>
      </div>

      <Card>
        <form onSubmit={submit}>
          <Field label="E-mail" className="mb-5">
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
              className={inputClass}
            />
          </Field>

          <Button type="submit" pending={pending} className="w-full">
            Envoyer le lien
          </Button>
        </form>
      </Card>

      <p className="mt-5 text-center text-sm text-muted">
        <Link href="/" className="underline-offset-2 hover:underline">
          Retour à la connexion
        </Link>
      </p>
    </>
  );
}

export function NewPasswordForm() {
  const toast = useToast();
  const params = useSearchParams();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);

  const mismatch = confirmation.length > 0 && confirmation !== password;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (mismatch) {
      toast.error("Les deux mots de passe ne correspondent pas.");
      return;
    }
    setPending(true);

    const ok = await toast.run(
      () => confirmPasswordReset({ uid, token, password }),
      {
        success: "Mot de passe mis à jour.",
        error: "Ce lien n'est plus valable. Demandez-en un nouveau.",
      },
    );

    setPending(false);
    if (ok) setDone(true);
  }

  if (!uid || !token) {
    return (
      <Card>
        <h1 className="text-xl font-semibold tracking-tight text-ink">
          Lien incomplet
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Ouvrez le lien tel qu&apos;il figure dans l&apos;e-mail, sans le
          modifier. Certains logiciels de messagerie le coupent en deux.
        </p>
        <Link
          href="/mot-de-passe-oublie"
          className="mt-6 inline-flex items-center justify-center rounded-lg bg-salon px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:brightness-110"
        >
          Demander un nouveau lien
        </Link>
      </Card>
    );
  }

  if (done) {
    return (
      <Card>
        <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-success-bg text-success">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            className="size-6"
          >
            <path
              d="M20 6 9 17l-5-5"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <h1 className="mt-4 text-xl font-semibold tracking-tight text-ink">
          Mot de passe mis à jour
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Vous pouvez maintenant vous connecter. Les autres sessions ouvertes
          restent valides ; changez-le à nouveau si vous soupçonnez un accès non
          autorisé.
        </p>
        <Link
          href="/"
          className="mt-6 inline-flex items-center justify-center rounded-lg bg-salon px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:brightness-110"
        >
          Se connecter
        </Link>
      </Card>
    );
  }

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Nouveau mot de passe
        </h1>
        <p className="mt-1.5 text-sm text-muted">
          Choisissez un mot de passe d&apos;au moins 10 caractères.
        </p>
      </div>

      <Card>
        <form onSubmit={submit}>
          {/*
            Le même champ que sur les deux écrans de connexion, œil compris.

            C'est ici qu'il sert le plus : choisir un mot de passe de dix
            caractères à l'aveugle, puis le retaper à l'aveugle, fait échouer
            la confirmation sans qu'on sache laquelle des deux saisies était
            fautive.
          */}
          <div className="mb-4">
            <PasswordField
              label="Nouveau mot de passe"
              value={password}
              onChange={setPassword}
              autoComplete="new-password"
              inputClassName={inputClass}
              hint="Au moins 10 caractères."
            />
          </div>

          <div className="mb-5">
            <PasswordField
              label="Confirmation"
              value={confirmation}
              onChange={setConfirmation}
              autoComplete="new-password"
              inputClassName={inputClass}
            />
            {mismatch && (
              <p className="mt-1.5 text-xs font-medium text-danger">
                Les deux saisies diffèrent.
              </p>
            )}
          </div>

          <Button
            type="submit"
            pending={pending}
            disabled={mismatch || password.length < 10}
            className="w-full"
          >
            Enregistrer
          </Button>
        </form>
      </Card>
    </>
  );
}
