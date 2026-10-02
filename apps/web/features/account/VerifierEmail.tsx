"use client";

/**
 * La page ouverte depuis le lien « Confirmez votre adresse e-mail ».
 *
 * Le jeton arrive dans l'adresse ; il est envoyé au serveur une seule fois,
 * puis retiré de la barre d'adresse (il n'a plus rien à faire dans
 * l'historique ni dans un éventuel en-tête Referer).
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { verifierAdresse } from "@/lib/dashboard";
import { Card } from "@/features/ui";

type Etat = "attente" | "ok" | "erreur";

export function VerifierEmail() {
  const [etat, setEtat] = useState<Etat>("attente");
  const [message, setMessage] = useState("");
  const envoye = useRef(false);

  useEffect(() => {
    if (envoye.current) return; // double montage en développement
    envoye.current = true;
    const token = new URLSearchParams(window.location.search).get("token") ?? "";
    window.history.replaceState(null, "", window.location.pathname);
    if (!token) {
      // Après le rendu, et non pendant l'effet : pas de rendu en cascade.
      void Promise.resolve().then(() => {
        setEtat("erreur");
        setMessage("Ce lien est incomplet. Ouvrez celui reçu par e-mail, ou demandez-en un nouveau.");
      });
      return;
    }
    verifierAdresse(token)
      .then(() => setEtat("ok"))
      .catch((erreur: unknown) => {
        setEtat("erreur");
        setMessage(
          erreur instanceof Error
            ? erreur.message
            : "La vérification a échoué. Réessayez dans un instant.",
        );
      });
  }, []);

  return (
    <Card>
      {etat === "attente" && (
        <p className="flex items-center gap-2 text-sm text-muted" role="status">
          <span className="size-4 animate-spin rounded-full border-2 border-line border-t-salon" />
          Vérification de votre adresse…
        </p>
      )}

      {etat === "ok" && (
        <div role="status">
          <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-success-bg text-success">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="size-6" aria-hidden>
              <path d="M20 6 9 17l-5-5" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <h1 className="mt-4 text-xl font-semibold tracking-tight text-ink">Adresse confirmée</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Merci ! Votre adresse e-mail est vérifiée. Toutes les fonctions de votre espace sont
            ouvertes.
          </p>
          <Link
            href="/"
            className="mt-6 inline-flex items-center justify-center rounded-lg bg-salon px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:brightness-110"
          >
            Accéder à mon espace
          </Link>
        </div>
      )}

      {etat === "erreur" && (
        <div role="alert">
          <h1 className="text-xl font-semibold tracking-tight text-ink">Lien non valable</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">{message}</p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Connectez-vous : un bandeau en haut de votre espace permet de recevoir un nouveau lien.
          </p>
          <Link
            href="/"
            className="mt-6 inline-flex items-center justify-center rounded-lg border border-line px-4 py-2.5 text-sm font-medium text-ink transition hover:bg-surface-hover"
          >
            Se connecter
          </Link>
        </div>
      )}
    </Card>
  );
}
