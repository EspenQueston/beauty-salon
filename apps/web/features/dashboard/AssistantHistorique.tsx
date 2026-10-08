"use client";

/**
 * Offre Pro : brancher n8n, et relire les conversations de l'assistant.
 *
 * ---------------------------------------------------------------------------
 * n8n
 * ---------------------------------------------------------------------------
 *
 * Un salon qui a déjà son automatisation WhatsApp (n8n, avec son propre
 * numéro) n'a pas à la refaire ici : il nous envoie chaque message sur une
 * adresse de webhook, et l'historique s'affiche avec celui de l'assistant
 * relié par la plateforme. L'adresse porte un jeton secret, montré **une
 * seule fois** — le serveur n'en garde que l'empreinte. Perdue, elle se
 * régénère ; l'ancienne cesse alors de fonctionner.
 *
 * ---------------------------------------------------------------------------
 * L'historique
 * ---------------------------------------------------------------------------
 *
 * Une messagerie en lecture seule : les fils à gauche, le fil ouvert à
 * droite ; sur téléphone, l'un puis l'autre. Il se relit tout seul pendant
 * que la page est visible — une conversation en cours s'y suit sans
 * recharger.
 */

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { DashboardError, dashboardFetch } from "@/lib/dashboard";
import {
  Badge,
  Button,
  Card,
  DangerButton,
  ErrorState,
  GhostButton,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { TexteRiche } from "@/features/ui/TexteRiche";
import { useToast } from "@/features/ui/Toast";

import { dateLongue } from "./abonnement";
import { Icon } from "./icons";
import { EnteteCarte, useFonction } from "./Pro";
import { useResource } from "./useResource";

interface EtatN8n {
  numero: string;
  relie: boolean;
  derniere_reception: string | null;
  messages: number;
  adresse?: string;
}

interface Fil {
  id: string;
  canal: "whatsapp" | "n8n";
  contact: string;
  nom: string;
  dernier_message_le: string;
  dernier_apercu: string;
  nombre_messages: number;
}

interface FilOuvert {
  id: string;
  canal: Fil["canal"];
  contact: string;
  nom: string;
  messages: {
    id: string;
    direction: "entrant" | "sortant";
    texte: string;
    envoye_le: string;
  }[];
}

const EXEMPLE = `{
  "contact": "+242061234567",
  "nom": "Awa",
  "direction": "entrant",
  "message": "Bonjour, vous êtes ouverts demain ?",
  "horodatage": "2026-10-03T09:14:00Z",
  "id": "wamid.HBgM…"
}`;

// ---------------------------------------------------------------------------
// La carte n8n
// ---------------------------------------------------------------------------

export function CarteN8n({
  tenantId,
  proprietaire,
}: {
  tenantId: string;
  proprietaire: boolean;
}) {
  const toast = useToast();
  const ouvert = useFonction("whatsapp_assistant");
  const etat = useResource<EtatN8n>("/api/v1/assistant/n8n", tenantId, {
    enabled: ouvert !== false,
  });
  const [numero, setNumero] = useState<string | null>(null);
  const [adresse, setAdresse] = useState("");
  const [envoi, setEnvoi] = useState<"numero" | "adresse" | "retrait" | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  const valeurNumero = numero ?? etat.data?.numero ?? "";
  const modifie = numero !== null && numero !== (etat.data?.numero ?? "");

  async function enregistrerNumero(evenement: FormEvent) {
    evenement.preventDefault();
    setEnvoi("numero");
    setErreur(null);
    try {
      await dashboardFetch(
        "/api/v1/assistant/n8n",
        { method: "PATCH", body: JSON.stringify({ numero: valeurNumero }) },
        tenantId,
      );
      setNumero(null);
      toast.success("Numéro enregistré.");
      etat.reload();
    } catch (caught) {
      setErreur(caught instanceof DashboardError ? caught.message : "Numéro refusé.");
    } finally {
      setEnvoi(null);
    }
  }

  async function genererAdresse() {
    if (
      etat.data?.relie &&
      !window.confirm(
        "Régénérer l'adresse ? L'ancienne cessera de fonctionner : pensez à mettre à jour n8n.",
      )
    ) {
      return;
    }
    setEnvoi("adresse");
    setErreur(null);
    try {
      const reponse = await dashboardFetch<EtatN8n>(
        "/api/v1/assistant/n8n",
        { method: "POST" },
        tenantId,
      );
      setAdresse(reponse.adresse ?? "");
      etat.reload();
    } catch (caught) {
      setErreur(caught instanceof DashboardError ? caught.message : "Opération impossible.");
    } finally {
      setEnvoi(null);
    }
  }

  async function retirer() {
    if (!window.confirm("Débrancher n8n ? Les messages déjà reçus restent dans l'historique.")) {
      return;
    }
    setEnvoi("retrait");
    try {
      await dashboardFetch("/api/v1/assistant/n8n", { method: "DELETE" }, tenantId);
      setAdresse("");
      toast.success("n8n débranché.");
      etat.reload();
    } catch (caught) {
      toast.error(caught instanceof DashboardError ? caught.message : "Opération impossible.");
    } finally {
      setEnvoi(null);
    }
  }

  async function copier(texte: string, quoi: string) {
    try {
      await navigator.clipboard.writeText(texte);
      toast.success(`${quoi} copié.`);
    } catch {
      toast.error("Copie impossible : sélectionnez le texte à la main.");
    }
  }

  const relie = etat.data?.relie ?? false;

  return (
    <Card padded={false} className="p-4">
      <EnteteCarte
        icone="bolt"
        titre="Avec n8n"
        detail="Votre automatisation WhatsApp sur n8n envoie chaque message ici : vous suivez les échanges dans l'historique, plus bas."
        statut={
          relie ? <Badge tone="success">Relié</Badge> : <Badge tone="neutral">Non relié</Badge>
        }
      />

      {ouvert === false ? (
        <p className="mt-3 rounded-xl bg-surface-muted px-3 py-2 text-[12px] leading-relaxed text-muted">
          Fonction de l&apos;offre Pro.
        </p>
      ) : !etat.data ? (
        etat.error ? (
          <div className="mt-3">
            <ErrorState>{etat.error}</ErrorState>
          </div>
        ) : (
          <div className="mt-3">
            <Skeleton rows={2} />
          </div>
        )
      ) : (
        <div className="mt-3 space-y-3">
          <form onSubmit={enregistrerNumero} className="space-y-1.5">
            <label htmlFor="n8n-numero" className="block text-[12.5px] font-medium text-ink">
              Numéro WhatsApp de l&apos;assistant
            </label>
            <div className="flex gap-2">
              <input
                id="n8n-numero"
                type="tel"
                inputMode="tel"
                autoComplete="off"
                placeholder="+242 06 123 45 67"
                value={valeurNumero}
                onChange={(evenement) => setNumero(evenement.target.value)}
                className={`${inputClass} min-w-0 flex-1 py-2`}
              />
              <GhostButton
                type="submit"
                pending={envoi === "numero"}
                disabled={!modifie}
                className="shrink-0"
              >
                Enregistrer
              </GhostButton>
            </div>
            <p className="text-[11px] leading-snug text-subtle">
              Celui que vos clientes écrivent. Il s&apos;affiche dans l&apos;historique.
            </p>
          </form>

          {adresse && (
            <div className="rounded-xl border border-success/30 bg-success-bg p-3">
              <p className="text-[12px] font-semibold text-success">
                Copiez cette adresse maintenant : elle ne sera plus affichée.
              </p>
              <div className="mt-2 flex items-start gap-2">
                <code className="min-w-0 flex-1 break-all rounded-lg bg-surface px-2 py-1.5 font-mono text-[11px] leading-snug text-ink">
                  {adresse}
                </code>
                <button
                  type="button"
                  aria-label="Copier l'adresse du webhook"
                  onClick={() => void copier(adresse, "Adresse")}
                  className="shrink-0 rounded-lg border border-line bg-surface p-2 text-muted transition hover:text-ink"
                >
                  <Icon name="copy" className="size-4" />
                </button>
              </div>
            </div>
          )}

          {relie && (
            <p className="text-[12px] text-muted">
              {etat.data.derniere_reception
                ? `Dernier message reçu le ${dateLongue.format(new Date(etat.data.derniere_reception))} · ${etat.data.messages} au total.`
                : "Adresse prête : en attente du premier message de n8n."}
            </p>
          )}

          {erreur && <ErrorState>{erreur}</ErrorState>}

          {proprietaire ? (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              <Button
                type="button"
                pending={envoi === "adresse"}
                onClick={() => void genererAdresse()}
                icon={<Icon name="bolt" className="size-4" />}
                className={relie ? "" : "sm:col-span-2 lg:col-span-1 xl:col-span-2"}
              >
                {relie ? "Régénérer l'adresse" : "Créer l'adresse du webhook"}
              </Button>
              {relie && (
                <DangerButton
                  type="button"
                  pending={envoi === "retrait"}
                  onClick={() => void retirer()}
                >
                  Débrancher
                </DangerButton>
              )}
            </div>
          ) : (
            <p className="text-[12px] text-muted">
              Le propriétaire du salon crée l&apos;adresse du webhook.
            </p>
          )}

          <details className="group rounded-xl border border-line">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-[12.5px] font-medium text-ink">
              Dans n8n : nœud « HTTP Request »
              <Icon
                name="chevron-right"
                className="size-4 text-muted transition group-open:rotate-90"
              />
            </summary>
            <div className="space-y-2 border-t border-line px-3 py-3 text-[11.5px] leading-relaxed text-muted">
              <p>
                Méthode <strong className="text-ink">POST</strong>, corps{" "}
                <strong className="text-ink">JSON</strong>, vers l&apos;adresse ci-dessus.
                Un message par appel — ou <code>{`{"messages": [...]}`}</code>, 50 au plus.
              </p>
              <div className="relative">
                <pre className="overflow-x-auto rounded-lg bg-surface-muted p-2.5 font-mono text-[10.5px] leading-snug text-ink">
                  {EXEMPLE}
                </pre>
                <button
                  type="button"
                  aria-label="Copier l'exemple"
                  onClick={() => void copier(EXEMPLE, "Exemple")}
                  className="absolute right-1.5 top-1.5 rounded-md bg-surface p-1 text-muted transition hover:text-ink"
                >
                  <Icon name="copy" className="size-3.5" />
                </button>
              </div>
              <p>
                <code>direction</code> : <code>entrant</code> (la cliente) ou{" "}
                <code>sortant</code> (l&apos;assistant). <code>id</code> évite les
                doublons si n8n renvoie un message.
              </p>
            </div>
          </details>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// L'historique
// ---------------------------------------------------------------------------

const CANAUX = [
  { valeur: "", libelle: "Tous" },
  { valeur: "whatsapp", libelle: "WhatsApp" },
  { valeur: "n8n", libelle: "n8n" },
] as const;

const heure = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });
const jourCourt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
const jourLong = new Intl.DateTimeFormat("fr-FR", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

function quand(iso: string): string {
  const date = new Date(iso);
  const aujourdhui = new Date();
  return date.toDateString() === aujourdhui.toDateString()
    ? heure.format(date)
    : jourCourt.format(date);
}

/** Relit `charger` à intervalles, seulement quand l'onglet est visible. */
function useRelecture(charger: () => void, intervalle: number, actif: boolean) {
  const dernier = useRef(charger);
  useEffect(() => {
    dernier.current = charger;
  });
  useEffect(() => {
    if (!actif) return;
    const minuterie = window.setInterval(() => {
      if (document.visibilityState === "visible") dernier.current();
    }, intervalle);
    return () => window.clearInterval(minuterie);
  }, [intervalle, actif]);
}

export function HistoriqueConversations({ tenantId }: { tenantId: string }) {
  const ouvert = useFonction("whatsapp_assistant");
  const [canal, setCanal] = useState<"" | "whatsapp" | "n8n">("");
  const [saisie, setSaisie] = useState("");
  const [recherche, setRecherche] = useState("");
  const [choisi, setChoisi] = useState<string | null>(null);

  // La recherche part 300 ms après la dernière frappe, pas à chaque lettre.
  useEffect(() => {
    const minuterie = window.setTimeout(() => setRecherche(saisie.trim()), 300);
    return () => window.clearTimeout(minuterie);
  }, [saisie]);

  const parametres = new URLSearchParams();
  if (canal) parametres.set("canal", canal);
  if (recherche) parametres.set("q", recherche);
  const chemin = `/api/v1/assistant/conversations${parametres.size ? `?${parametres}` : ""}`;

  const liste = useResource<{ conversations: Fil[] }>(chemin, tenantId, {
    enabled: ouvert !== false,
  });
  useRelecture(liste.reload, 15_000, ouvert !== false);

  const fils = liste.data?.conversations ?? [];

  return (
    <section className="mt-6" aria-labelledby="historique-titre">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="historique-titre" className="text-base font-semibold text-ink sm:text-lg">
            Historique des conversations
          </h2>
          <p className="text-[12.5px] text-muted sm:text-sm">
            Les échanges entre l&apos;assistant et vos clientes, sur WhatsApp et via n8n.
          </p>
        </div>
        {ouvert !== false && (
          <div
            role="radiogroup"
            aria-label="Canal"
            className="inline-flex rounded-xl border border-line bg-surface p-0.5"
          >
            {CANAUX.map((option) => (
              <button
                key={option.valeur}
                type="button"
                role="radio"
                aria-checked={canal === option.valeur}
                onClick={() => {
                  setCanal(option.valeur);
                  setChoisi(null);
                }}
                className="rounded-lg px-3 py-1.5 text-[12px] font-medium text-muted transition aria-checked:bg-salon aria-checked:text-white"
              >
                {option.libelle}
              </button>
            ))}
          </div>
        )}
      </div>

      {ouvert === false ? (
        <Card className="text-sm text-muted">
          L&apos;historique des conversations fait partie de l&apos;offre Pro.
        </Card>
      ) : (
        <Card
          padded={false}
          className="grid h-[min(38rem,calc(100svh-9rem))] min-h-[26rem] overflow-hidden md:grid-cols-[17rem_minmax(0,1fr)] lg:grid-cols-[19rem_minmax(0,1fr)]"
        >
          {/* Les fils. Sur téléphone, cachés quand un fil est ouvert. */}
          <div
            className={`min-h-0 flex-col border-line md:flex md:border-r ${
              choisi ? "hidden" : "flex"
            }`}
          >
            <div className="border-b border-line p-2.5">
              <label className="relative block">
                <span className="sr-only">Rechercher un contact</span>
                <Icon
                  name="search"
                  className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-subtle"
                />
                <input
                  type="search"
                  value={saisie}
                  onChange={(evenement) => setSaisie(evenement.target.value)}
                  placeholder="Nom ou numéro"
                  className={`${inputClass} py-2 pl-8`}
                />
              </label>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {liste.error && !liste.data ? (
                <div className="p-3">
                  <ErrorState>{liste.error}</ErrorState>
                </div>
              ) : !liste.data ? (
                <div className="p-3">
                  <Skeleton rows={4} />
                </div>
              ) : fils.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
                  <span className="flex size-10 items-center justify-center rounded-2xl bg-salon-soft text-salon">
                    <Icon name="chat" className="size-5" />
                  </span>
                  <p className="text-[12.5px] leading-relaxed text-muted">
                    {recherche || canal
                      ? "Aucune conversation ne correspond."
                      : "Aucune conversation pour l'instant. Elles apparaissent dès que l'assistant répond sur WhatsApp ou que n8n envoie un message."}
                  </p>
                </div>
              ) : (
                <ul>
                  {fils.map((fil) => (
                    <li key={fil.id}>
                      <button
                        type="button"
                        onClick={() => setChoisi(fil.id)}
                        aria-current={choisi === fil.id ? "true" : undefined}
                        className="flex w-full items-start gap-2.5 border-b border-line/60 px-3 py-2.5 text-left transition hover:bg-surface-hover aria-[current]:bg-salon-soft"
                      >
                        <Avatar fil={fil} />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-baseline justify-between gap-2">
                            <span className="truncate text-[13px] font-semibold text-ink">
                              {fil.nom || fil.contact}
                            </span>
                            <span className="tabular shrink-0 text-[10.5px] text-subtle">
                              {quand(fil.dernier_message_le)}
                            </span>
                          </span>
                          <span className="mt-0.5 flex items-center gap-1.5">
                            <span className="line-clamp-1 min-w-0 flex-1 text-[12px] text-muted">
                              {fil.dernier_apercu}
                            </span>
                            <span className="shrink-0 rounded-full bg-surface-muted px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide text-subtle">
                              {fil.canal === "n8n" ? "n8n" : "WA"}
                            </span>
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Le fil ouvert. */}
          <div className={`min-h-0 flex-col md:flex ${choisi ? "flex" : "hidden"}`}>
            {choisi ? (
              <FilDeDiscussion
                key={choisi}
                id={choisi}
                tenantId={tenantId}
                onRetour={() => setChoisi(null)}
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
                <Icon name="chat" className="size-6 text-subtle" />
                <p className="text-[13px] text-muted">Choisissez une conversation.</p>
              </div>
            )}
          </div>
        </Card>
      )}
    </section>
  );
}

function Avatar({ fil }: { fil: Pick<Fil, "nom" | "contact" | "canal"> }) {
  const lettre = (fil.nom || "").trim()[0]?.toUpperCase();
  return (
    <span
      aria-hidden
      className="flex size-9 shrink-0 items-center justify-center rounded-full bg-salon-soft text-[13px] font-semibold text-salon"
    >
      {lettre || <Icon name="phone" className="size-4" />}
    </span>
  );
}

function FilDeDiscussion({
  id,
  tenantId,
  onRetour,
}: {
  id: string;
  tenantId: string;
  onRetour: () => void;
}) {
  const fil = useResource<FilOuvert>(`/api/v1/assistant/conversations/${id}`, tenantId);
  useRelecture(fil.reload, 10_000, true);
  const bas = useRef<HTMLDivElement>(null);
  const nombre = fil.data?.messages.length ?? 0;

  // En bas à l'ouverture, et à chaque nouveau message : c'est là qu'on lit.
  useEffect(() => {
    if (nombre) bas.current?.scrollIntoView({ block: "end" });
  }, [nombre]);

  // Les messages regroupés par jour, comme dans WhatsApp.
  const jours = useMemo(() => {
    const groupes: { jour: string; messages: FilOuvert["messages"] }[] = [];
    for (const message of fil.data?.messages ?? []) {
      const jour = jourLong.format(new Date(message.envoye_le));
      const dernier = groupes[groupes.length - 1];
      if (dernier && dernier.jour === jour) dernier.messages.push(message);
      else groupes.push({ jour, messages: [message] });
    }
    return groupes;
  }, [fil.data]);

  return (
    <>
      <div className="flex items-center gap-2.5 border-b border-line px-3 py-2.5">
        <button
          type="button"
          onClick={onRetour}
          aria-label="Retour aux conversations"
          className="-ml-1 rounded-lg p-1.5 text-muted transition hover:bg-surface-hover hover:text-ink md:hidden"
        >
          <Icon name="chevron-left" className="size-5" />
        </button>
        {fil.data && <Avatar fil={fil.data} />}
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13.5px] font-semibold text-ink">
            {fil.data ? fil.data.nom || fil.data.contact : "…"}
          </p>
          {fil.data && (
            <p className="truncate text-[11.5px] text-muted">
              {fil.data.nom ? `${fil.data.contact} · ` : ""}
              {fil.data.canal === "n8n" ? "via n8n" : "WhatsApp (plateforme)"}
            </p>
          )}
        </div>
        {fil.data && fil.data.contact.startsWith("+") && (
          <a
            href={`https://wa.me/${fil.data.contact.slice(1)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] font-medium text-ink transition hover:bg-surface-hover"
          >
            <Icon name="external" className="size-3.5" />
            <span className="hidden sm:inline">Répondre</span>
          </a>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-surface-muted/40 px-3 py-3 sm:px-4">
        {fil.error && !fil.data ? (
          <ErrorState>{fil.error}</ErrorState>
        ) : !fil.data ? (
          <Skeleton rows={4} />
        ) : (
          jours.map((groupe) => (
            <div key={groupe.jour}>
              <p className="my-3 text-center first:mt-0">
                <span className="rounded-full bg-surface px-2.5 py-1 text-[10.5px] font-medium capitalize text-subtle shadow-sm">
                  {groupe.jour}
                </span>
              </p>
              <ul className="space-y-1.5">
                {groupe.messages.map((message) => {
                  const sortant = message.direction === "sortant";
                  return (
                    <li
                      key={message.id}
                      className={`flex ${sortant ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[85%] whitespace-pre-line break-words rounded-2xl px-3 py-2 text-[13px] leading-relaxed shadow-sm sm:max-w-[75%] ${
                          sortant
                            ? "rounded-br-md bg-salon text-white"
                            : "rounded-bl-md bg-surface text-ink"
                        }`}
                      >
                        {sortant && (
                          <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-white/75">
                            Assistant
                          </span>
                        )}
                        <TexteRiche
                          texte={message.texte}
                          classeLien={sortant ? "underline text-white" : "underline text-salon"}
                        />
                        <span
                          className={`tabular mt-0.5 block text-right text-[10px] ${
                            sortant ? "text-white/70" : "text-subtle"
                          }`}
                        >
                          {heure.format(new Date(message.envoye_le))}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}
        <div ref={bas} />
      </div>
    </>
  );
}
