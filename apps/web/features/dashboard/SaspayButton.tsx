"use client";

/**
 * Régler l'abonnement par SASPAY.
 *
 * Le salon paie sur la page hébergée par SASPAY (Mobile Money ou carte),
 * puis revient ici avec `?saspay=<intention>`. Ce retour ne prouve rien : il
 * déclenche seulement une vérification, faite par le serveur auprès de
 * l'API SASPAY. Si le paiement n'est pas encore confirmé — une validation
 * Mobile Money peut prendre quelques instants — le serveur le rattrapera de
 * lui-même (webhook signé, puis vérification périodique) ; la page, qui se
 * relit tant qu'un paiement attend, s'ouvrira alors toute seule.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { dashboardFetch } from "@/lib/dashboard";
import { Button, ErrorState, GhostButton } from "@/features/ui";

interface Intention {
  id: string;
  checkout_url: string;
  statut: string;
}

interface Verification {
  confirme: boolean;
  statut: string;
}

/** Seule une page SASPAY peut recevoir le salon : jamais une adresse arbitraire. */
function versSaspay(adresse: string) {
  const url = new URL(adresse);
  if (url.protocol !== "https:" || !/(^|\.)saspay\.me$/.test(url.hostname)) {
    throw new Error("adresse");
  }
  window.location.assign(url.toString());
}

interface ChoixProps {
  tenantId: string;
  choix: { plan: string; country: string; currency: string; method: string; montant_attendu: string };
}

/** Le bouton de la commande : ouvre le paiement et part sur la page SASPAY. */
export function SaspayButton({ tenantId, choix }: ChoixProps) {
  const t = useTranslations("pro.saspay");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function payer() {
    setPending(true);
    setError(null);
    try {
      const intention = await dashboardFetch<Intention>(
        "/api/v1/billing/saspay",
        { method: "POST", body: JSON.stringify(choix) },
        tenantId,
      );
      versSaspay(intention.checkout_url);
    } catch (e) {
      setError(e instanceof Error && e.message !== "adresse" ? e.message : t("indisponible"));
      setPending(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button type="button" pending={pending} onClick={() => void payer()}>
        {pending ? t("redirection") : t("payer")}
      </Button>
      {error && <ErrorState>{error}</ErrorState>}
      <p className="text-xs text-muted">{t("securise")}</p>
    </div>
  );
}

interface AttenteProps {
  tenantId: string;
  demande: string;
  onConfirme: () => void;
}

/**
 * Sous un paiement SASPAY en attente : reprendre la page de paiement, ou
 * demander la vérification. Au retour de SASPAY, la vérification part seule.
 */
export function SaspayEnAttente({ tenantId, demande, onConfirme }: AttenteProps) {
  const t = useTranslations("pro.saspay");
  const [action, setAction] = useState<"reprendre" | "verifier" | null>(null);
  const [message, setMessage] = useState<{ ton: "info" | "erreur"; texte: string } | null>(null);
  const dejaVerifie = useRef(false);

  const lire = useCallback(
    () =>
      dashboardFetch<Intention>(
        `/api/v1/billing/saspay?demande=${encodeURIComponent(demande)}`,
        {},
        tenantId,
      ),
    [demande, tenantId],
  );

  const verifier = useCallback(
    async (intention?: string) => {
      setAction("verifier");
      setMessage(null);
      try {
        const id = intention ?? (await lire()).id;
        const resultat = await dashboardFetch<Verification>(
          "/api/v1/billing/saspay/confirm",
          { method: "POST", body: JSON.stringify({ intention: id }) },
          tenantId,
        );
        if (resultat.confirme) {
          setMessage({ ton: "info", texte: t("confirme") });
          onConfirme();
        } else {
          setMessage({ ton: "info", texte: t("pasEncore") });
        }
      } catch {
        setMessage({ ton: "erreur", texte: t("erreur") });
      } finally {
        setAction(null);
      }
    },
    [lire, onConfirme, t, tenantId],
  );

  // Retour de la page SASPAY : une vérification, une seule, puis l'adresse
  // redevient propre (un rechargement ne relance rien).
  useEffect(() => {
    if (dejaVerifie.current) return;
    const url = new URL(window.location.href);
    const intention = url.searchParams.get("saspay");
    if (!intention) return;
    dejaVerifie.current = true;
    url.searchParams.delete("saspay");
    window.history.replaceState(null, "", url.toString());
    // Après le rendu : l'effet ne pose pas d'état lui-même.
    void Promise.resolve().then(() => verifier(intention));
  }, [verifier]);

  async function reprendre() {
    setAction("reprendre");
    setMessage(null);
    try {
      versSaspay((await lire()).checkout_url);
    } catch {
      setMessage({ ton: "erreur", texte: t("indisponible") });
      setAction(null);
    }
  }

  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button type="button" pending={action === "reprendre"} onClick={() => void reprendre()}>
          {t("reprendre")}
        </Button>
        <GhostButton type="button" disabled={action !== null} onClick={() => void verifier()}>
          {action === "verifier" ? t("verification") : t("verifier")}
        </GhostButton>
      </div>
      {message?.ton === "erreur" && <ErrorState>{message.texte}</ErrorState>}
      {message?.ton === "info" && (
        <p role="status" className="text-[12.5px] leading-relaxed text-muted sm:text-sm">
          {message.texte}
        </p>
      )}
    </div>
  );
}
