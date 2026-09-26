"use client";

/**
 * Domaine personnalisé (offre Pro) : relier un domaine que le salon possède.
 *
 * Trois temps, dans cet ordre, parce que c'est l'ordre du registraire :
 *
 *   1. le salon saisit son domaine — la plateforme ne l'achète pas ;
 *   2. il crée deux enregistrements chez son registraire : un TXT, qui prouve
 *      qu'il contrôle le domaine, et un A ou un CNAME, qui l'amène ici ;
 *   3. il demande la vérification. Le serveur lit le DNS lui-même : rien de
 *      ce que dit l'écran ne vaut preuve.
 *
 * Le DNS met parfois des heures à se propager : l'écran le dit, et la
 * vérification se relance d'un geste.
 */

import { useState, type FormEvent } from "react";

import { DashboardError, dashboardFetch } from "@/lib/dashboard";
import {
  Badge,
  Button,
  Card,
  DangerButton,
  EmptyState,
  ErrorState,
  Field,
  GhostButton,
  PageHeader,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { dateLongue } from "./abonnement";
import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";
import { EnteteCarte, VerrouPro, useFonction } from "./Pro";
import { useResource } from "./useResource";

interface Enregistrement {
  type: "TXT" | "A" | "CNAME";
  nom: string;
  valeur: string;
}

interface Domaine {
  id: string;
  hostname: string;
  status: "pending" | "connected";
  relie: boolean;
  en_pause: boolean;
  derniere_erreur: string;
  verifie_le: string | null;
  consignes: { txt: Enregistrement; routage: Enregistrement };
  adresse_gratuite: string;
}

export function DomainePerso() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const proprietaire = membership.role === "owner";
  const ouvert = useFonction("custom_domain");
  const toast = useToast();

  const domaines = useResource<Domaine[]>("/api/v1/domaines", tenantId, {
    enabled: proprietaire,
  });
  const [saisie, setSaisie] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  if (!proprietaire) {
    return (
      <section>
        <PageHeader title="Domaine personnalisé" />
        <EmptyState title="Réservé au propriétaire">
          Relier un domaine engage l&apos;adresse publique du salon : c&apos;est le
          propriétaire qui s&apos;en charge.
        </EmptyState>
      </section>
    );
  }

  async function ajouter(event: FormEvent) {
    event.preventDefault();
    setErreur(null);
    const hostname = saisie.trim();
    if (!hostname) return;
    setEnvoi(true);
    try {
      await dashboardFetch(
        "/api/v1/domaines",
        { method: "POST", body: JSON.stringify({ hostname }) },
        tenantId,
      );
      setSaisie("");
      toast.success("Domaine ajouté. Créez maintenant les deux enregistrements DNS.");
      domaines.reload();
    } catch (caught) {
      setErreur(caught instanceof DashboardError ? caught.message : "Ajout impossible.");
    } finally {
      setEnvoi(false);
    }
  }

  const liste = domaines.data ?? [];

  return (
    <section>
      <PageHeader
        title="Domaine personnalisé"
        description="Votre mini-site sur votre propre nom de domaine — www.monsalon.com plutôt qu'une adresse Beauty Salon."
      />

      {ouvert === false && <VerrouPro fonction="custom_domain" />}

      <div className="grid gap-4 lg:grid-cols-[1fr_20rem] lg:items-start">
        <div className="space-y-4">
          <Card padded={false} className="p-4 sm:p-5">
            <EnteteCarte
              icone="globe"
              titre="Ajouter un domaine"
              detail="Un domaine que vous possédez déjà, acheté chez un registraire (OVH, GoDaddy, Namecheap, Alibaba Cloud…)."
            />
            <form onSubmit={ajouter} className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-start">
              <Field label="Domaine" className="min-w-0 flex-1" error={erreur ?? undefined}>
                <input
                  className={inputClass}
                  value={saisie}
                  onChange={(event) => setSaisie(event.target.value)}
                  placeholder="www.monsalon.com"
                  autoComplete="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  inputMode="url"
                  maxLength={253}
                  disabled={ouvert === false}
                />
              </Field>
              <Button
                type="submit"
                pending={envoi}
                disabled={ouvert === false || !saisie.trim()}
                className="sm:mt-7"
              >
                Ajouter
              </Button>
            </form>
          </Card>

          {domaines.error && <ErrorState>{domaines.error}</ErrorState>}
          {domaines.data === null && !domaines.error && <Skeleton rows={2} />}
          {domaines.data !== null && liste.length === 0 && (
            <p className="rounded-2xl border border-dashed border-line-strong px-4 py-6 text-center text-[13px] text-muted sm:text-sm">
              Aucun domaine pour l&apos;instant. Votre mini-site reste joignable à son
              adresse Beauty Salon.
            </p>
          )}

          {liste.map((domaine) => (
            <CarteDomaine
              key={domaine.id}
              domaine={domaine}
              tenantId={tenantId}
              ouvert={ouvert !== false}
              onChange={domaines.reload}
            />
          ))}
        </div>

        <Aide />
      </div>
    </section>
  );
}

function CarteDomaine({
  domaine,
  tenantId,
  ouvert,
  onChange,
}: {
  domaine: Domaine;
  tenantId: string;
  ouvert: boolean;
  onChange: () => void;
}) {
  const toast = useToast();
  const [verification, setVerification] = useState(false);
  const [retrait, setRetrait] = useState(false);
  const [confirmer, setConfirmer] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function verifier() {
    setVerification(true);
    setMessage(null);
    try {
      await dashboardFetch(
        `/api/v1/domaines/${domaine.id}/verifier`,
        { method: "POST" },
        tenantId,
      );
      toast.success(`${domaine.hostname} est relié à votre mini-site.`);
      onChange();
    } catch (caught) {
      setMessage(caught instanceof DashboardError ? caught.message : "Vérification impossible.");
      onChange();
    } finally {
      setVerification(false);
    }
  }

  async function retirer() {
    setRetrait(true);
    try {
      await dashboardFetch(`/api/v1/domaines/${domaine.id}`, { method: "DELETE" }, tenantId);
      toast.success("Domaine retiré.");
      onChange();
    } catch (caught) {
      toast.error(caught instanceof DashboardError ? caught.message : "Retrait impossible.");
      setRetrait(false);
    }
  }

  const statut = domaine.en_pause ? (
    <Badge tone="warning">En pause</Badge>
  ) : domaine.relie ? (
    <Badge tone="success">Relié</Badge>
  ) : (
    <Badge tone="info">En attente du DNS</Badge>
  );
  const erreur = message ?? (domaine.relie ? "" : domaine.derniere_erreur);

  return (
    <Card padded={false} className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 p-4 sm:p-5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-[15px] font-semibold text-ink sm:text-lg">
              {domaine.hostname}
            </p>
            {statut}
          </div>
          <p className="mt-0.5 text-[11.5px] text-muted sm:text-xs">
            {domaine.relie
              ? domaine.en_pause
                ? "Relié, mais servi seulement avec l'offre Pro : les visites arrivent sur votre adresse Beauty Salon."
                : `Vos clientes y trouvent votre mini-site, en HTTPS.`
              : domaine.verifie_le
                ? `Dernière vérification le ${dateLongue.format(new Date(domaine.verifie_le))}.`
                : "Créez les deux enregistrements ci-dessous, puis vérifiez."}
          </p>
        </div>
        {domaine.relie && !domaine.en_pause && (
          <a
            href={`https://${domaine.hostname}`}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 text-sm font-medium text-salon hover:underline"
          >
            Ouvrir <Icon name="external" className="size-3.5" />
          </a>
        )}
      </div>

      {!domaine.relie && (
        <div className="border-t border-line bg-surface-muted/50 p-4 sm:p-5">
          <p className="mb-2.5 text-[12px] font-semibold uppercase tracking-wide text-subtle">
            Chez votre registraire
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <LigneDns
              etape={1}
              titre="Prouver que le domaine est à vous"
              enregistrement={domaine.consignes.txt}
            />
            <LigneDns
              etape={2}
              titre="Amener le domaine ici"
              enregistrement={domaine.consignes.routage}
            />
          </div>
          {erreur && (
            <p className="mt-3 rounded-xl bg-warning-bg px-3 py-2 text-[12px] leading-relaxed text-warning sm:text-xs">
              {erreur}
            </p>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line p-3 sm:px-5">
        {confirmer ? (
          <>
            <span className="mr-auto text-[12px] text-muted sm:text-sm">
              Retirer {domaine.hostname} ?
            </span>
            <GhostButton type="button" onClick={() => setConfirmer(false)}>
              Annuler
            </GhostButton>
            <DangerButton type="button" pending={retrait} onClick={retirer}>
              Retirer
            </DangerButton>
          </>
        ) : (
          <>
            <GhostButton type="button" onClick={() => setConfirmer(true)}>
              Retirer
            </GhostButton>
            {!domaine.relie && (
              <Button
                type="button"
                pending={verification}
                disabled={!ouvert}
                onClick={verifier}
                icon={<Icon name="check" className="size-4" />}
              >
                Vérifier
              </Button>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

function LigneDns({
  etape,
  titre,
  enregistrement,
}: {
  etape: number;
  titre: string;
  enregistrement: Enregistrement;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface p-3">
      <p className="flex items-center gap-1.5 text-[12.5px] font-medium text-ink sm:text-sm">
        <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-salon text-[11px] font-semibold text-white">
          {etape}
        </span>
        {titre}
      </p>
      <dl className="mt-2 space-y-1.5">
        <Valeur terme="Type" valeur={enregistrement.type} />
        <Valeur terme="Nom" valeur={enregistrement.nom} copiable />
        <Valeur
          terme="Valeur"
          valeur={enregistrement.valeur || "Adresse du serveur : demandez-la à l'équipe"}
          copiable={Boolean(enregistrement.valeur)}
        />
      </dl>
    </div>
  );
}

function Valeur({
  terme,
  valeur,
  copiable = false,
}: {
  terme: string;
  valeur: string;
  copiable?: boolean;
}) {
  const toast = useToast();
  return (
    <div className="flex min-w-0 items-center gap-2">
      <dt className="w-12 shrink-0 text-[10.5px] uppercase tracking-wide text-subtle sm:text-[11px]">
        {terme}
      </dt>
      <dd className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-ink sm:text-xs" title={valeur}>
        {valeur}
      </dd>
      {copiable && (
        <button
          type="button"
          aria-label={`Copier ${terme.toLowerCase()}`}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(valeur);
              toast.success(`${terme} copié.`);
            } catch {
              toast.error("Copie impossible : sélectionnez le texte à la main.");
            }
          }}
          className="shrink-0 rounded-md p-1 text-muted transition hover:bg-surface-hover hover:text-ink"
        >
          <Icon name="copy" className="size-3.5" />
        </button>
      )}
    </div>
  );
}

function Aide() {
  const points = [
    "Le domaine doit déjà vous appartenir : Beauty Salon ne l'achète pas pour vous.",
    "Un sous-domaine (www.monsalon.com) se relie par un CNAME ; le domaine nu (monsalon.com) par un enregistrement A.",
    "Le DNS met de quelques minutes à quelques heures à se propager. Vérifiez à nouveau plus tard si besoin.",
    "Le certificat HTTPS est créé automatiquement à la première visite.",
    "Votre adresse Beauty Salon reste active, et reprend le relais si Pro s'arrête.",
  ];
  return (
    <Card padded={false} className="p-4 sm:p-5">
      <p className="text-[13px] font-semibold text-ink sm:text-sm">Bon à savoir</p>
      <ul className="mt-2 space-y-2">
        {points.map((point) => (
          <li key={point} className="flex gap-2 text-[12px] leading-relaxed text-muted sm:text-[13px]">
            <Icon name="check" className="mt-0.5 size-3.5 shrink-0 text-salon" />
            {point}
          </li>
        ))}
      </ul>
    </Card>
  );
}
