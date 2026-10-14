"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { dashboardFetch } from "@/lib/dashboard";
import { Button, Card, ErrorState, Field, inputClass, Skeleton } from "@/features/ui";
import { useFormats } from "./formats";
import { useResource } from "./useResource";

interface Configuration {
  active: boolean; taux: string | null; validite_jours: number | null;
  plafond_montant: string | null; devise: string; nature_plafond: string;
}
interface Donnees {
  configuration: Configuration;
  historique: { id: string; action: string; cree_le: string }[];
}

export function ParrainageClients({ tenantId, devise }: { tenantId: string; devise: string }) {
  const t = useTranslations("pro.parrainage.clients");
  const resource = useResource<Donnees>("/api/v1/parrainage/clients", tenantId);
  if (resource.error) return <ErrorState>{t("erreur")}</ErrorState>;
  if (!resource.data) return <Skeleton rows={2} />;
  return <ConfigurationClients key={`${resource.data.configuration.active}-${resource.data.configuration.taux}-${resource.data.configuration.validite_jours}-${resource.data.configuration.plafond_montant}`}
    tenantId={tenantId} devise={devise} data={resource.data} onSaved={resource.reload} />;
}

function ConfigurationClients({ tenantId, devise, data, onSaved }: {
  tenantId: string; devise: string; data: Donnees; onSaved: () => void;
}) {
  const t = useTranslations("pro.parrainage.clients");
  const { region } = useFormats();
  const [config, setConfig] = useState(data.configuration);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function enregistrer(e: React.FormEvent) {
    e.preventDefault(); setPending(true); setError(null);
    try {
      await dashboardFetch("/api/v1/parrainage/clients", { method: "PATCH", body: JSON.stringify({
        ...config, devise, nature_plafond: "montant_par_reservation",
      }) }, tenantId);
      onSaved();
    } catch (err) { setError(err instanceof Error ? err.message : t("invalide")); }
    finally { setPending(false); }
  }
  return <section className="mb-8 min-w-0">
    <h2 className="mb-3 text-base font-semibold text-ink">{t("titre")}</h2>
    <Card>
      <p className="mb-4 text-xs leading-relaxed text-muted sm:text-sm">{t("intro")}</p>
      <form onSubmit={(e) => void enregistrer(e)} className="grid grid-cols-2 gap-3">
        <Field label={t("reduction")} hint={t("reductionAide")}>
          <input className={inputClass} type="number" min="10" max="100" step="0.01" required={config.active}
            value={config.taux ?? ""} onChange={(e) => setConfig({ ...config, taux: e.target.value || null })} />
        </Field>
        <Field label={t("validite")}>
          <input className={inputClass} type="number" min="1" required={config.active} value={config.validite_jours ?? ""}
            onChange={(e) => setConfig({ ...config, validite_jours: e.target.value ? Number(e.target.value) : null })} />
        </Field>
        <Field label={t("plafond", { devise })}>
          <input className={inputClass} type="number" min="0.01" step="0.01" required={config.active} value={config.plafond_montant ?? ""}
            onChange={(e) => setConfig({ ...config, plafond_montant: e.target.value || null })} />
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={config.active} onChange={(e) => setConfig({ ...config, active: e.target.checked })} /> {t("activer")}
        </label>
        <details className="col-span-2 rounded-xl border border-line bg-canvas p-3 text-xs text-muted">
          <summary className="cursor-pointer font-medium text-ink">{t("detailsTitre")}</summary>
          <p className="mt-2 leading-relaxed">{t("details")}</p>
        </details>
        {error && <div className="col-span-2"><ErrorState>{error}</ErrorState></div>}
        <Button type="submit" pending={pending} className="col-span-2 sm:col-span-1">{t("enregistrer")}</Button>
      </form>
    </Card>
    {data.historique.length > 0 && <ul className="mt-3 grid grid-cols-2 gap-2">
      {data.historique.slice(0, 12).map((evt) => <li key={evt.id} className="min-w-0 rounded-xl border border-line p-3 text-xs text-muted">
        <p className="break-words font-medium text-ink">{evt.action.replaceAll("_", " ")}</p>
        <time dateTime={evt.cree_le}>{new Date(evt.cree_le).toLocaleDateString(region)}</time>
      </li>)}
    </ul>}
  </section>;
}
