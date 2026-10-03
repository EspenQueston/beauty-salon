"use client";

/**
 * Le film de présentation, sur la page d'accueil.
 *
 * ---------------------------------------------------------------------------
 * Il part tout seul, et il part muet — ce n'est pas un choix
 * ---------------------------------------------------------------------------
 *
 * Le film démarre quand la section arrive à l'écran, pour qu'on n'ait rien à
 * cliquer. Mais aucun navigateur n'autorise une lecture automatique **avec le
 * son** : Chrome, Safari et Firefox rejettent la promesse rendue par `play()`
 * dès que la piste audio est active et qu'aucun geste n'a précédé. La seule
 * lecture automatique qui existe est une lecture muette.
 *
 * Or la musique est la moitié de ce film. D'où la forme retenue : l'image
 * part seule, et un bouton « Activer le son » attend par-dessus. Un seul
 * clic, qui vaut geste, et le son s'ouvre sans interrompre l'image.
 *
 * ---------------------------------------------------------------------------
 * Les trois cas où l'on ne démarre pas
 * ---------------------------------------------------------------------------
 *
 * Le fichier pèse trois mégaoctets, et les personnes qu'on vise ouvrent cette
 * page depuis un téléphone d'entrée de gamme, souvent sur un forfait où le
 * mégaoctet se compte. Dépenser trois mégaoctets sans qu'on ait rien demandé
 * n'est acceptable que si la connexion peut les absorber.
 *
 *   - `prefers-reduced-motion` — une image qui bouge toute seule pendant
 *     vingt-neuf secondes est exactement ce que ce réglage demande d'éviter ;
 *   - `saveData` — la personne a explicitement demandé à son navigateur
 *     d'économiser ses données. Passer outre serait lui mentir ;
 *   - une connexion `2g` ou `slow-2g` — le film arriverait par saccades, ce
 *     qui est pire que pas de film.
 *
 * Dans ces trois cas l'affiche et son bouton restent : rien n'est perdu, il
 * faut seulement un clic.
 *
 * ---------------------------------------------------------------------------
 * Ce qui se passe quand on quitte la section
 * ---------------------------------------------------------------------------
 *
 * Le film se met en pause. Une vidéo qui continue hors champ consomme du
 * réseau et de la batterie pour une image que personne ne regarde — et si le
 * son a été activé, elle parle à un écran vide.
 *
 * Elle reprend au retour, **sauf si la personne l'a mise en pause elle-même**.
 * Une pause manuelle est une décision ; la reprendre de force au premier
 * défilement serait reprendre la main sur quelqu'un qui vient de la demander.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { Relief } from "@/features/ui/Relief";

/** Ce que le film montre, dans l'ordre. Sert de légende et de sommaire. */
const MOMENTS = [
  /* L'horodatage ne se traduit pas ; le repère, si. */
  { t: "00:00", cle: "demandes" },
  { t: "00:07", cle: "promesse" },
  { t: "00:11", cle: "outils" },
  { t: "00:24", cle: "double" },
];

/** La lecture automatique est-elle acceptable ici et maintenant ? */
function departAutomatiquePermis() {
  if (typeof window === "undefined") return false;

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    return false;

  // `connection` n'existe pas partout — Safari ne l'expose pas. Son absence
  // n'est pas un refus : on ne peut pas conclure d'une information manquante.
  const lien = (
    navigator as Navigator & {
      connection?: { saveData?: boolean; effectiveType?: string };
    }
  ).connection;

  if (lien?.saveData) return false;
  if (lien?.effectiveType === "2g" || lien?.effectiveType === "slow-2g") {
    return false;
  }

  return true;
}

export function Film() {
  const t = useTranslations("site");
  const video = useRef<HTMLVideoElement>(null);
  const cadre = useRef<HTMLDivElement>(null);

  const [demarre, setDemarre] = useState(false);
  const [muet, setMuet] = useState(true);

  /*
   * Deux `ref` que l'observateur lit sans être reconstruit.
   *
   * L'observateur d'intersection est créé une fois pour toutes. S'il
   * dépendait de `muet` ou d'un état de pause, il serait détruit et recréé à
   * chaque changement — et un observateur recréé rappelle immédiatement son
   * callback avec l'état courant, donc relancerait le film que la personne
   * vient de mettre en pause.
   */
  const pauseVoulue = useRef(false);
  const muetRef = useRef(true);

  useEffect(() => {
    muetRef.current = muet;
  }, [muet]);

  /** Lance la lecture, avec ou sans son, et note ce que le navigateur répond. */
  const lancer = useCallback((avecSon: boolean) => {
    const noeud = video.current;
    if (!noeud) return;

    // `muted` est posé sur l'élément et non par une propriété JSX : React ne
    // rend pas cet attribut côté serveur, et la valeur doit être juste avant
    // l'appel à `play()`, sinon le navigateur refuse la lecture.
    noeud.muted = !avecSon;
    muetRef.current = !avecSon;
    setMuet(!avecSon);
    pauseVoulue.current = false;

    void noeud.play().then(
      () => setDemarre(true),
      () => {
        /*
         * Refus du navigateur. S'il s'agissait d'une tentative avec le son,
         * on retombe sur une lecture muette : l'image vaut mieux que
         * l'affiche, et le bouton « Activer le son » sera là.
         *
         * Le cas arrive pour de bon — une page ouverte directement sur
         * /#film n'a été précédée d'aucun geste.
         */
        if (!avecSon) {
          setDemarre(false);
          return;
        }
        noeud.muted = true;
        muetRef.current = true;
        setMuet(true);
        void noeud.play().then(
          () => setDemarre(true),
          () => setDemarre(false),
        );
      },
    );
  }, []);

  /*
   * « Voir le film », dans le haut de page, mène ici par une ancre.
   *
   * Quelqu'un qui clique ce bouton-là veut le film **avec** le son : on ne
   * peut pas se contenter de le laisser arriver et démarrer muet comme un
   * simple passage. Le clic ouvre une fenêtre d'activation de quelques
   * secondes, pendant laquelle le navigateur accepte encore une lecture
   * sonore — et s'il refuse, le repli ci-dessus prend le relais.
   */
  useEffect(() => {
    const surAncre = () => {
      if (window.location.hash === "#film") lancer(true);
    };
    surAncre();
    window.addEventListener("hashchange", surAncre);
    return () => window.removeEventListener("hashchange", surAncre);
  }, [lancer]);

  /* --------------------------------------------------- départ à l'approche */
  useEffect(() => {
    const bloc = cadre.current;
    const noeud = video.current;
    if (!bloc || !noeud) return;
    if (typeof IntersectionObserver === "undefined") return;
    if (!departAutomatiquePermis()) return;

    // Premier observateur : mise en mémoire tampon un peu avant que la
    // section n'arrive, pour que l'image parte sans temps mort. Il se retire
    // dès qu'il a servi.
    const prechargement = new IntersectionObserver(
      (entrees) => {
        if (!entrees.some((e) => e.isIntersecting)) return;
        // `load()` réinitialise l'élément : sur une vidéo déjà partie il la
        // coupe et la ramène à zéro. Le cas arrive quand on entre par
        // l'ancre, où la lecture précède ce déclenchement.
        if (noeud.readyState === 0 && noeud.paused) {
          noeud.preload = "auto";
          noeud.load();
        }
        prechargement.disconnect();
      },
      { rootMargin: "700px 0px" },
    );
    prechargement.observe(bloc);

    // Second observateur : il vit tant que la page vit, puisqu'il sert aussi
    // à mettre en pause quand la section sort du champ.
    const lecture = new IntersectionObserver(
      (entrees) => {
        for (const entree of entrees) {
          if (entree.isIntersecting) {
            if (noeud.paused && !noeud.ended && !pauseVoulue.current) {
              noeud.muted = muetRef.current;
              void noeud.play().then(
                () => setDemarre(true),
                () => setDemarre(false),
              );
            }
          } else if (!noeud.paused) {
            // Sortie du champ : pause technique. On ne touche pas à
            // `pauseVoulue`, qui n'enregistre que les pauses de la personne.
            noeud.pause();
          }
        }
      },
      // 45 % du cadre visible : le film part quand la section est vraiment
      // regardée, pas quand son premier pixel effleure le bas de l'écran.
      { threshold: 0.45 },
    );
    lecture.observe(bloc);

    return () => {
      prechargement.disconnect();
      lecture.disconnect();
    };
  }, []);

  /* ------------------------------------------------- pauses de la personne */
  /*
   * `onPause` se déclenche aussi pour nos propres pauses de sortie de champ.
   * On ne peut pas les distinguer depuis l'événement : on marque donc la
   * pause comme voulue dans tous les cas **sauf** quand le cadre est hors de
   * l'écran, cas où c'est nous qui venons d'agir.
   */
  const surPause = useCallback(() => {
    const noeud = video.current;
    const bloc = cadre.current;
    if (!noeud || !bloc) return;
    if (noeud.ended) return; // Une pause à la fin du film n'est pas une pause.

    const r = bloc.getBoundingClientRect();
    const visible =
      r.bottom > window.innerHeight * 0.15 && r.top < window.innerHeight * 0.85;

    if (visible) pauseVoulue.current = true;
  }, []);

  const basculerSon = useCallback(() => {
    const noeud = video.current;
    if (!noeud) return;
    const prochain = !noeud.muted;
    noeud.muted = prochain;
    muetRef.current = prochain;
    setMuet(prochain);
    // Activer le son est un geste : si le film s'était arrêté, il repart.
    if (!prochain && noeud.paused) {
      pauseVoulue.current = false;
      void noeud.play().catch(() => {});
    }
  }, []);

  // Pas de reflet : le cadre porte `.lisere`, dont l'anneau vit sur le même
  // `::after` — et un reflet blanc sur une image vidéo n'apporterait rien.
  return (
    <Relief force={0.45} reflet={false} className="w-full">
      <div
        ref={cadre}
        className="lisere relative overflow-hidden rounded-3xl border border-line bg-[#0e0e12] shadow-float"
      >
        <video
          ref={video}
          className="block aspect-video w-full"
          src="/film/beauty-salon.mp4"
          poster="/film/affiche.jpg"
          preload="none"
          playsInline
          controls={demarre}
          onPlay={() => setDemarre(true)}
          onPause={surPause}
          onEnded={() => {
            pauseVoulue.current = false;
            setDemarre(false);
          }}
        >
          {/*
            Un repli en texte pour les navigateurs sans <video>, et pour les
            lecteurs d'écran qui annoncent l'élément : le film n'apporte
            aucune information qui ne soit ailleurs dans la page.
          */}
          {t("filmSecours")}{" "}
          <a href="/film/beauty-salon.mp4">{t("film.telecharger")}</a>
        </video>

        {/* La couche de départ : elle reste tant que rien ne joue — au premier
            affichage, après un refus du navigateur, et à la fin du film. */}
        {!demarre && (
          <button
            type="button"
            onClick={() => lancer(true)}
            aria-label={t("film.lancer")}
            className="group absolute inset-0 grid place-items-center bg-gradient-to-t from-black/55 via-black/10 to-black/25 transition"
          >
            <span className="couche-3 relative grid size-20 place-items-center rounded-full bg-white/95 text-[#b4436c] shadow-[0_18px_50px_-12px_rgb(0_0_0/0.7)] transition duration-300 group-hover:scale-110 sm:size-24">
              <span
                aria-hidden
                className="pouls absolute inset-0 rounded-full bg-white/70"
              />
              <svg
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden
                className="relative size-7 translate-x-[2px] sm:size-9"
              >
                <path d="M8 5.2 19 12 8 18.8Z" />
              </svg>
            </span>

            <span className="couche-2 absolute bottom-3 left-3 flex items-center gap-2 rounded-full bg-black/55 px-3 py-1.5 text-[0.7rem] font-medium text-white backdrop-blur sm:bottom-5 sm:left-5 sm:text-xs">
              <span
                aria-hidden
                className="size-1.5 rounded-full bg-[#d9628a]"
              />
              29 s · son original
            </span>
          </button>
        )}

        {/*
          Le bouton de son, pendant la lecture muette.

          En haut à droite, et pas en bas : la barre de commandes native occupe
          le bas de l'image dès que le film joue, et deux commandes superposées
          finissent par se manquer au doigt.
        */}
        {demarre && muet && (
          <button
            type="button"
            onClick={basculerSon}
            className="absolute right-3 top-3 z-10 inline-flex items-center gap-2 rounded-full bg-black/65 py-2 pl-2.5 pr-3.5 text-[0.72rem] font-semibold text-white shadow-lg backdrop-blur transition hover:bg-black/80 sm:right-5 sm:top-5 sm:text-sm"
          >
            <span className="relative grid size-6 shrink-0 place-items-center rounded-full bg-white/95 text-[#b4436c] sm:size-7">
              <span
                aria-hidden
                className="pouls absolute inset-0 rounded-full bg-white/70"
              />
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
                className="relative size-3.5 sm:size-4"
              >
                <path d="M11 5 6.5 9H3v6h3.5L11 19Z" />
                <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
              </svg>
            </span>
            Activer le son
          </button>
        )}

        {/* Une fois le son ouvert, le bouton devient discret : il ne sert plus
            qu'à le refermer, ce qui est rare. */}
        {demarre && !muet && (
          <button
            type="button"
            onClick={basculerSon}
            aria-label={t("film.couper")}
            className="absolute right-3 top-3 z-10 grid size-9 place-items-center rounded-full bg-black/55 text-white/90 backdrop-blur transition hover:bg-black/75 sm:right-5 sm:top-5"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
              className="size-4"
            >
              <path d="M11 5 6.5 9H3v6h3.5L11 19Z" />
              <path d="m16 9 5 6M21 9l-5 6" />
            </svg>
          </button>
        )}
      </div>

      {/*
        Le sommaire sous l'image. Deux colonnes dès le téléphone : quatre
        repères en pile feraient défiler pour une information qui tient en
        un coup d'œil.
      */}
      <ol className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        {MOMENTS.map((moment) => (
          <li
            key={moment.t}
            className="verre rounded-xl px-3 py-2.5 sm:px-4 sm:py-3"
          >
            <span className="tabular block text-[0.68rem] font-semibold text-salon-ink sm:text-xs">
              {moment.t}
            </span>
            <span className="mt-0.5 block text-[0.72rem] leading-snug text-muted sm:text-[0.8rem]">
              {t(`film.chapitres.${moment.cle}`)}
            </span>
          </li>
        ))}
      </ol>
    </Relief>
  );
}
