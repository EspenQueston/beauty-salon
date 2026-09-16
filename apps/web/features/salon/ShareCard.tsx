"use client";

/**
 * Partage du mini-site.
 *
 * Le lien d'un salon circule de main en main : WhatsApp entre clientes,
 * WeChat pour la diaspora en Chine, la bio TikTok ou Instagram pour attirer.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi pas des boutons tous identiques
 * ---------------------------------------------------------------------------
 *
 * Seul WhatsApp expose une adresse de partage utilisable depuis le Web
 * (`wa.me`). WeChat et TikTok n'en ont pas : leurs partages passent par
 * l'application. Fabriquer trois boutons qui se ressemblent alors que deux ne
 * mèneraient nulle part serait une promesse non tenue.
 *
 * On propose donc, dans cet ordre :
 *
 *   1. le partage natif du téléphone quand il existe — il présente à lui seul
 *      WhatsApp, WeChat, TikTok et tout ce qui est installé ;
 *   2. WhatsApp en direct, qui marche partout, y compris sur ordinateur ;
 *   3. la copie du lien, à coller dans une bio ;
 *   4. le QR code, la façon dont WeChat ouvre un lien depuis un écran ou une
 *      affichette posée au salon.
 *
 * Les comptes du salon complètent la rangée quand il en a déclaré : ils
 * mènent au même geste — ouvrir le salon ailleurs — et leurs libellés
 * suffisent à les distinguer sans qu'on ait à les isoler.
 */

import { useState, useSyncExternalStore } from "react";
import { QRCodeSVG } from "qrcode.react";

import { SalonIcon } from "./icons";
import type { ContactLink } from "./contact";

/**
 * Le partage natif existe-t-il dans ce navigateur ?
 *
 * C'est une capacité du navigateur, pas un état de React : elle est lue
 * comme telle. Un `useEffect` qui poserait un `useState` provoquerait un
 * second rendu à chaque montage, et le serveur — qui ne peut pas savoir —
 * répond simplement « non ».
 */
const NEVER_CHANGES = () => () => {};
const readShareSupport = () =>
  typeof navigator !== "undefined" && typeof navigator.share === "function";
const noShareOnServer = () => false;

export function ShareCard({
  host,
  salonName,
  socials = [],
}: {
  host: string;
  salonName: string;
  /** Comptes renseignés par le salon. Vide s'il n'en a déclaré aucun. */
  socials?: ContactLink[];
}) {
  const [copied, setCopied] = useState(false);
  const canShare = useSyncExternalStore(
    NEVER_CHANGES,
    readShareSupport,
    noShareOnServer,
  );

  const url = `https://${host}`;
  const message = `Prenez rendez-vous chez ${salonName} : ${url}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    } catch {
      // Presse-papier refusé (contexte non sécurisé, permission) : le lien
      // reste affiché en clair juste au-dessus, rien n'est perdu.
      setCopied(false);
    }
  }

  async function share() {
    try {
      await navigator.share({ title: salonName, text: message, url });
    } catch {
      // L'utilisatrice a fermé la feuille de partage : ce n'est pas une
      // erreur, il n'y a rien à signaler.
    }
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-[0_1px_3px_rgb(23_23_28_/_0.05)]">
      <div className="grid gap-6 p-5 sm:grid-cols-[auto_1fr] sm:items-start sm:p-6">
        {/*
          Le QR reste sur fond blanc quel que soit le thème : un lecteur de
          code a besoin du contraste maximal, et l'inverser en mode sombre
          rend le code illisible pour la moitié des téléphones.
        */}
        <div className="mx-auto w-fit rounded-2xl bg-white p-3 ring-1 ring-[var(--site-line)] sm:mx-0">
          <QRCodeSVG value={url} size={132} level="M" marginSize={0} />
        </div>

        <div className="min-w-0 text-center sm:text-left">
          <h2 className="font-semibold text-[var(--site-ink)]">
            Partager {salonName}
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-[var(--site-muted)]">
            Scannez le code avec WeChat ou l&apos;appareil photo, ou envoyez le
            lien.
          </p>

          <p className="mt-3 break-all rounded-lg bg-[var(--salon-primary)]/[0.06] px-3 py-2 text-sm text-[var(--site-muted)]">
            {host}
          </p>

          <div className="mt-4 flex flex-wrap justify-center gap-2 sm:justify-start">
            {canShare && (
              <button
                type="button"
                onClick={share}
                className="salon-gradient inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:brightness-110"
              >
                <SalonIcon name="arrow" className="size-4" />
                Partager
              </button>
            )}

            <ShareAction
              href={`https://wa.me/?text=${encodeURIComponent(message)}`}
              icon="whatsapp"
              label="WhatsApp"
            />

            <button
              type="button"
              onClick={copy}
              aria-live="polite"
              className={ACTION}
            >
              <SalonIcon
                name={copied ? "check" : "sparkle"}
                className="size-4 text-[var(--salon-ink)]"
              />
              {copied ? "Lien copié" : "Copier le lien"}
            </button>

            {/*
              Les comptes du salon sur la meme rangee que WhatsApp.

              Ils y menent au meme geste — ouvrir le salon ailleurs — et une
              seconde rangee coupait la ligne du regard pour une distinction
              que les libelles portent deja tout seuls.
            */}
            {socials.map((social) => (
              <a
                key={social.key}
                href={social.href}
                target="_blank"
                rel="noreferrer noopener"
                className={`${ACTION} group`}
              >
                <SalonIcon
                  name={social.icon}
                  className="size-4 text-[var(--salon-ink)] transition-transform duration-300 group-hover:scale-110"
                />
                {social.label}
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const ACTION =
  "inline-flex items-center gap-2 rounded-full border border-[var(--site-line)] px-4 py-2.5 text-sm font-medium text-[var(--site-ink)] transition hover:border-[var(--salon-primary)] hover:text-[var(--salon-ink)]";

function ShareAction({
  href,
  icon,
  label,
}: {
  href: string;
  icon: "whatsapp";
  label: string;
}) {
  return (
    <a href={href} target="_blank" rel="noreferrer noopener" className={ACTION}>
      <SalonIcon name={icon} className="size-4 text-[var(--salon-ink)]" />
      {label}
    </a>
  );
}
