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
 *
 * ---------------------------------------------------------------------------
 * Sauf WeChat
 * ---------------------------------------------------------------------------
 *
 * Lui ne s'ouvre pas par une adresse : on rejoint quelqu'un en scannant son
 * QR, ou en tapant son identifiant dans la barre de recherche. Rangé parmi
 * les autres, le bouton « WeChat » menait donc à une page d'accueil
 * générique — une promesse non tenue, exactement ce que le reste de ce
 * fichier s'applique à éviter.
 *
 * Il ouvre maintenant un panneau qui montre **les deux ensemble**. Ce n'est
 * pas de la redondance : le QR sert à qui lit la page sur un ordinateur ou
 * une affichette, l'identifiant à qui la lit *dans* WeChat, où l'on ne peut
 * pas scanner son propre écran. Chacun couvre l'angle mort de l'autre.
 */

import { useTranslations } from "next-intl";
import { useState, useSyncExternalStore } from "react";
import { QRCodeSVG } from "qrcode.react";

import type { MediaAsset } from "@/lib/types";
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
  wechatId = "",
  wechatQr = null,
}: {
  host: string;
  salonName: string;
  /** Comptes renseignés par le salon. Vide s'il n'en a déclaré aucun. */
  socials?: ContactLink[];
  /** L'identifiant WeChat du salon, tel qu'on le tape pour le chercher. */
  wechatId?: string;
  /** Le QR qui ajoute le salon en contact. */
  wechatQr?: MediaAsset | null;
}) {
  const t = useTranslations("salon");
  const [copied, setCopied] = useState(false);
  const [copiedId, setCopiedId] = useState(false);
  const [wechatOuvert, setWechatOuvert] = useState(false);
  const canShare = useSyncExternalStore(
    NEVER_CHANGES,
    readShareSupport,
    noShareOnServer,
  );

  const url = `https://${host}`;
  const message = t("partage.message", { salon: salonName, url });

  /*
    Le bouton WeChat n'existe que s'il y a de quoi le remplir.

    L'ancienne adresse collée dans « Réseaux sociaux » a disparu : elle ne
    menait qu'à l'accueil de WeChat, ce qui est le contraire d'un contact.
    C'est le QR ou l'identifiant, ou rien.
  */
  const aWechat = Boolean(wechatId.trim() || wechatQr);

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

  async function copierIdentifiant() {
    try {
      await navigator.clipboard.writeText(wechatId.trim());
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2200);
    } catch {
      // L'identifiant reste affiché en clair : il se recopie à la main.
      setCopiedId(false);
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
            {t("partage.scannez")}
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
              {copied ? t("partage.copie") : t("partage.copier")}
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

            {aWechat && (
              <button
                type="button"
                onClick={() => setWechatOuvert((ouvert) => !ouvert)}
                aria-expanded={wechatOuvert}
                aria-controls="panneau-wechat"
                className={`${ACTION} group ${
                  wechatOuvert ? "border-[var(--salon-primary)]" : ""
                }`}
              >
                <SalonIcon
                  name="wechat"
                  className="size-4 text-[var(--salon-ink)] transition-transform duration-300 group-hover:scale-110"
                />
                WeChat
                <SalonIcon
                  name="arrow"
                  aria-hidden
                  className={`size-3.5 opacity-50 transition-transform duration-300 ${
                    wechatOuvert ? "-rotate-90" : "rotate-90"
                  }`}
                />
              </button>
            )}
          </div>

          {aWechat && wechatOuvert && (
            <PanneauWechat
              id="panneau-wechat"
              salonName={salonName}
              identifiant={wechatId.trim()}
              qr={wechatQr}
              copie={copiedId}
              onCopier={copierIdentifiant}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Le QR et l'identifiant, ensemble.
 *
 * Il se déplie sous la rangée plutôt que dans une fenêtre modale : il n'y a
 * rien à décider ici, seulement quelque chose à lire. Une modale aurait
 * demandé un piège de focus et un bouton pour refermer, pour un contenu de
 * trois lignes qu'on regarde puis qu'on quitte.
 */
function PanneauWechat({
  id,
  salonName,
  identifiant,
  qr,
  copie,
  onCopier,
}: {
  id: string;
  salonName: string;
  identifiant: string;
  qr: MediaAsset | null;
  copie: boolean;
  onCopier: () => void;
}) {
  const t = useTranslations("salon");
  return (
    <div
      id={id}
      className="mt-4 flex flex-col gap-4 rounded-xl border border-[var(--site-line)] bg-[var(--salon-primary)]/[0.04] p-4 text-left sm:flex-row sm:items-center"
    >
      {qr && (
        /*
          Fond blanc quel que soit le thème, comme le QR du lien juste
          au-dessus : un code inversé n'est plus lisible par la moitié des
          téléphones, et le mini-site passe en sombre chez qui le demande.
        */
        <div className="mx-auto w-fit shrink-0 rounded-xl bg-white p-2.5 ring-1 ring-[var(--site-line)] sm:mx-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={qr.url}
            alt={t("partage.qrWechat", { salon: salonName })}
            /*
              Chargée tout de suite, pas en différé.

              Le panneau n'existe qu'une fois le bouton pressé : l'image est
              donc demandée au moment précis où elle apparaît. En « lazy »,
              le navigateur la mettait en file d'attente et le cadre restait
              vide une seconde — juste après le seul geste dont le but était
              de la voir.
            */
            loading="eager"
            className="size-32 object-contain"
          />
        </div>
      )}

      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-[var(--site-ink)]">
          {qr
            ? t("partage.wechatTitre")
            : t("partage.chercher", { salon: salonName })}
        </p>
        <p className="mt-1 text-[0.8rem] leading-relaxed text-[var(--site-muted)]">
          {qr ? t("partage.wechatBureau") : t("partage.wechatTelephone")}
        </p>

        {identifiant && (
          <button
            type="button"
            onClick={onCopier}
            aria-live="polite"
            className="mt-3 inline-flex max-w-full items-center gap-2 rounded-lg border border-[var(--site-line)] bg-[var(--site-surface)] px-3 py-2 text-sm transition hover:border-[var(--salon-primary)]"
          >
            <SalonIcon
              name={copie ? "check" : "sparkle"}
              className="size-4 shrink-0 text-[var(--salon-ink)]"
            />
            <span className="truncate font-medium text-[var(--site-ink)]">
              {identifiant}
            </span>
            <span className="shrink-0 text-xs text-[var(--site-subtle)]">
              {copie ? "copié" : "copier"}
            </span>
          </button>
        )}
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
