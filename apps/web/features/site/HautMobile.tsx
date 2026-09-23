"use client";

/**
 * Le haut de page, version téléphone.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'il fallait réparer
 * ---------------------------------------------------------------------------
 *
 * La version qui se contentait de rétrécir empilait : titre, paragraphe de
 * quatre lignes, deux boutons, mention, vérificateur d'adresse, puis la
 * photo. Deux écrans à parcourir avant de voir à quoi ressemble le produit,
 * et la photo — la seule chose qui dise « salon de beauté » sans être lue —
 * arrivait en dernier.
 *
 * ---------------------------------------------------------------------------
 * L'ordre retenu
 * ---------------------------------------------------------------------------
 *
 *   1. le métier, en une ligne de repères ;
 *   2. la promesse en trois mots ;
 *   3. **la photo**, pleine largeur, avec deux éléments d'interface posés
 *      dessus — l'heure d'un rendez-vous et l'adresse d'un mini-site. On voit
 *      le produit avant de lire ce qu'il fait ;
 *   4. une phrase, une seule ;
 *   5. le bouton, puis le film.
 *
 * Le vérificateur d'adresse descend dans sa propre section : c'est un geste
 * qu'on fait après avoir compris, pas avant.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi la photo est ici et pas en fond
 * ---------------------------------------------------------------------------
 *
 * Poser le titre par-dessus l'image aurait été plus spectaculaire. Mais le
 * contraste d'un texte sur photographie dépend de la photographie, donc il ne
 * se garantit pas : il faudrait un voile assez sombre pour couvrir le pire
 * pixel, et ce voile ferait disparaître le salon qu'on voulait montrer.
 *
 * La photo occupe donc sa propre bande. Le texte garde le fond de la page, et
 * son contraste est celui du thème — mesurable, et le même partout.
 */

import { useEffect, useRef, useState } from "react";

import { useTranslations } from "next-intl";

import { Fleche } from "@/features/site/contenu";
import { illustrationUrl } from "@/lib/illustrations";
import { appUrl } from "@/lib/site";

export function HautMobile({ photo }: { photo: string }) {
  const t = useTranslations("accueil");
  const c = useTranslations("commun");
  /* Les métiers et la promesse sont des listes : leur nombre peut différer
     d'une langue à l'autre, et rien dans la mise en page n'en dépend. */
  const metiers = t.raw("metiers") as string[];
  const promesse = t.raw("promesse") as string[];

  return (
    <section className="relative isolate overflow-hidden px-4 pb-8 pt-24 sm:hidden">
      <div aria-hidden className="aurore">
        <span />
        <span />
        <span />
      </div>

      <div className="relative z-10">
        {/* Les métiers d'abord : « Réservez. Coiffez. Encaissez. » ne dit pas
            à qui la page s'adresse, et c'est la première chose à savoir. */}
        <ul
          className="rise flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[0.7rem] font-semibold uppercase tracking-[0.1em] text-salon-ink"
          style={{ animationDelay: "60ms" }}
        >
          {metiers.map((metier, index) => (
            <li key={metier} className="flex items-center gap-1.5">
              {index > 0 && (
                <span
                  aria-hidden
                  className="size-1 rounded-full bg-salon-ink/40"
                />
              )}
              {metier}
            </li>
          ))}
        </ul>

        <h1 className="mt-3 text-[2.9rem] font-semibold leading-[0.93] tracking-tight text-ink">
          {promesse.map((mot, index) => (
            <span
              key={mot}
              className="rise block"
              style={{ animationDelay: `${140 + index * 90}ms` }}
            >
              {mot}
              <span className="text-salon-ink">.</span>
            </span>
          ))}
        </h1>
      </div>

      {/* ------------------------------------------------------- la photo */}
      <div
        className="rise pleine-largeur relative z-10 mt-6"
        style={{ animationDelay: "420ms" }}
      >
        <div className="relative overflow-hidden rounded-3xl border border-line shadow-float">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={photo}
            alt=""
            fetchPriority="high"
            className="derive aspect-[16/11] size-full object-cover"
          />
          {/* Un voile en bas : il n'est là que pour asseoir les deux pastilles,
              pas pour porter du texte. */}
          <div
            aria-hidden
            className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/45 to-transparent"
          />

          <span className="verre absolute left-3 top-3 flex items-center gap-2 rounded-xl px-2.5 py-1.5 shadow-float">
            <span
              aria-hidden
              className="pouls size-1.5 shrink-0 rounded-full bg-salon"
            />
            <span className="tabular text-[0.72rem] font-semibold text-ink">
              10:30 · Cornrows
            </span>
          </span>

          <span className="verre absolute bottom-3 right-3 flex max-w-[calc(100%-1.5rem)] items-center gap-1.5 rounded-xl px-2.5 py-1.5 shadow-float">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden
              className="size-3 shrink-0 text-salon-ink"
            >
              <path
                d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"
                strokeLinecap="round"
              />
            </svg>
            <span className="truncate text-[0.7rem] font-medium text-ink">
              aminata.beauty-salon.com
            </span>
          </span>
        </div>
      </div>

      {/* -------------------------------------------------- la phrase, une */}
      <p
        className="rise relative z-10 mt-5 text-[0.95rem] leading-relaxed text-muted"
        style={{ animationDelay: "500ms" }}
      >
        {t("introCourte")}
      </p>

      {/* ------------------------------------------------------ les gestes */}
      <div
        className="rise relative z-10 mt-5 grid gap-2.5"
        style={{ animationDelay: "560ms" }}
      >
        <a
          href={`${appUrl}/inscription`}
          className="salon-gradient eclat flex items-center justify-center gap-2 rounded-2xl px-6 py-4 text-base font-semibold text-white shadow-lg"
        >
          <span className="relative z-10">{c("creerSalon")}</span>
          <Fleche className="relative z-10 size-4" />
        </a>

        <a
          href="#film"
          className="verre flex items-center justify-center gap-2 rounded-2xl px-6 py-3.5 text-[0.95rem] font-medium text-ink"
        >
          <span className="grid size-5 place-items-center rounded-full bg-salon text-white">
            <svg
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden
              className="size-2.5 translate-x-px"
            >
              <path d="M8 5.2 19 12 8 18.8Z" />
            </svg>
          </span>
          {t("voirFilm")}
          <span className="tabular text-xs text-muted">{t("dureeFilm")}</span>
        </a>
      </div>

      {/* `text-muted` et non `text-subtle` : ce gris-là donne 2,69:1 sur le
          fond clair, et cette ligne est un argument, pas un ornement. */}
      <p
        className="rise relative z-10 mt-3 text-center text-[0.78rem] text-muted"
        style={{ animationDelay: "620ms" }}
      >
        {t("essai")}
      </p>
    </section>
  );
}

/**
 * Le bandeau des territoires, en défilement continu.
 *
 * Trois noms posés sur une ligne se lisent une fois et deviennent du décor.
 * Les mêmes qui glissent lentement restent une information vivante — et le
 * mouvement dit, sans l'écrire, que la plateforme tourne quelque part.
 *
 * Le contenu est répété deux fois et le défilement parcourt exactement la
 * moitié de la piste : l'image à la fin du cycle est celle du début, donc la
 * boucle ne se voit pas.
 */
export function BandeauTerritoires({ lieux }: { lieux: string[] }) {
  const t = useTranslations("site");
  const piste = useRef<HTMLDivElement>(null);
  const [anime, setAnime] = useState(false);

  useEffect(() => {
    // On n'anime que si le contenu dépasse : sur un écran large, une piste
    // qui glisse alors qu'il reste de la place se lit comme un bug.
    const noeud = piste.current;
    if (!noeud) return;
    setAnime(noeud.scrollWidth / 2 > noeud.clientWidth);
  }, []);

  return (
    <div className="pleine-largeur relative overflow-hidden border-y border-line py-3 sm:hidden">
      {/* La liste lue à voix haute : la piste au-dessus est décorative
          et défile, ce qui ne se lit pas. */}
      <p className="sr-only">
        {t("territoiresLus", { lieux: lieux.join(", ") })}
      </p>
      <div
        ref={piste}
        aria-hidden
        className={`flex w-max items-center gap-6 ${anime ? "marquee-piste" : ""}`}
      >
        {[0, 1].map((copie) => (
          <div key={copie} className="flex items-center gap-6">
            {lieux.map((lieu) => (
              <span
                key={lieu}
                className="flex shrink-0 items-center gap-2 text-[0.8rem] font-medium text-muted"
              >
                <span aria-hidden className="size-1.5 rounded-full bg-salon" />
                {lieu}
              </span>
            ))}
            <span
              aria-hidden
              className="shrink-0 text-[0.7rem] uppercase tracking-[0.14em] text-subtle"
            >
              Salons utilisateurs
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** L'adresse de la photo du haut de page, calculée une fois côté serveur. */
export function adressePhoto(id: string) {
  return illustrationUrl(id, { width: 900, ratio: 0.7 });
}
