"use client";

/**
 * Confirmation d'adresse e-mail d'une cliente, sur le mini-site du salon.
 *
 * Même logique que l'espace professionnel (`features/account/VerifierEmail`) :
 * le jeton part une fois au serveur puis quitte la barre d'adresse. Seul
 * l'habillage change — celui du salon, dans la langue du site.
 */

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { SalonLogo } from "@/features/salon/SalonLogo";
import { AuthShell, authCard, authLead, authTitle } from "@/features/ui/AuthShell";
import { Lien } from "@/features/ui/Lien";
import { ThemeToggle } from "@/features/ui/ThemeToggle";
import type { PublicSalon } from "@/lib/types";

import { api } from "./api";

const PRIMARY =
  "mt-6 inline-flex w-full items-center justify-center rounded-xl bg-[var(--salon-primary)] px-5 py-3 font-semibold text-white shadow-sm transition hover:brightness-110";

type Etat = "attente" | "ok" | "erreur";

export function VerifierEmailCliente({ salon, host }: { salon: PublicSalon; host: string }) {
  const t = useTranslations("espace.verification");
  const [etat, setEtat] = useState<Etat>("attente");
  const [message, setMessage] = useState("");
  const envoye = useRef(false);

  useEffect(() => {
    if (envoye.current) return;
    envoye.current = true;
    const token = new URLSearchParams(window.location.search).get("token") ?? "";
    window.history.replaceState(null, "", window.location.pathname);
    if (!token) {
      // Après le rendu, et non pendant l'effet : pas de rendu en cascade.
      void Promise.resolve().then(() => {
        setEtat("erreur");
        setMessage(t("incomplet"));
      });
      return;
    }
    api("/api/v1/account/email/verify", host, {
      method: "POST",
      body: JSON.stringify({ token }),
    })
      .then(() => setEtat("ok"))
      .catch((erreur: unknown) => {
        setEtat("erreur");
        setMessage(erreur instanceof Error ? erreur.message : t("echec"));
      });
  }, [host, t]);

  return (
    <AuthShell
      homeHref="/"
      homeLabel={salon.name}
      brand={
        <>
          <SalonLogo logo={salon.logo} name={salon.name} className="size-8 text-xs" />
          <span className="truncate font-semibold tracking-tight text-ink">{salon.name}</span>
        </>
      }
      action={<ThemeToggle />}
    >
      <div className={authCard}>
        {etat === "attente" && (
          <p className="flex items-center gap-2 text-sm text-ink/75" role="status">
            <span className="size-4 animate-spin rounded-full border-2 border-line border-t-[var(--salon-primary)]" />
            {t("attente")}
          </p>
        )}
        {etat === "ok" && (
          <div role="status">
            <h1 className={authTitle}>{t("okTitre")}</h1>
            <p className={authLead}>{t("okCorps")}</p>
            <Lien href="/compte" className={PRIMARY}>
              {t("monEspace")}
            </Lien>
          </div>
        )}
        {etat === "erreur" && (
          <div role="alert">
            <h1 className={authTitle}>{t("erreurTitre")}</h1>
            <p className={authLead}>{message}</p>
            <p className={authLead}>{t("erreurAide")}</p>
            <Lien href="/compte" className={PRIMARY}>
              {t("monEspace")}
            </Lien>
          </div>
        )}
      </div>
    </AuthShell>
  );
}
