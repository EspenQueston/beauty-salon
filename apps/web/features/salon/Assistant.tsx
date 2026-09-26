"use client";

/**
 * L'assistant des clientes, sur le mini-site (offre Pro).
 *
 * Une bulle discrète, en bas à gauche — la droite est à la barre de
 * réservation et au retour en haut. Ouverte, une conversation courte :
 * l'assistant renseigne (prestations, prix, horaires, adresse) et renvoie
 * vers la réservation ; il ne réserve rien lui-même.
 *
 * Toujours joignable, même quand l'IA ne l'est pas : une réponse refusée
 * (panne, plafond du jour) affiche les coordonnées du salon — c'est le
 * « repli » que renvoie le serveur, pas un message d'erreur sans issue.
 *
 * La conversation vit dans l'onglet (sessionStorage) : elle survit à un
 * changement de page du mini-site, pas à la fermeture du navigateur. Rien
 * n'en est gardé côté serveur.
 */

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { browserApi, csrfToken } from "@/lib/api";
import { SalonIcon } from "./icons";
import { whatsappHref } from "./contact";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Repli {
  whatsapp?: string;
  telephone?: string;
  email?: string;
}

const MAX_MESSAGES = 12;
const LONGUEUR_MAX = 1000;

export function Assistant({ host, salon, slug }: { host: string; salon: string; slug: string }) {
  const t = useTranslations("salon.assistant");
  const cle = `beauty-salon.assistant.${slug}`;
  const [ouvert, setOuvert] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [saisie, setSaisie] = useState("");
  const [attente, setAttente] = useState(false);
  const [repli, setRepli] = useState<Repli | null>(null);
  const fil = useRef<HTMLDivElement>(null);
  const champ = useRef<HTMLTextAreaElement>(null);
  // La conversation de l'onglet n'est relue qu'à la première ouverture :
  // l'écrire avant l'aurait effacée.
  const restauree = useRef(false);

  function basculer() {
    if (!ouvert && !restauree.current) {
      restauree.current = true;
      try {
        const lus = JSON.parse(sessionStorage.getItem(cle) ?? "[]") as Message[];
        if (Array.isArray(lus)) setMessages(lus.slice(-MAX_MESSAGES));
      } catch {
        // Stockage indisponible (navigation privée stricte) : on repart de zéro.
      }
    }
    setOuvert((valeur) => !valeur);
  }

  useEffect(() => {
    if (restauree.current) {
      try {
        sessionStorage.setItem(cle, JSON.stringify(messages.slice(-MAX_MESSAGES)));
      } catch {
        // Sans stockage, la conversation dure le temps de la page : c'est assez.
      }
    }
    fil.current?.scrollTo({ top: fil.current.scrollHeight, behavior: "smooth" });
  }, [messages, attente, cle]);

  useEffect(() => {
    if (!ouvert) return;
    champ.current?.focus();
    const echap = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOuvert(false);
    };
    window.addEventListener("keydown", echap);
    return () => window.removeEventListener("keydown", echap);
  }, [ouvert]);

  async function envoyer(texte: string) {
    const question = texte.trim().slice(0, LONGUEUR_MAX);
    if (!question || attente) return;
    const suite = [...messages, { role: "user" as const, content: question }].slice(-MAX_MESSAGES);
    // La conversation envoyée commence par une question : le serveur refuse
    // un fil qui s'ouvre sur une réponse.
    const envoi = suite.slice(suite.findIndex((message) => message.role === "user"));
    setMessages(suite);
    setSaisie("");
    setAttente(true);
    setRepli(null);
    try {
      const reponse = await fetch(`${browserApi()}/api/v1/public/assistant`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-Host": host,
          "X-CSRFToken": await csrfToken(),
        },
        body: JSON.stringify({ messages: envoi }),
      });
      const corps = (await reponse.json().catch(() => null)) as {
        reponse?: string;
        repli?: Repli;
        detail?: string;
      } | null;
      if (reponse.ok && corps?.reponse) {
        setMessages((avant) => [...avant, { role: "assistant", content: corps.reponse ?? "" }]);
      } else {
        setRepli(corps?.repli ?? {});
      }
    } catch {
      setRepli({});
    } finally {
      setAttente(false);
    }
  }

  function soumettre(event: FormEvent) {
    event.preventDefault();
    void envoyer(saisie);
  }

  const suggestions = [t("suggestions.prix"), t("suggestions.horaires"), t("suggestions.reserver")];

  return (
    <>
      <button
        type="button"
        onClick={basculer}
        aria-expanded={ouvert}
        aria-controls="assistant-salon"
        aria-label={ouvert ? t("fermer") : t("ouvrir")}
        className={`salon-gradient fixed bottom-[6.5rem] left-4 z-40 flex size-12 items-center justify-center rounded-full text-white shadow-lg transition hover:scale-105 active:scale-95 sm:bottom-24 sm:left-6 sm:size-14 ${
          ouvert ? "max-sm:hidden" : ""
        }`}
      >
        <SalonIcon name={ouvert ? "close" : "sparkle"} className="size-5 sm:size-6" />
      </button>

      {ouvert && (
        <section
          id="assistant-salon"
          role="dialog"
          aria-label={t("titre")}
          className="fixed inset-x-2 bottom-2 z-50 flex max-h-[78svh] flex-col overflow-hidden rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-2xl sm:inset-x-auto sm:bottom-40 sm:left-6 sm:h-[32rem] sm:max-h-[calc(100svh-12rem)] sm:w-[23rem]"
        >
          <header className="salon-gradient flex items-center gap-3 px-4 py-3 text-white">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-white/20">
              <SalonIcon name="sparkle" className="size-4.5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{t("titre")}</p>
              <p className="truncate text-[11px] opacity-85">{t("sousTitre")}</p>
            </div>
            {messages.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setMessages([]);
                  setRepli(null);
                }}
                className="rounded-lg px-2 py-1 text-[11px] font-medium opacity-90 transition hover:bg-white/15"
              >
                {t("effacer")}
              </button>
            )}
            <button
              type="button"
              onClick={() => setOuvert(false)}
              aria-label={t("fermer")}
              className="flex size-8 items-center justify-center rounded-full transition hover:bg-white/15"
            >
              <SalonIcon name="close" className="size-4" />
            </button>
          </header>

          <div ref={fil} className="flex-1 space-y-2.5 overflow-y-auto px-3 py-3" aria-live="polite">
            <Bulle role="assistant">{t("bienvenue", { salon })}</Bulle>

            {messages.length === 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => void envoyer(suggestion)}
                    className="rounded-full border border-[var(--site-line)] px-3 py-1.5 text-xs text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}

            {messages.map((message, index) => (
              <Bulle key={index} role={message.role}>
                {message.content}
              </Bulle>
            ))}

            {attente && (
              <p className="flex items-center gap-2 px-1 text-xs text-[var(--site-muted)]">
                <span className="flex gap-1" aria-hidden>
                  {[0, 150, 300].map((delai) => (
                    <span
                      key={delai}
                      className="size-1.5 animate-bounce rounded-full bg-[var(--salon-primary)]"
                      style={{ animationDelay: `${delai}ms` }}
                    />
                  ))}
                </span>
                {t("reflechit")}
              </p>
            )}

            {repli && <Coordonnees repli={repli} />}
          </div>

          <form onSubmit={soumettre} className="border-t border-[var(--site-line)] p-2.5">
            <div className="flex items-end gap-2">
              <textarea
                ref={champ}
                value={saisie}
                onChange={(event) => setSaisie(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void envoyer(saisie);
                  }
                }}
                rows={1}
                maxLength={LONGUEUR_MAX}
                placeholder={t("placeholder")}
                aria-label={t("placeholder")}
                className="max-h-28 min-h-10 flex-1 resize-none rounded-xl border border-[var(--site-line)] bg-transparent px-3 py-2 text-sm text-[var(--site-ink)] outline-none placeholder:text-[var(--site-subtle)] focus:border-[var(--salon-primary)]"
              />
              <button
                type="submit"
                disabled={!saisie.trim() || attente}
                aria-label={t("envoyer")}
                className="salon-gradient flex size-10 shrink-0 items-center justify-center rounded-xl text-white transition disabled:opacity-40"
              >
                <SalonIcon name="arrow" className="size-4" />
              </button>
            </div>
            <p className="mt-1.5 px-1 text-[10.5px] leading-snug text-[var(--site-subtle)]">
              {t("automatique")}
            </p>
          </form>
        </section>
      )}
    </>
  );
}

function Bulle({ role, children }: { role: Message["role"]; children: React.ReactNode }) {
  const moi = role === "user";
  return (
    <div className={`flex ${moi ? "justify-end" : "justify-start"}`}>
      <p
        className={`max-w-[85%] whitespace-pre-line rounded-2xl px-3 py-2 text-[13px] leading-relaxed ${
          moi
            ? "salon-gradient rounded-br-md text-white"
            : "rounded-bl-md bg-[color-mix(in_srgb,var(--salon-primary)_8%,var(--site-surface))] text-[var(--site-ink)]"
        }`}
      >
        {children}
      </p>
    </div>
  );
}

function Coordonnees({ repli }: { repli: Repli }) {
  const t = useTranslations("salon.assistant");
  const whatsapp = repli.whatsapp ? whatsappHref(repli.whatsapp) : null;
  const liens = [
    whatsapp && { href: whatsapp, icone: "whatsapp" as const, texte: t("whatsapp") },
    repli.telephone && { href: `tel:${repli.telephone}`, icone: "phone" as const, texte: t("appeler") },
    repli.email && { href: `mailto:${repli.email}`, icone: "mail" as const, texte: t("email") },
  ].filter(Boolean) as { href: string; icone: "whatsapp" | "phone" | "mail"; texte: string }[];

  return (
    <div className="rounded-xl border border-[var(--site-line)] p-3 text-[12.5px] text-[var(--site-muted)]">
      <p>{t("indisponible")}</p>
      {liens.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {liens.map((lien) => (
            <a
              key={lien.href}
              href={lien.href}
              target={lien.icone === "whatsapp" ? "_blank" : undefined}
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1.5 rounded-full border border-[var(--site-line)] px-3 py-1.5 font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)]"
            >
              <SalonIcon name={lien.icone} className="size-3.5" />
              {lien.texte}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
