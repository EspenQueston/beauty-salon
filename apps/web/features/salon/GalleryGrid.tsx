"use client";

/**
 * Réalisations du salon : photos et vidéos courtes.
 *
 * C'est la section qui convainc. Un tarif rassure, une photo décide — la
 * cliente veut voir des tresses déjà faites, pas lire qu'on en fait.
 *
 * Trois choix qui comptent sur les réseaux mobiles visés :
 *
 *   - les vidéos ne se chargent pas toutes seules (`preload="metadata"`) ;
 *     une grille de six vidéos en lecture automatique coûterait plusieurs
 *     dizaines de mégaoctets à quelqu'un qui paie sa donnée ;
 *   - la visionneuse ne charge le média en grand qu'à l'ouverture ;
 *   - la mosaïque est irrégulière mais déterministe : elle donne du rythme
 *     sans dépendre du format réel des fichiers, qu'on ne connaît pas
 *     toujours.
 *
 * ---------------------------------------------------------------------------
 * De la photo à la réservation
 * ---------------------------------------------------------------------------
 *
 * Une réalisation reliée à une prestation (écran Galerie de l'espace pro) dit
 * ce qu'elle montre, combien, combien de temps, et qui l'a faite — et propose
 * « Réserver ce look », qui ouvre la réservation sur cette prestation. Une
 * cliente qui tombe sur la photo de ses rêves n'a plus à chercher la ligne
 * correspondante dans le catalogue.
 *
 * Chaque photo a aussi son adresse (`?photo=…`, avec `lienDirect`) : partagée
 * sur WhatsApp, elle rouvre la visionneuse sur cette photo-là.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { Lien } from "@/features/ui/Lien";
import { Reveal } from "@/features/ui/Reveal";
import { formatDuration } from "@/lib/format";
import { isVideo, type MediaAsset } from "@/lib/types";
import { Prix } from "./Devise";
import { SalonIcon } from "./icons";
import { photo, TAILLES } from "./images";
import { TeinteDeMarque } from "./Teinte";

/** Motif de tailles répété : la 1re et la 6e occupent deux colonnes. */
function spanOf(index: number): string {
  const position = index % 6;
  if (position === 0) return "sm:col-span-2 sm:row-span-2";
  if (position === 5) return "sm:col-span-2";
  return "";
}

const PARAMETRE = "photo";

function titreDe(asset: MediaAsset): string {
  return asset.prestation?.nom || asset.alt_text || "";
}

export function GalleryGrid({
  assets,
  salonName,
  reservable = true,
  lienDirect = false,
  aOuvrir,
}: {
  assets: MediaAsset[];
  salonName: string;
  /** Faux quand le salon ne prend plus de réservations : pas de « Réserver ce look ». */
  reservable?: boolean;
  /** Chaque photo ouverte prend son adresse (`?photo=…`), et l'adresse rouvre la photo. */
  lienDirect?: boolean;
  /** Ouvrir cette photo depuis l'extérieur (un coup de cœur). `jeton` change à chaque demande. */
  aOuvrir?: { id: string; jeton: number } | null;
}) {
  const t = useTranslations("salon");
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const ouvrir = useCallback(
    (index: number | null) => {
      setOpenIndex(index);
      if (!lienDirect) return;
      const url = new URL(window.location.href);
      if (index === null) url.searchParams.delete(PARAMETRE);
      else url.searchParams.set(PARAMETRE, assets[index].id);
      window.history.replaceState(null, "", url);
    },
    [assets, lienDirect],
  );

  const close = useCallback(() => ouvrir(null), [ouvrir]);

  const move = useCallback(
    (delta: number) => {
      if (openIndex === null) return;
      ouvrir((openIndex + delta + assets.length) % assets.length);
    },
    [assets.length, openIndex, ouvrir],
  );

  // Une adresse partagée rouvre sa photo. Après le premier rendu : le
  // serveur ne connaît pas `?photo=`, la grille s'affiche d'abord fermée.
  const dejaLu = useRef(false);
  useEffect(() => {
    if (!lienDirect || dejaLu.current) return;
    dejaLu.current = true;
    const voulu = new URLSearchParams(window.location.search).get(PARAMETRE);
    const index = voulu ? assets.findIndex((asset) => asset.id === voulu) : -1;
    if (index >= 0) void Promise.resolve().then(() => setOpenIndex(index));
  }, [assets, lienDirect]);

  // Une demande d'ouverture venue d'ailleurs sur la page (un coup de cœur).
  useEffect(() => {
    if (!aOuvrir) return;
    const index = assets.findIndex((asset) => asset.id === aOuvrir.id);
    if (index >= 0) void Promise.resolve().then(() => ouvrir(index));
  }, [aOuvrir, assets, ouvrir]);

  // Clavier : échappement pour fermer, flèches pour parcourir. Une galerie
  // qu'on ne peut quitter qu'à la souris piège qui navigue au clavier.
  useEffect(() => {
    if (openIndex === null) return;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "ArrowRight") move(1);
      if (event.key === "ArrowLeft") move(-1);
    };

    document.addEventListener("keydown", onKey);
    // Le fond ne doit pas défiler derrière la visionneuse.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [openIndex, close, move]);

  // Glisser du doigt pour passer d'une photo à l'autre, comme partout ailleurs
  // sur un téléphone.
  const depart = useRef<number | null>(null);

  const open = openIndex === null ? null : assets[openIndex];

  return (
    <>
      <ul className="grid auto-rows-[10rem] grid-cols-2 gap-3 sm:auto-rows-[12rem] sm:grid-cols-4">
        {assets.map((asset, index) => {
          const titre = titreDe(asset);
          return (
            /*
              L'apparition est portee par le <li> lui-meme via `as`.

              Envelopper la tuile dans un <div> casserait la grille : c'est le
              <li> qui porte les classes de colonne, et un intermediaire lui
              volerait sa place. Le decalage est plafonne a huit tuiles, sinon
              la quarantieme photo attendrait trois secondes pour rien.
            */
            <Reveal
              as="li"
              key={asset.id}
              delay={Math.min(index, 8) * 60}
              className={spanOf(index)}
            >
              {/*
                La légende est sous le média, pas dessus : superposée, elle
                n'apparaissait qu'au survol — donc jamais sur un téléphone — et
                sa lisibilité dépendait de la photo. Sur une bande unie, elle
                se lit toujours.
              */}
              <button
                type="button"
                onClick={() => ouvrir(index)}
                className="group flex size-full flex-col overflow-hidden rounded-2xl bg-[var(--site-surface)] text-left ring-1 ring-[var(--site-line)] transition hover:ring-[var(--salon-primary)]"
                aria-label={
                  titre ||
                  t("galerie.altNumerotee", { n: index + 1, salon: salonName })
                }
              >
                <span className="relative min-h-0 flex-1 overflow-hidden bg-black/[0.05]">
                  {isVideo(asset) ? (
                    <>
                      <video
                        src={asset.url}
                        preload="metadata"
                        muted
                        playsInline
                        className="size-full object-cover transition-transform duration-500 group-hover:scale-105"
                      />
                      <span className="absolute inset-0 flex items-center justify-center bg-black/25">
                        <span className="flex size-12 items-center justify-center rounded-full bg-white/90 text-[var(--salon-ink-white)] shadow-lg transition-transform duration-300 group-hover:scale-110">
                          <SalonIcon name="play" className="size-6" filled />
                        </span>
                      </span>
                    </>
                  ) : (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        {...photo(asset, TAILLES.grille)}
                        alt={
                          asset.alt_text ||
                          titre ||
                          t("galerie.alt", { salon: salonName })
                        }
                        loading="lazy"
                        className="size-full object-cover transition-transform duration-500 group-hover:scale-105"
                      />
                      <TeinteDeMarque />
                    </>
                  )}
                  {asset.prestation && reservable && (
                    <span className="absolute right-2 top-2 rounded-full bg-black/45 px-2 py-0.5 text-[0.65rem] font-semibold text-white backdrop-blur-sm sm:text-[0.7rem]">
                      {t("galeriePlus.reservable")}
                    </span>
                  )}
                </span>

                {(titre || asset.prestataire) && (
                  <span className="shrink-0 px-2.5 py-2">
                    {titre && (
                      <span className="line-clamp-1 text-[0.72rem] font-semibold leading-snug text-[var(--site-ink)] sm:text-xs">
                        {titre}
                      </span>
                    )}
                    {asset.prestataire && (
                      <span className="line-clamp-1 text-[0.68rem] text-[var(--site-muted)] sm:text-[0.72rem]">
                        {t("galeriePlus.par", { nom: asset.prestataire.nom })}
                      </span>
                    )}
                  </span>
                )}
              </button>
            </Reveal>
          );
        })}
      </ul>

      {open && openIndex !== null && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={titreDe(open) || t("galerie.simple")}
          onClick={close}
          onTouchStart={(event) => {
            depart.current = event.touches[0]?.clientX ?? null;
          }}
          onTouchEnd={(event) => {
            const debut = depart.current;
            depart.current = null;
            const fin = event.changedTouches[0]?.clientX;
            if (debut === null || fin === undefined || assets.length < 2)
              return;
            if (Math.abs(fin - debut) > 50) move(fin < debut ? 1 : -1);
          }}
          className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/85 p-3 backdrop-blur-sm sm:p-6"
        >
          <button
            type="button"
            onClick={close}
            aria-label="Fermer"
            className="fixed right-3 top-3 z-10 flex size-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20 sm:right-4 sm:top-4"
          >
            <SalonIcon name="close" className="size-5" />
          </button>

          {assets.length > 1 && (
            <>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  move(-1);
                }}
                aria-label={t("precedente")}
                className="fixed left-2 top-1/2 z-10 hidden size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20 sm:flex"
              >
                <SalonIcon name="arrow" className="size-5 rotate-180" />
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  move(1);
                }}
                aria-label={t("suivante")}
                className="fixed right-2 top-1/2 z-10 hidden size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20 sm:flex"
              >
                <SalonIcon name="arrow" className="size-5" />
              </button>
            </>
          )}

          <figure
            onClick={(event) => event.stopPropagation()}
            className="my-auto grid w-full max-w-5xl gap-3 sm:gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-center"
          >
            {isVideo(open) ? (
              <video
                key={open.id}
                src={open.url}
                controls
                autoPlay
                playsInline
                className="max-h-[62svh] w-full rounded-2xl bg-black object-contain lg:max-h-[82svh]"
              />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={open.id}
                {...photo(open, TAILLES.pleineLargeur)}
                alt={
                  open.alt_text ||
                  titreDe(open) ||
                  t("galerie.alt", { salon: salonName })
                }
                className="max-h-[62svh] w-full rounded-2xl object-contain lg:max-h-[82svh]"
              />
            )}

            <Fiche
              asset={open}
              position={openIndex + 1}
              total={assets.length}
              salonName={salonName}
              reservable={reservable}
              lienDirect={lienDirect}
            />
          </figure>
        </div>
      )}
    </>
  );
}

/** Ce que montre la photo, et ce qu'on peut en faire. */
function Fiche({
  asset,
  position,
  total,
  salonName,
  reservable,
  lienDirect,
}: {
  asset: MediaAsset;
  position: number;
  total: number;
  salonName: string;
  reservable: boolean;
  lienDirect: boolean;
}) {
  const t = useTranslations("salon");
  const [copie, setCopie] = useState(false);
  const prestation = asset.prestation;
  const titre = titreDe(asset);
  const description =
    prestation && asset.alt_text && asset.alt_text !== prestation.nom
      ? asset.alt_text
      : "";

  async function partager() {
    const url = window.location.href;
    const texte = t("galeriePlus.partageMessage", { salon: salonName, url });
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: titre || salonName, text: texte, url });
        return;
      } catch {
        /* partage annulé : rien à dire */
        return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopie(true);
      window.setTimeout(() => setCopie(false), 1800);
    } catch {
      window.open(
        `https://wa.me/?text=${encodeURIComponent(texte)}`,
        "_blank",
        "noopener",
      );
    }
  }

  return (
    <figcaption className="rounded-2xl bg-white/[0.07] p-4 text-white ring-1 ring-white/10 backdrop-blur sm:p-5">
      <div className="flex items-center justify-between gap-3 text-[0.7rem] uppercase tracking-[0.14em] text-white/55 sm:text-xs">
        <span className="truncate">
          {prestation?.categorie || t("galerie.simple")}
        </span>
        <span className="tabular shrink-0 normal-case tracking-normal">
          {position} / {total}
        </span>
      </div>

      {titre && (
        <p className="mt-2 text-lg font-semibold leading-snug sm:text-xl">
          {titre}
        </p>
      )}
      {description && (
        <p className="mt-1 text-sm leading-relaxed text-white/75">
          {description}
        </p>
      )}

      {(prestation || asset.prestataire) && (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          {prestation && (
            <div className="rounded-xl bg-white/[0.06] px-3 py-2">
              <dt className="text-[0.68rem] text-white/55">
                {t("galeriePlus.tarif")}
              </dt>
              <dd className="mt-0.5 font-semibold">
                {prestation.prix_type === "quote" ? (
                  t("prix.surDevis")
                ) : (
                  <Prix
                    montant={prestation.prix}
                    prefixe={
                      prestation.prix_type === "from"
                        ? t("prix.aPartirDeSeul")
                        : ""
                    }
                    className="tabular"
                  />
                )}
              </dd>
            </div>
          )}
          {prestation && (
            <div className="rounded-xl bg-white/[0.06] px-3 py-2">
              <dt className="text-[0.68rem] text-white/55">
                {t("galeriePlus.duree")}
              </dt>
              <dd className="mt-0.5 font-semibold">
                {formatDuration(prestation.duree)}
              </dd>
            </div>
          )}
          {asset.prestataire && (
            <div className="col-span-2 flex items-center gap-2 rounded-xl bg-white/[0.06] px-3 py-2">
              <SalonIcon
                name="user"
                className="size-4 shrink-0 text-white/60"
              />
              <dt className="sr-only">{t("galeriePlus.artiste")}</dt>
              <dd className="text-sm">
                {t("galeriePlus.realiseePar", { nom: asset.prestataire.nom })}
              </dd>
            </div>
          )}
        </dl>
      )}

      <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-1">
        {prestation && reservable ? (
          <Lien
            href={`/reserver?service=${encodeURIComponent(prestation.id)}`}
            className="salon-gradient col-span-1 inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:brightness-110"
          >
            <SalonIcon name="calendar" className="size-4" />
            {t("galeriePlus.reserverCeLook")}
          </Lien>
        ) : reservable ? (
          <Lien
            href="/reserver"
            className="salon-gradient inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:brightness-110"
          >
            <SalonIcon name="calendar" className="size-4" />
            {t("galeriePlus.reserver")}
          </Lien>
        ) : null}
        {lienDirect && (
          <button
            type="button"
            onClick={() => void partager()}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/20 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"
          >
            <SalonIcon
              name={copie ? "check" : "arrow"}
              className={`size-4 ${copie ? "" : "-rotate-45"}`}
            />
            {copie ? t("galeriePlus.lienCopie") : t("galeriePlus.partager")}
          </button>
        )}
      </div>
    </figcaption>
  );
}
