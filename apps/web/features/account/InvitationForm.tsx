"use client";

/**
 * Acceptation d'une invitation d'équipe.
 *
 * Le lien reçu par e-mail vaut preuve d'identité : c'est lui qui autorise la
 * création du compte. On ne demande donc un mot de passe que si la personne
 * n'en a pas déjà un — quelqu'un qui travaille dans un autre salon rejoint
 * l'équipe en un clic.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import {
  DashboardError,
  acceptInvitation,
  fetchInvitation,
  type InvitationPreview,
} from "@/lib/dashboard";
import {
  Badge,
  Button,
  Card,
  Field,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";

export function InvitationForm() {
  const toast = useToast();
  const token = useSearchParams().get("token") ?? "";

  const [invitation, setInvitation] = useState<InvitationPreview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    fetchInvitation(token)
      .then((data) => {
        if (!cancelled) setInvitation(data);
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadError(
          error instanceof DashboardError
            ? error.message
            : "Cette invitation n'est plus valable.",
        );
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);

    const ok = await toast.run(
      () =>
        acceptInvitation({
          token,
          password: invitation?.account_exists ? undefined : password,
          display_name: displayName || undefined,
        }),
      {
        success: `Vous faites partie de l'équipe de ${invitation?.salon_name}.`,
      },
    );

    setPending(false);
    if (ok) setDone(true);
  }

  // Déduit du rendu plutôt que posé dans l'effet : modifier l'état de façon
  // synchrone dans un effet déclenche un second rendu inutile.
  const message = token ? loadError : "Lien d'invitation incomplet.";

  if (message) {
    return (
      <Card>
        <h1 className="text-xl font-semibold tracking-tight text-ink">
          Invitation indisponible
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">{message}</p>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Une invitation est valable 7 jours. Demandez au salon de vous en
          envoyer une nouvelle.
        </p>
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
          Bienvenue dans l&apos;équipe
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Vous faites maintenant partie de {invitation?.salon_name}.
        </p>
        <Link
          href="/"
          className="mt-6 inline-flex items-center justify-center rounded-lg bg-salon px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:brightness-110"
        >
          Accéder à l&apos;espace
        </Link>
      </Card>
    );
  }

  if (!invitation) {
    return <Skeleton rows={3} />;
  }

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Rejoindre {invitation.salon_name}
        </h1>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
          <span>{invitation.email}</span>
          <Badge tone="salon">{invitation.role_display}</Badge>
        </p>
      </div>

      <Card>
        <form onSubmit={submit}>
          {invitation.account_exists ? (
            <p className="mb-5 rounded-lg bg-info-bg p-3 text-sm text-info">
              Vous avez déjà un compte Beauty Salon. Acceptez l&apos;invitation
              pour ajouter ce salon — vous basculerez de l&apos;un à
              l&apos;autre depuis le menu.
            </p>
          ) : (
            <>
              <Field label="Votre nom" className="mb-4">
                <input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  autoComplete="name"
                  className={inputClass}
                />
              </Field>

              <Field
                label="Mot de passe"
                hint="Au moins 10 caractères."
                className="mb-5"
              >
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={10}
                  required
                  className={inputClass}
                />
              </Field>
            </>
          )}

          <Button type="submit" pending={pending} className="w-full">
            Rejoindre l&apos;équipe
          </Button>
        </form>
      </Card>
    </>
  );
}
