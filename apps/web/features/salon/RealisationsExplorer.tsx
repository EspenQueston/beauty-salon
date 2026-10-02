"use client";

/**
 * La page des réalisations, vivante : coups de cœur, filtres, visionneuse.
 *
 *   - **Coups de cœur** : les photos mises en vitrine par le salon, en
 *     bandeau qui glisse au doigt. Ce sont celles dont il est fier ; elles
 *     ouvrent la visionneuse comme les autres.
 *   - **Filtres** : une pastille par catégorie de prestation présente dans la
 *     galerie (reliée depuis l'espace pro), avec son compte. « Tout » d'abord.
 *     Sans photo reliée, pas de filtre : une seule pastille ne filtre rien.
 *   - **Grille** : celle de `GalleryGrid`, avec « Réserver ce look » et une
 *     adresse par photo (`?photo=…`) pour la partager.
 */

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { Lien } from "@/features/ui/Lien";
import { isVideo, type MediaAsset } from "@/lib/types";
import { GalleryGrid } from "./GalleryGrid";
import { SalonIcon } from "./icons";
import { photo, TAILLES } from "./images";
import { TeinteDeMarque } from "./Teinte";

const TOUT = "";

export function RealisationsExplorer({
  assets,
  salonName,
  reservable,
}: {
  assets: MediaAsset[];
  salonName: string;
  reservable: boolean;
}) {
  const t = useTranslations("salon.galeriePlus");
  const [filtre, setFiltre] = useState(TOUT);
  const [aOuvrir, setAOuvrir] = useState<{ id: string; jeton: number } | null>(
    null,
  );

  const categories = useMemo(() => {
    const comptes = new Map<string, { nom: string; n: number }>();
    for (const asset of assets) {
      const p = asset.prestation;
      if (!p?.categorie_id) continue;
      const deja = comptes.get(p.categorie_id);
      comptes.set(p.categorie_id, { nom: p.categorie, n: (deja?.n ?? 0) + 1 });
    }
    return [...comptes.entries()].map(([id, valeur]) => ({ id, ...valeur }));
  }, [assets]);

  const sansCategorie = assets.some((asset) => !asset.prestation?.categorie_id);
  const avecFiltres =
    categories.length >= 2 || (categories.length === 1 && sansCategorie);

  const visibles = filtre
    ? assets.filter((asset) => asset.prestation?.categorie_id === filtre)
    : assets;

  const coupsDeCoeur = assets.filter((asset) => asset.featured);

  return (
    <>
      {coupsDeCoeur.length >= 2 && (
        <section aria-labelledby="coups-de-coeur" className="mb-10 sm:mb-12">
          <div className="mb-4 flex items-end justify-between gap-3">
            <div>
              <h2
                id="coups-de-coeur"
                className="font-display text-xl font-semibold tracking-tight text-[var(--site-ink)] sm:text-2xl"
              >
                {t("coupsDeCoeur")}
              </h2>
              <p className="mt-1 text-[13px] text-[var(--site-muted)] sm:text-sm">
                {t("coupsDeCoeurCorps")}
              </p>
            </div>
            <span className="hidden shrink-0 text-xs text-[var(--site-subtle)] sm:block">
              {t("glisser")}
            </span>
          </div>
          <CoupsDeCoeur
            assets={coupsDeCoeur}
            onOuvrir={(asset) => {
              // La grille porte la visionneuse : on lui demande d'ouvrir
              // cette photo, sans filtre pour qu'elle y soit.
              setFiltre(TOUT);
              setAOuvrir({ id: asset.id, jeton: Date.now() });
            }}
            reservable={reservable}
          />
        </section>
      )}

      {avecFiltres && (
        <div
          role="toolbar"
          aria-label={t("filtrer")}
          className="-mx-4 mb-5 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0 [&::-webkit-scrollbar]:hidden"
        >
          {[{ id: TOUT, nom: t("tout"), n: assets.length }, ...categories].map(
            (categorie) => {
              const actif = filtre === categorie.id;
              return (
                <button
                  key={categorie.id || "tout"}
                  type="button"
                  aria-pressed={actif}
                  onClick={() => {
                    setFiltre(categorie.id);
                    setAOuvrir(null);
                  }}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-medium transition sm:text-sm ${
                    actif
                      ? "salon-gradient text-white shadow-sm"
                      : "border border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-ink)] hover:border-[var(--salon-primary)]"
                  }`}
                >
                  {categorie.nom}
                  <span
                    className={`tabular text-xs ${actif ? "text-white/75" : "text-[var(--site-subtle)]"}`}
                  >
                    {categorie.n}
                  </span>
                </button>
              );
            },
          )}
        </div>
      )}

      {/* La clé remonte la grille au changement de filtre : l'apparition
          rejoue, et l'œil voit que la sélection a changé. */}
      <div key={filtre || "tout"} id="grille-realisations">
        <GalleryGrid
          assets={visibles}
          salonName={salonName}
          reservable={reservable}
          lienDirect
          aOuvrir={aOuvrir}
        />
      </div>
    </>
  );
}

function CoupsDeCoeur({
  assets,
  onOuvrir,
  reservable,
}: {
  assets: MediaAsset[];
  onOuvrir: (asset: MediaAsset) => void;
  reservable: boolean;
}) {
  const t = useTranslations("salon.galeriePlus");
  return (
    <ul className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 [scrollbar-width:none] sm:mx-0 sm:px-0 [&::-webkit-scrollbar]:hidden">
      {assets.map((asset) => (
        <li key={asset.id} className="w-[68%] shrink-0 snap-start sm:w-64">
          <div className="group relative overflow-hidden rounded-2xl ring-1 ring-[var(--site-line)]">
            <button
              type="button"
              onClick={() => onOuvrir(asset)}
              className="block aspect-[4/5] w-full"
              aria-label={
                asset.prestation?.nom || asset.alt_text || t("coupsDeCoeur")
              }
            >
              {isVideo(asset) ? (
                <video
                  src={asset.url}
                  preload="metadata"
                  muted
                  playsInline
                  className="size-full object-cover"
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  {...photo(asset, TAILLES.grille)}
                  alt={asset.alt_text || asset.prestation?.nom || ""}
                  loading="lazy"
                  className="size-full object-cover transition-transform duration-500 group-hover:scale-105"
                />
              )}
              <TeinteDeMarque />
              <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 via-black/30 to-transparent p-3 pt-10 text-left text-white">
                <span className="mb-1 inline-flex items-center gap-1 rounded-full bg-white/20 px-2 py-0.5 text-[0.65rem] font-semibold backdrop-blur">
                  <SalonIcon name="star" className="size-3" filled />
                  {t("coupDeCoeur")}
                </span>
                {(asset.prestation?.nom || asset.alt_text) && (
                  <span className="block truncate text-sm font-semibold">
                    {asset.prestation?.nom || asset.alt_text}
                  </span>
                )}
                {asset.prestataire && (
                  <span className="block truncate text-xs text-white/75">
                    {t("par", { nom: asset.prestataire.nom })}
                  </span>
                )}
              </span>
            </button>
            {asset.prestation && reservable && (
              <Lien
                href={`/reserver?service=${encodeURIComponent(asset.prestation.id)}`}
                aria-label={`${t("reserverCeLook")} — ${asset.prestation.nom}`}
                className="salon-gradient absolute right-2 top-2 flex size-9 items-center justify-center rounded-full text-white shadow-md transition hover:brightness-110"
              >
                <SalonIcon name="calendar" className="size-4" />
              </Lien>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
