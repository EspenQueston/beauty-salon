"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { useKKiaPay } from "kkiapay-react";
import { dashboardFetch } from "@/lib/dashboard";
import { Button, ErrorState } from "@/features/ui";
import { messageKkiapayRejete } from "./kkiapayMessage.mjs";

interface Intention {
  id: string; amount: number; api_key: string; sandbox: boolean; partnerId: string;
}

let protege = false;

/** Le SDK fournisseur écoute postMessage sans vérifier l'origine : filtrer avant son chargement. */
function protegerMessages() {
  if (protege) return;
  protege = true;
  window.addEventListener("message", (event) => {
    const cadre = document.querySelector<HTMLIFrameElement>('iframe[src="https://widget-v3.kkiapay.me"]');
    if (messageKkiapayRejete(event, cadre)) event.stopImmediatePropagation();
  }, true);
}

interface Props {
  tenantId: string;
  demande?: string;
  choix?: { plan: string; country: string; currency: string; method: string; montant_attendu: string };
  onConfirme: () => void;
}

export function KkiapayButton(props: Props) {
  const t = useTranslations("pro.kkiapay");
  const [pret, setPret] = useState(false);
  useEffect(() => {
    protegerMessages();
    Promise.resolve().then(() => setPret(true));
  }, []);
  return pret ? <Paiement {...props} /> : <Button disabled>{t("chargement")}</Button>;
}

function Paiement({ tenantId, choix, demande, onConfirme }: Props) {
  const t = useTranslations("pro.kkiapay");
  const sdk = useKKiaPay();
  const intention = useRef<Intention | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verification, setVerification] = useState(false);
  const sdkPret = typeof window !== "undefined" && sdk.openKkiapayWidget ===
    (window as Window & { openKkiapayWidget?: unknown }).openKkiapayWidget;

  useEffect(() => {
    async function succes(data: { transactionId: string }) {
      if (!intention.current) return;
      setVerification(true);
      setError(null);
      try {
        await dashboardFetch("/api/v1/billing/kkiapay/confirm", { method: "POST",
          body: JSON.stringify({ intention: intention.current.id, transaction_id: data.transactionId }) }, tenantId);
        onConfirme();
      } catch {
        setError(t("enCours"));
      } finally { setVerification(false); }
    }
    sdk.addKkiapayListener("success", succes);
    sdk.addKkiapayListener("failed", () => setError(t("nonConfirme")));
    return () => { sdk.removeKkiapayListener("success"); sdk.removeKkiapayListener("failed"); };
  }, [sdk, tenantId, onConfirme, t]);

  async function payer() {
    setPending(true); setError(null);
    try {
      const i = demande
        ? await dashboardFetch<Intention>(`/api/v1/billing/kkiapay?demande=${encodeURIComponent(demande)}`, {}, tenantId)
        : await dashboardFetch<Intention>("/api/v1/billing/kkiapay", { method: "POST", body: JSON.stringify(choix) }, tenantId);
      intention.current = i;
      sdk.openKkiapayWidget({ amount: i.amount, api_key: i.api_key, sandbox: i.sandbox,
        partnerId: i.partnerId, paymentmethod: ["momo", "card"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : t("indisponible"));
    } finally { setPending(false); }
  }

  return <div className="space-y-2">
    <Button type="button" disabled={!sdkPret} pending={pending || verification} onClick={() => void payer()}>
      {verification ? t("verification") : t("payer")}
    </Button>
    {error && <ErrorState>{error}</ErrorState>}
    <p className="text-xs text-muted">{t("securise")}</p>
  </div>;
}
