"use client";

/**
 * Le catalogue en galerie, et l'interrupteur qui y mène.
 *
 * La liste dit tout d'une prestation ; la galerie montre ce que la cliente
 * verra — **la même image que le mini-site**, au même cadrage : la photo du
 * salon, ou à défaut l'illustration d'ambiance que le mini-site choisit
 * pour cette prestation (`ServiceCard`, page Prestations). Une gérante
 * repère ainsi d'un coup d'œil les prestations encore illustrées par une
 * photo générique, et en remplace une d'un toucher.
 *
 * Le choix de vue est mémorisé sur l'appareil. Sans choix, un téléphone part
 * sur la galerie (deux colonnes, l'écran se lit sans défiler sans fin) et un
 * ordinateur sur la liste, plus dense.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from "react";

import { photo as attributsPhoto, TAILLES } from "@/features/salon/images";
import { Icon } from "./icons";
import type { PickableMedia } from "./MediaPicker";

export type VuePrestations = "liste" | "galerie";

const CLE = "beauty-salon-vue-prestations";
const ECRAN_ETROIT = "(max-width: 639px)";
const abonnes = new Set<() => void>();
// Navigation privée ou stockage bloqué : le choix tient au moins jusqu'au
// rechargement de la page.
let enMemoire: VuePrestations | null = null;

function lireVue(): VuePrestations {
  if (enMemoire) return enMemoire;
  try {
    const stockee = localStorage.getItem(CLE);
    if (stockee === "liste" || stockee === "galerie") return stockee;
  } catch {
    // Stockage indisponible : la valeur par défaut fait foi.
  }
  return window.matchMedia(ECRAN_ETROIT).matches ? "galerie" : "liste";
}

function suivreVue(rappel: () => void) {
  abonnes.add(rappel);
  const surStockage = (event: StorageEvent) => {
    if (event.key === CLE) rappel();
  };
  // Sans choix enregistré, la vue suit la largeur : un téléphone tourné en
  // paysage, une fenêtre rétrécie.
  const ecran = window.matchMedia(ECRAN_ETROIT);
  window.addEventListener("storage", surStockage);
  ecran.addEventListener("change", rappel);
  return () => {
    abonnes.delete(rappel);
    window.removeEventListener("storage", surStockage);
    ecran.removeEventListener("change", rappel);
  };
}

export function useVuePrestations(): [VuePrestations, (vue: VuePrestations) => void] {
  // Côté serveur, la liste : c'est la vue d'origine, et l'écran se corrige
  // dès l'hydratation si l'appareil en préfère une autre.
  const vue = useSyncExternalStore(suivreVue, lireVue, () => "liste" as VuePrestations);
  const choisir = useCallback((suivante: VuePrestations) => {
    enMemoire = suivante;
    try {
      localStorage.setItem(CLE, suivante);
    } catch {
      // Le choix reste en mémoire pour cette page.
    }
    abonnes.forEach((rappel) => rappel());
  }, []);
  return [vue, choisir];
}

export function SelecteurVue({
  vue,
  onChange,
}: {
  vue: VuePrestations;
  onChange: (vue: VuePrestations) => void;
}) {
  const t = useTranslations("pro.prestations.vue");
  return (
    <div
      role="group"
      aria-label={t("aria")}
      className="relative inline-grid shrink-0 grid-cols-2 rounded-xl border border-line bg-surface p-0.5"
    >
      {/* Le repère glisse d'un choix à l'autre : on voit la vue changer de
          côté, plutôt que deux boutons qui échangent leur couleur. */}
      <span
        aria-hidden
        className={`absolute inset-y-0.5 left-0.5 w-[calc(50%-2px)] rounded-[10px] bg-salon shadow-sm transition-transform duration-300 ease-out motion-reduce:transition-none ${
          vue === "galerie" ? "translate-x-full" : ""
        }`}
      />
      {(["liste", "galerie"] as const).map((choix) => (
        <button
          key={choix}
          type="button"
          aria-pressed={vue === choix}
          title={t(choix)}
          onClick={() => onChange(choix)}
          className={`relative z-10 inline-flex items-center justify-center gap-1.5 rounded-[10px] px-3 py-2 text-sm font-medium transition-colors ${
            vue === choix ? "text-white" : "text-muted hover:text-ink"
          }`}
        >
          <Icon name={choix === "liste" ? "rows" : "grid"} className="size-4" />
          <span className="sr-only sm:not-sr-only">{t(choix)}</span>
        </button>
      ))}
    </div>
  );
}

export interface TuileProps {
  nom: string;
  description: string;
  active: boolean;
  /** Le média de la prestation, s'il est chargé. */
  photo: PickableMedia | undefined;
  /**
   * L'illustration d'ambiance du mini-site pour cette prestation : affichée
   * à défaut de photo, comme sur le mini-site.
   */
  illustration: string;
  prix: string;
  details: string;
  acompte: string | null;
  canEdit: boolean;
  recente: boolean;
  /** Rang dans la grille : décale l'entrée des vignettes. */
  rang: number;
  onModifier: (bouton: HTMLElement) => void;
  onBasculer: () => void;
  onSupprimer: () => void;
}

export function TuilePrestation({
  nom,
  description,
  active,
  photo,
  illustration,
  prix,
  details,
  acompte,
  canEdit,
  recente,
  rang,
  onModifier,
  onBasculer,
  onSupprimer,
}: TuileProps) {
  const t = useTranslations("pro.prestations");
  const [cassee, setCassee] = useState(false);

  /*
   * Supprimer en deux temps.
   *
   * Dans la liste, « Supprimer » est un bouton large et nommé. Ici, c'est une
   * petite corbeille au bout du pouce, à côté de « Modifier » : un toucher
   * imprécis effaçait une prestation. Le premier toucher demande, le second
   * confirme ; sans réponse, la demande retombe.
   */
  const [confirmer, setConfirmer] = useState(false);
  const confirmation = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!confirmer) return;
    confirmation.current?.focus();
    const delai = window.setTimeout(() => setConfirmer(false), 4000);
    return () => window.clearTimeout(delai);
  }, [confirmer]);

  const video = photo?.content_type.startsWith("video/");
  const visible = photo && !cassee;
  const teinte = active ? "" : "opacity-60 grayscale";
  const style = { "--i": Math.min(rang, 12) } as CSSProperties;

  return (
    <li className="vue-entre" style={style}>
      <article
        className={`group relative flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card transition duration-300 hover:-translate-y-0.5 hover:shadow-lg motion-reduce:transition-none motion-reduce:hover:translate-y-0 ${
          recente ? "ring-2 ring-salon/60 ring-offset-2 ring-offset-bg" : ""
        }`}
      >
        {/* Le cadrage des cartes du mini-site (16/10) : la gérante voit sa
            vignette telle que ses clientes la verront. */}
        <div className="relative aspect-[16/10] overflow-hidden bg-surface-hover">
          {visible && video ? (
            <video
              // `#t=0.1` : Safari n'affiche rien d'une vidéo non lue sans
              // un instant de départ.
              src={`${photo.url}#t=0.1`}
              muted
              playsInline
              preload="metadata"
              aria-hidden
              onError={() => setCassee(true)}
              className={`size-full object-cover transition duration-500 group-hover:scale-[1.04] motion-reduce:transition-none ${teinte}`}
            />
          ) : visible ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              {...attributsPhoto(photo, TAILLES.grille)}
              alt={photo.alt_text || nom}
              loading="lazy"
              decoding="async"
              onError={() => setCassee(true)}
              className={`size-full object-cover transition duration-500 group-hover:scale-[1.04] motion-reduce:transition-none ${teinte}`}
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={illustration}
              alt=""
              loading="lazy"
              decoding="async"
              className={`size-full object-cover transition duration-500 group-hover:scale-[1.04] motion-reduce:transition-none ${teinte}`}
            />
          )}

          {/* Illustration générique : le rappel qu'une vraie photo ferait
              mieux, sans masquer l'image. */}
          {!visible && canEdit && (
            <span
              aria-hidden
              className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-full bg-black/55 px-2 py-1 text-[11px] font-medium text-white backdrop-blur"
            >
              <Icon name="image" className="size-3.5" />
              <span className="hidden sm:inline">{t("galerie.ajouterPhoto")}</span>
            </span>
          )}

          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/60 to-transparent"
          />
          <span className="tabular absolute bottom-2 left-2.5 right-2.5 truncate text-xs font-semibold text-white drop-shadow sm:bottom-2.5 sm:left-3 sm:text-sm">
            {prix}
          </span>
          {!active && (
            <span className="absolute left-2 top-2 rounded-full bg-black/60 px-2 py-0.5 text-[11px] font-medium text-white backdrop-blur">
              {t("inactive")}
            </span>
          )}

          {/* Toute la vignette ouvre la fiche : c'est la cible que le pouce
              vise naturellement. */}
          {canEdit && (
            <button
              type="button"
              onClick={(event) => onModifier(event.currentTarget)}
              aria-label={t("galerie.modifierAria", { nom })}
              className="absolute inset-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-salon"
            />
          )}
        </div>

        <div className="flex flex-1 flex-col p-2.5 sm:p-3.5">
          <h3 className="line-clamp-2 text-[13px] font-semibold leading-snug text-ink sm:text-[15px]">
            {nom}
          </h3>
          <p className="mt-1 flex items-start gap-1 text-[11px] leading-snug text-muted sm:text-xs">
            <Icon name="clock" className="mt-px size-3.5 shrink-0" />
            <span>{details}</span>
          </p>
          {acompte && (
            <p className="mt-0.5 text-[11px] leading-snug text-subtle sm:text-xs">{acompte}</p>
          )}
          {description && (
            <div className="mt-1.5 hidden sm:block">
              <p className="line-clamp-2 text-xs leading-relaxed text-subtle">{description}</p>
            </div>
          )}

          {canEdit && (
            <div className="mt-auto flex items-center gap-1 pt-2.5 sm:gap-1.5">
              {confirmer ? (
                <>
                  <button
                    type="button"
                    onClick={() => setConfirmer(false)}
                    className="inline-flex min-h-9 flex-1 items-center justify-center rounded-lg border border-line bg-surface px-2 text-xs font-medium text-ink transition hover:bg-surface-hover sm:text-sm"
                  >
                    {t("galerie.annuler")}
                  </button>
                  <button
                    ref={confirmation}
                    type="button"
                    onClick={() => {
                      setConfirmer(false);
                      onSupprimer();
                    }}
                    aria-label={t("galerie.confirmerAria", { nom })}
                    className="inline-flex min-h-9 flex-1 items-center justify-center gap-1 rounded-lg bg-danger px-2 text-xs font-semibold text-white transition hover:brightness-110 sm:text-sm"
                  >
                    <Icon name="trash" className="size-3.5" />
                    {t("supprimer")}
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={(event) => onModifier(event.currentTarget)}
                    aria-label={t("galerie.modifierAria", { nom })}
                    className="inline-flex min-h-9 min-w-0 flex-1 items-center justify-center gap-1.5 rounded-lg border border-line bg-surface px-1.5 text-xs font-medium text-ink transition hover:bg-surface-hover sm:px-2 sm:text-sm"
                  >
                    {/* Sur téléphone, le libellé seul : avec l'icône, il était
                        coupé (« Mo… ») — et la photo ouvre déjà la fiche. */}
                    <Icon name="edit" className="hidden size-3.5 shrink-0 sm:block" />
                    <span className="truncate">{t("modifier")}</span>
                  </button>
                  <button
                    type="button"
                    onClick={onBasculer}
                    aria-label={`${active ? t("desactiver") : t("activer")} · ${nom}`}
                    title={active ? t("desactiver") : t("activer")}
                    className="grid h-9 w-8 shrink-0 place-items-center rounded-lg border border-line bg-surface text-muted transition hover:bg-surface-hover hover:text-ink sm:w-9"
                  >
                    <Icon name={active ? "eye-off" : "eye"} className="size-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmer(true)}
                    aria-label={`${t("supprimer")} · ${nom}`}
                    title={t("supprimer")}
                    className="grid h-9 w-8 shrink-0 place-items-center rounded-lg bg-danger-bg text-danger transition hover:brightness-95 sm:w-9"
                  >
                    <Icon name="trash" className="size-4" />
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </article>
    </li>
  );
}
