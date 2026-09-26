"use client";

/**
 * Les assistants IA (offre Pro), au même endroit :
 *
 *   - l'assistant de l'espace pro, à qui toute l'équipe pose ses questions
 *     (agenda de la semaine, catalogue, « où se règle… ») ; il lit, il ne
 *     modifie rien — et chacun n'y voit que ce que son rôle permet de voir ;
 *   - l'assistant des clientes, sur le mini-site, 24 h/24 ;
 *   - l'assistant WhatsApp, branché sur le numéro du salon.
 *
 * Les interrupteurs sont réservés à la direction, la connexion WhatsApp au
 * propriétaire. Le serveur vérifie les deux, et l'offre Pro, à chaque appel.
 */

import { useEffect, useRef, useState, type FormEvent } from "react";

import { DashboardError, dashboardFetch } from "@/lib/dashboard";
import {
  Badge,
  Button,
  Card,
  DangerButton,
  ErrorState,
  GhostButton,
  PageHeader,
  Skeleton,
  Toggle,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { dateLongue } from "./abonnement";
import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";
import { EnteteCarte, VerrouPro, useFonction } from "./Pro";
import { useResource } from "./useResource";

interface Etat {
  fonctions: { plateforme: boolean; clientes: boolean; whatsapp: boolean };
  ia_configuree: boolean;
  clientes_actif: boolean;
  whatsapp: {
    configuree: boolean;
    statut: "aucun" | "en_attente" | "connecte" | "deconnecte";
    numero: string;
    actif: boolean;
    derniere_activite: string | null;
  };
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTIONS = [
  "Qu'est-ce qui m'attend demain ?",
  "Combien de rendez-vous cette semaine ?",
  "Où modifier mes horaires ?",
];

export function Assistants() {
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const direction = membership.role === "owner" || membership.role === "manager";
  const ouvert = useFonction("platform_assistant");

  const etat = useResource<Etat>("/api/v1/assistant/reglages", tenantId, { enabled: direction });

  return (
    <section>
      <PageHeader
        title="Assistants IA"
        description="Un assistant pour votre équipe, un pour vos clientes sur le mini-site, un sur WhatsApp. Ils renseignent ; ils ne réservent ni ne modifient rien."
      />

      {ouvert === false && <VerrouPro fonction="platform_assistant" />}
      {direction && etat.data && !etat.data.ia_configuree && (
        <p className="mb-4 flex items-start gap-2 rounded-2xl border border-warning/30 bg-warning-bg p-3 text-[12.5px] leading-relaxed text-warning sm:text-sm">
          <Icon name="bolt" className="mt-0.5 size-4 shrink-0" />
          Le service d&apos;IA n&apos;est pas encore branché sur la plateforme : les
          assistants répondent par les coordonnées du salon en attendant.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_22rem] lg:items-start">
        <Conversation tenantId={tenantId} actif={ouvert !== false} />

        {direction && (
          <div className="space-y-4">
            {etat.error && <ErrorState>{etat.error}</ErrorState>}
            {!etat.data && !etat.error && <Skeleton rows={3} />}
            {etat.data && (
              <>
                <Clientes etat={etat.data} tenantId={tenantId} onChange={etat.reload} />
                <WhatsApp
                  etat={etat.data}
                  tenantId={tenantId}
                  proprietaire={membership.role === "owner"}
                  onChange={etat.reload}
                />
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// L'assistant de l'espace pro
// ---------------------------------------------------------------------------

function Conversation({ tenantId, actif }: { tenantId: string; actif: boolean }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [saisie, setSaisie] = useState("");
  const [attente, setAttente] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const fil = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fil.current?.scrollTo({ top: fil.current.scrollHeight, behavior: "smooth" });
  }, [messages, attente]);

  async function envoyer(texte: string) {
    const question = texte.trim().slice(0, 1000);
    if (!question || attente || !actif) return;
    const suite = [...messages, { role: "user" as const, content: question }].slice(-12);
    const envoi = suite.slice(suite.findIndex((message) => message.role === "user"));
    setMessages(suite);
    setSaisie("");
    setErreur(null);
    setAttente(true);
    try {
      const reponse = await dashboardFetch<{ reponse: string }>(
        "/api/v1/assistant",
        { method: "POST", body: JSON.stringify({ messages: envoi }) },
        tenantId,
      );
      setMessages((avant) => [...avant, { role: "assistant", content: reponse.reponse }]);
    } catch (caught) {
      setErreur(caught instanceof DashboardError ? caught.message : "L'assistant ne répond pas.");
    } finally {
      setAttente(false);
    }
  }

  function soumettre(event: FormEvent) {
    event.preventDefault();
    void envoyer(saisie);
  }

  return (
    <Card padded={false} className="flex h-[min(34rem,calc(100svh-14rem))] min-h-[24rem] flex-col overflow-hidden">
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <span className="salon-gradient flex size-9 shrink-0 items-center justify-center rounded-full text-white">
          <Icon name="chat" className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">Assistant de l&apos;espace pro</p>
          <p className="truncate text-[11.5px] text-muted">
            Il lit votre agenda des 7 prochains jours et votre catalogue.
          </p>
        </div>
        {messages.length > 0 && (
          <GhostButton type="button" onClick={() => setMessages([])} className="!px-2.5 !py-1.5 text-xs">
            Effacer
          </GhostButton>
        )}
      </div>

      <div ref={fil} className="flex-1 space-y-2.5 overflow-y-auto p-3 sm:p-4" aria-live="polite">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-salon-soft text-salon">
              <Icon name="sparkles" className="size-6" />
            </span>
            <p className="mt-3 text-sm font-medium text-ink">Que voulez-vous savoir ?</p>
            <div className="mt-3 grid w-full max-w-sm gap-1.5">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  disabled={!actif}
                  onClick={() => void envoyer(suggestion)}
                  className="rounded-xl border border-line px-3 py-2 text-left text-[13px] text-ink transition hover:border-salon hover:bg-salon-soft/50 disabled:opacity-50"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message, index) => (
          <div key={index} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
            <p
              className={`max-w-[85%] whitespace-pre-line rounded-2xl px-3 py-2 text-[13px] leading-relaxed sm:text-sm ${
                message.role === "user"
                  ? "rounded-br-md bg-salon text-white"
                  : "rounded-bl-md bg-surface-muted text-ink"
              }`}
            >
              {message.content}
            </p>
          </div>
        ))}
        {attente && (
          <p className="flex items-center gap-2 text-xs text-muted">
            <span className="flex gap-1" aria-hidden>
              {[0, 150, 300].map((delai) => (
                <span
                  key={delai}
                  className="size-1.5 animate-bounce rounded-full bg-salon"
                  style={{ animationDelay: `${delai}ms` }}
                />
              ))}
            </span>
            L&apos;assistant écrit…
          </p>
        )}
        {erreur && <ErrorState>{erreur}</ErrorState>}
      </div>

      <form onSubmit={soumettre} className="flex items-end gap-2 border-t border-line p-2.5 sm:p-3">
        <textarea
          value={saisie}
          onChange={(event) => setSaisie(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void envoyer(saisie);
            }
          }}
          disabled={!actif}
          rows={1}
          maxLength={1000}
          placeholder={actif ? "Votre question…" : "Réservé à l'offre Pro"}
          aria-label="Votre question"
          className="max-h-28 min-h-10 flex-1 resize-none rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink outline-none placeholder:text-subtle focus:border-salon disabled:opacity-60"
        />
        <Button
          type="submit"
          disabled={!actif || !saisie.trim() || attente}
          aria-label="Envoyer"
          className="!size-10 !p-0"
          icon={<Icon name="send" className="size-4" />}
        />
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// L'assistant des clientes
// ---------------------------------------------------------------------------

function Clientes({
  etat,
  tenantId,
  onChange,
}: {
  etat: Etat;
  tenantId: string;
  onChange: () => void;
}) {
  const toast = useToast();
  const [envoi, setEnvoi] = useState(false);
  const ouvert = etat.fonctions.clientes;

  async function basculer(valeur: boolean) {
    setEnvoi(true);
    try {
      await dashboardFetch(
        "/api/v1/assistant/reglages",
        { method: "PATCH", body: JSON.stringify({ clientes_actif: valeur }) },
        tenantId,
      );
      toast.success(valeur ? "Assistant activé sur votre mini-site." : "Assistant retiré du mini-site.");
      onChange();
    } catch (caught) {
      toast.error(caught instanceof DashboardError ? caught.message : "Changement impossible.");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Card padded={false} className="p-4">
      <EnteteCarte
        icone="globe"
        titre="Sur le mini-site"
        detail="Répond jour et nuit aux questions des clientes. En cas de panne, il donne vos coordonnées."
        statut={
          ouvert && etat.clientes_actif ? (
            <Badge tone="success">En ligne</Badge>
          ) : (
            <Badge tone="neutral">Hors ligne</Badge>
          )
        }
      />
      <div className={`mt-3 ${!ouvert || envoi ? "pointer-events-none opacity-50" : ""}`}>
        <Toggle
          checked={ouvert && etat.clientes_actif}
          onChange={basculer}
          label="Afficher l'assistant"
          hint={ouvert ? "Une bulle en bas à gauche du mini-site." : "Offre Pro."}
        />
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// WhatsApp
// ---------------------------------------------------------------------------

const STATUTS: Record<Etat["whatsapp"]["statut"], { texte: string; ton: "success" | "warning" | "neutral" | "danger" }> = {
  aucun: { texte: "Non relié", ton: "neutral" },
  en_attente: { texte: "En attente du scan", ton: "warning" },
  connecte: { texte: "Relié", ton: "success" },
  deconnecte: { texte: "Déconnecté", ton: "danger" },
};

function WhatsApp({
  etat,
  tenantId,
  proprietaire,
  onChange,
}: {
  etat: Etat;
  tenantId: string;
  proprietaire: boolean;
  onChange: () => void;
}) {
  const toast = useToast();
  const ouvert = useFonction("whatsapp_assistant") ?? etat.fonctions.whatsapp;
  const [qr, setQr] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const { whatsapp } = etat;
  const statut = STATUTS[whatsapp.statut] ?? STATUTS.aucun;

  // Tant qu'on attend le scan, on relit l'état : le QR se renouvelle, et
  // la connexion apparaît d'elle-même.
  const attendScan = whatsapp.statut === "en_attente" && proprietaire && ouvert;
  useEffect(() => {
    if (!attendScan) return;
    let annule = false;
    const lire = () =>
      dashboardFetch<{ qr: string } & Etat>("/api/v1/assistant/whatsapp", {}, tenantId)
        .then((reponse) => {
          if (annule) return;
          setQr(reponse.qr);
          if (reponse.whatsapp.statut !== "en_attente") onChange();
        })
        .catch(() => undefined);
    lire();
    const minuterie = window.setInterval(lire, 5000);
    return () => {
      annule = true;
      window.clearInterval(minuterie);
    };
  }, [attendScan, tenantId, onChange]);

  async function appeler(methode: "POST" | "DELETE", succes: string) {
    setEnvoi(true);
    setErreur(null);
    try {
      const reponse = await dashboardFetch<{ qr?: string }>(
        "/api/v1/assistant/whatsapp",
        { method: methode },
        tenantId,
      );
      setQr(reponse?.qr ?? "");
      toast.success(succes);
      onChange();
    } catch (caught) {
      setErreur(caught instanceof DashboardError ? caught.message : "Opération impossible.");
    } finally {
      setEnvoi(false);
    }
  }

  async function basculer(valeur: boolean) {
    try {
      await dashboardFetch(
        "/api/v1/assistant/reglages",
        { method: "PATCH", body: JSON.stringify({ whatsapp_actif: valeur }) },
        tenantId,
      );
      toast.success(valeur ? "L'assistant répond sur WhatsApp." : "L'assistant ne répond plus sur WhatsApp.");
      onChange();
    } catch (caught) {
      toast.error(caught instanceof DashboardError ? caught.message : "Changement impossible.");
    }
  }

  return (
    <Card padded={false} className="p-4">
      <EnteteCarte
        icone="phone"
        titre="Sur WhatsApp"
        detail="Répond aux messages reçus sur le numéro du salon, 20 réponses par heure et par contact au plus."
        statut={<Badge tone={statut.ton}>{statut.texte}</Badge>}
      />

      {!whatsapp.configuree ? (
        <p className="mt-3 rounded-xl bg-surface-muted px-3 py-2 text-[12px] leading-relaxed text-muted">
          La passerelle WhatsApp n&apos;est pas encore configurée sur la plateforme.
          L&apos;équipe Beauty Salon vous prévient dès qu&apos;elle l&apos;est.
        </p>
      ) : !proprietaire ? (
        <p className="mt-3 text-[12px] text-muted">
          Le propriétaire du salon relie le numéro WhatsApp.
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          {whatsapp.statut === "en_attente" && (
            <div className="grid grid-cols-[8.5rem_1fr] items-start gap-3">
              {qr ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={qr}
                  alt="QR code à scanner avec WhatsApp"
                  className="aspect-square w-full rounded-xl border border-line bg-white p-1.5"
                />
              ) : (
                <div className="flex aspect-square w-full items-center justify-center rounded-xl border border-dashed border-line-strong">
                  <Skeleton rows={1} />
                </div>
              )}
              <ol className="list-decimal space-y-1 pl-4 text-[12px] leading-relaxed text-muted">
                <li>Ouvrez WhatsApp sur le téléphone du salon.</li>
                <li>Réglages → Appareils connectés → Connecter un appareil.</li>
                <li>Scannez ce code. Il se renouvelle tout seul.</li>
              </ol>
            </div>
          )}

          {whatsapp.statut === "connecte" && (
            <>
              <p className="text-[12px] text-muted">
                {whatsapp.numero ? `Numéro ${whatsapp.numero}. ` : ""}
                {whatsapp.derniere_activite
                  ? `Dernière activité le ${dateLongue.format(new Date(whatsapp.derniere_activite))}.`
                  : "Aucun message traité pour l'instant."}
              </p>
              <Toggle
                checked={whatsapp.actif}
                onChange={basculer}
                label="Répondre automatiquement"
                hint="Coupez-le à tout moment pour répondre vous-même."
              />
            </>
          )}

          {erreur && <ErrorState>{erreur}</ErrorState>}

          <div className="flex flex-wrap gap-2">
            {(whatsapp.statut === "aucun" || whatsapp.statut === "deconnecte") && (
              <Button
                type="button"
                pending={envoi}
                disabled={!ouvert}
                onClick={() => appeler("POST", "Scannez le QR code avec le téléphone du salon.")}
                className="w-full"
              >
                Relier mon WhatsApp
              </Button>
            )}
            {whatsapp.statut !== "aucun" && (
              <DangerButton
                type="button"
                pending={envoi}
                onClick={() => appeler("DELETE", "WhatsApp déconnecté.")}
                className="w-full"
              >
                Déconnecter
              </DangerButton>
            )}
          </div>
          <p className="text-[10.5px] leading-snug text-subtle">
            La liaison passe par WhatsApp Web, comme un ordinateur connecté : ce
            n&apos;est pas l&apos;API officielle de Meta, et un usage jugé abusif peut
            faire limiter le numéro.
          </p>
        </div>
      )}
    </Card>
  );
}
