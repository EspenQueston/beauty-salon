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

export function HautMobile() {
  const t = useTranslations("accueil");
  const c = useTranslations("commun");
  const film = useTranslations("site.film");
  const video = useRef<HTMLVideoElement>(null);
  const [muet, setMuet] = useState(true);
  const [enLecture, setEnLecture] = useState(false);
  /* Les métiers et la promesse sont des listes : leur nombre peut différer
     d'une langue à l'autre, et rien dans la mise en page n'en dépend. */
  const metiers = t.raw("metiers") as string[];
  const promesse = t.raw("promesse") as string[];

  useEffect(() => {
    const noeud = video.current;
    if (!noeud) return;
    noeud.defaultMuted = true;
    noeud.muted = true;
    const lien = (navigator as Navigator & {
      connection?: { saveData?: boolean; effectiveType?: string };
    }).connection;
    if (
      window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
      lien?.saveData ||
      lien?.effectiveType === "2g" ||
      lien?.effectiveType === "slow-2g"
    ) return;

    // A fresh mount (including a page refresh) starts at the beginning.
    noeud.currentTime = 0;
    void noeud.play().then(() => setEnLecture(true), () => setEnLecture(false));

    if (typeof IntersectionObserver === "undefined") return;
    const observateur = new IntersectionObserver(([entree]) => {
      if (!entree?.isIntersecting) noeud.pause();
      else if (noeud.paused) void noeud.play().catch(() => {});
    }, { threshold: 0.15 });
    observateur.observe(noeud);
    return () => observateur.disconnect();
  }, []);

  function basculerSon() {
    const noeud = video.current;
    if (!noeud) return;
    noeud.muted = !noeud.muted;
    setMuet(noeud.muted);
    if (noeud.paused) void noeud.play().catch(() => {});
  }

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

      {/* Le film remplace la photo : lecture muette automatique, son sur geste. */}
      <div
        className="rise relative z-10 mx-1 mt-7"
        style={{ animationDelay: "420ms" }}
      >
        <div className="lisere relative overflow-hidden rounded-3xl border border-line bg-[#0e0e12] shadow-float">
          <video
            ref={video}
            src="/film/beauty-salon.mp4"
            poster="/film/affiche.jpg"
            preload="metadata"
            playsInline
            loop
            onPlay={() => setEnLecture(true)}
            onPause={() => setEnLecture(false)}
            className="block aspect-video w-full object-cover"
            aria-label={film("lancerMuet")}
          />
          {/* Un voile en bas : il n'est là que pour asseoir les deux pastilles,
              pas pour porter du texte. */}
          <div
            aria-hidden
            className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/45 to-transparent"
          />

          {!enLecture && (
            <button type="button" onClick={() => {
              video.current?.play().catch(() => {});
            }} aria-label={film("lancerMuet")}
              className="absolute inset-0 grid place-items-center bg-black/25 text-white">
              <span className="grid size-14 place-items-center rounded-full bg-white/90 text-salon shadow-lg" aria-hidden>▶</span>
            </button>
          )}
          <button type="button" onClick={basculerSon}
            aria-label={muet ? film("activer") : film("couper")}
            className="absolute bottom-3 right-3 z-10 rounded-full bg-black/70 px-3 py-2 text-xs font-semibold text-white backdrop-blur-sm active:scale-95">
            {muet ? film("activer") : film("couper")}
          </button>
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
          className="salon-gradient eclat mobile-cta flex items-center justify-center gap-2 rounded-2xl px-6 py-4 text-base font-semibold text-white shadow-lg"
        >
          <span className="relative z-10">{c("creerSalon")}</span>
          <Fleche className="relative z-10 size-4" />
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
  const accueil = useTranslations("accueil");
  const [arrete, setArrete] = useState(false);

  return (
    <div className="marquee relative overflow-hidden border-y border-line bg-surface/70 py-3.5 backdrop-blur-sm">
      {/* La liste lue à voix haute : la piste au-dessus est décorative
          et défile, ce qui ne se lit pas. */}
      <p className="sr-only">
        {t("territoiresLus", { lieux: lieux.join(", ") })}
      </p>
      <div aria-hidden className="marquee-piste items-center" data-arretee={arrete ? "" : undefined}>
        {[0, 1].map((copie) => (
          <div key={copie} className="flex shrink-0 items-center gap-6 pr-6 sm:gap-10 sm:pr-10">
            {lieux.map((lieu) => (
              <span
                key={lieu}
                className="flex shrink-0 items-center gap-2 text-xs font-medium text-muted sm:text-sm"
              >
                <span aria-hidden className="size-1.5 rounded-full bg-salon" />
                {lieu}
              </span>
            ))}
            <span
              aria-hidden
              className="shrink-0 text-[0.7rem] uppercase tracking-[0.14em] text-subtle"
            >
              {accueil("utilisePar")}
            </span>
          </div>
        ))}
      </div>
      <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-surface via-surface/80 to-transparent sm:w-24" />
      <button
        type="button"
        onClick={() => setArrete((value) => !value)}
        aria-label={arrete ? t("territoiresReprendre") : t("territoiresPause")}
        className="absolute right-2 top-1/2 z-10 grid size-8 -translate-y-1/2 place-items-center rounded-full border border-line bg-surface text-xs text-ink shadow-sm transition hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-salon sm:right-5"
      >
        <span aria-hidden="true">{arrete ? "▶" : "Ⅱ"}</span>
      </button>
    </div>
  );
}

/** L'adresse de la photo du haut de page, calculée une fois côté serveur. */
export function adressePhoto(id: string) {
  return illustrationUrl(id, { width: 900, ratio: 0.7 });
}
