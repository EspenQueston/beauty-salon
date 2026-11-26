"use client";

/**
 * La page ouverte depuis le lien « Confirmez votre adresse e-mail ».
 *
 * Le jeton arrive dans l'adresse ; il est envoyé au serveur une seule fois,
 * puis retiré de la barre d'adresse (il n'a plus rien à faire dans
 * l'historique ni dans un éventuel en-tête Referer).
 */

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
// Les liens portent la langue (/en/…).
import { Lien as Link } from "@/features/ui/Lien";

import { verifierAdresse } from "@/lib/dashboard";
import { Card } from "@/features/ui";

type Etat = "attente" | "ok" | "erreur";

export function VerifierEmail() {
  const t = useTranslations("compte.verifier");
  const [etat, setEtat] = useState<Etat>("attente");
  // Le message d'erreur du serveur, ou la clé d'un message de l'écran.
  const [message, setMessage] = useState("");
  const [cle, setCle] = useState<"incomplet" | "echec" | null>(null);
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
        setCle("incomplet");
      });
      return;
    }
    verifierAdresse(token)
      .then(() => setEtat("ok"))
      .catch((erreur: unknown) => {
        setEtat("erreur");
        if (erreur instanceof Error) setMessage(erreur.message);
        else setCle("echec");
      });
  }, []);

  return (
    <Card>
      {etat === "attente" && (
        <p className="flex items-center gap-2 text-sm text-muted" role="status">
          <span className="size-4 animate-spin rounded-full border-2 border-line border-t-salon" />
          {t("attente")}
        </p>
      )}

      {etat === "ok" && (
        <div role="status">
          <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-success-bg text-success">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="size-6" aria-hidden>
              <path d="M20 6 9 17l-5-5" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <h1 className="mt-4 text-xl font-semibold tracking-tight text-ink">{t("ok.titre")}</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">{t("ok.corps")}</p>
          <Link
            href="/"
            className="mt-6 inline-flex items-center justify-center rounded-lg bg-salon px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:brightness-110"
          >
            {t("ok.acceder")}
          </Link>
        </div>
      )}

      {etat === "erreur" && (
        <div role="alert">
          <h1 className="text-xl font-semibold tracking-tight text-ink">{t("erreur.titre")}</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {cle ? t(`erreur.${cle}`) : message}
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted">{t("erreur.bandeau")}</p>
          <Link
            href="/"
            className="mt-6 inline-flex items-center justify-center rounded-lg border border-line px-4 py-2.5 text-sm font-medium text-ink transition hover:bg-surface-hover"
          >
            {t("erreur.connexion")}
          </Link>
        </div>
      )}
    </Card>
  );
}
