"use client";

/**
 * Le film, en boucle, à côté des formulaires d'accès.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi une seconde version du fichier
 * ---------------------------------------------------------------------------
 *
 * Le film de la page d'accueil pèse 3 Mo : il porte une bande-son originale et
 * une définition de 1920 × 1080, parce qu'on le regarde. Ici on ne le regarde
 * pas — il tourne dans un cadre de 400 px pendant qu'on remplit un champ à
 * côté, sans le son.
 *
 * `boucle.mp4` est le même film encodé pour cet emploi-là : 960 × 540, aucune
 * piste audio, débit réduit. **391 ko au lieu de 3 Mo.** La différence n'est
 * pas cosmétique pour quelqu'un qui s'inscrit depuis un forfait mobile.
 *
 * ---------------------------------------------------------------------------
 * Il part seul, et il peut s'arrêter
 * ---------------------------------------------------------------------------
 *
 * Il n'y a **rien à cliquer pour qu'il démarre** : le film part muet dès
 * l'arrivée sur la page.
 *
 * Le réglage système « réduire les animations » ne le retient plus. Il le
 * retenait, et le résultat était pire que ce qu'il protégeait : sur un poste
 * où ce réglage est actif — c'est plus fréquent qu'on ne croit — on voyait une
 * image fixe d'agenda sans savoir qu'il y avait un film derrière.
 *
 * En contrepartie, un bouton de pause est **toujours** présent, et ce n'est
 * pas une politesse : un contenu qui bouge tout seul plus de cinq secondes à
 * côté d'autre chose doit pouvoir être arrêté — WCAG 2.2.2, niveau A. Il est
 * discret, visible sans survol (un écran tactile n'en a pas), et atteignable
 * au clavier.
 *
 * ---------------------------------------------------------------------------
 * Les deux cas où rien n'est téléchargé
 * ---------------------------------------------------------------------------
 *
 * Le mode économie de données et une connexion 2G. Ce ne sont pas des
 * préférences d'affichage : ce sont 391 ko prélevés sur un forfait compté. Un
 * bouton de lecture prend alors la place du film, et rien ne part sur le
 * réseau tant qu'on ne l'a pas touché.
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** Le fichier peut-il être téléchargé sans décider à la place de la personne ? */
function telechargementPermis() {
  if (typeof window === "undefined") return false;

  // `connection` n'existe pas partout — Safari ne l'expose pas. Son absence
  // n'est pas un refus : on ne conclut pas d'une information manquante.
  const lien = (
    navigator as Navigator & {
      connection?: { saveData?: boolean; effectiveType?: string };
    }
  ).connection;

  if (lien?.saveData) return false;
  if (lien?.effectiveType === "2g" || lien?.effectiveType === "slow-2g")
    return false;

  return true;
}

export function FilmAcces({ legende }: { legende?: string }) {
  const video = useRef<HTMLVideoElement>(null);
  /* L'état vient des événements de l'élément, jamais d'une supposition : c'est
     lui qui sait, y compris quand le navigateur l'arrête de son côté. */
  const [joue, setJoue] = useState(false);
  const [charge, setCharge] = useState(false);

  /** Pose la source si besoin, puis lance. */
  const lancer = useCallback(() => {
    const noeud = video.current;
    if (!noeud) return;

    /*
     * La source n'est posée qu'ici, et c'est le point important.
     *
     * Écrite dans le JSX, elle serait téléchargée par tout le monde — y
     * compris par ceux qu'on vient d'exclure, qui verraient l'affiche après
     * avoir payé les 391 ko. Posée au moment de jouer, le fichier n'est
     * demandé que si on a décidé de le jouer.
     */
    if (!noeud.currentSrc) noeud.src = "/film/boucle.mp4";
    noeud.muted = true;
    setCharge(true);
    void noeud.play().catch(() => {});
  }, []);

  useEffect(() => {
    if (!telechargementPermis()) return;
    lancer();

    /*
     * Un onglet qu'on quitte ne doit pas continuer à décoder des images : la
     * plupart des navigateurs le font déjà, mais pas tous, et la batterie
     * d'un téléphone d'entrée de gamme s'en ressent.
     *
     * Une pause demandée par la personne est respectée : au retour, on ne
     * relance que ce qu'on avait arrêté soi-même.
     */
    const noeud = video.current;
    const surVisibilite = () => {
      if (!noeud) return;
      if (document.visibilityState === "hidden") {
        if (!noeud.paused) noeud.dataset.reprendre = "1";
        noeud.pause();
      } else if (noeud.dataset.reprendre) {
        delete noeud.dataset.reprendre;
        void noeud.play().catch(() => {});
      }
    };
    document.addEventListener("visibilitychange", surVisibilite);
    return () =>
      document.removeEventListener("visibilitychange", surVisibilite);
  }, [lancer]);

  const basculer = useCallback(() => {
    const noeud = video.current;
    if (!noeud) return;
    if (noeud.paused) lancer();
    else noeud.pause();
  }, [lancer]);

  return (
    <figure className="m-0">
      <div className="relative overflow-hidden rounded-2xl border border-line bg-[#0e0e12] shadow-float">
        <video
          ref={video}
          className="block aspect-video w-full"
          poster="/film/affiche.jpg"
          preload="none"
          playsInline
          loop
          muted
          // `aria-hidden` : le film n'apporte aucune information qui ne soit
          // écrite ailleurs, et une vidéo décorative annoncée à un lecteur
          // d'écran n'est qu'un obstacle de plus avant le formulaire. La
          // commande, elle, reste annoncée.
          aria-hidden
          tabIndex={-1}
          onPlay={() => setJoue(true)}
          onPause={() => setJoue(false)}
        />

        {/*
          Voile de départ, quand le fichier n'a pas été téléchargé — économie
          de données ou 2G. Il occupe tout le cadre pour être facile à toucher.
        */}
        {!charge && (
          <button
            type="button"
            onClick={lancer}
            aria-label="Lancer le film de présentation, 29 secondes, sans son"
            className="group absolute inset-0 grid place-items-center bg-gradient-to-t from-black/55 via-black/10 to-black/20 transition"
          >
            <span className="grid size-14 place-items-center rounded-full bg-white/95 text-[#b4436c] shadow-[0_14px_40px_-10px_rgb(0_0_0/0.7)] transition duration-300 group-hover:scale-110">
              <Triangle className="size-6 translate-x-[2px]" />
            </span>
            <span className="absolute bottom-3 left-3 rounded-full bg-black/60 px-2.5 py-1 text-[0.66rem] font-medium text-white backdrop-blur">
              Voir le film · 29 s
            </span>
          </button>
        )}

        {/* La pastille de provenance, et la commande d'arrêt. Les deux
            n'apparaissent qu'une fois le film chargé. */}
        {charge && (
          <>
            <span className="pointer-events-none absolute bottom-2.5 left-2.5 flex items-center gap-1.5 rounded-full bg-black/55 px-2.5 py-1 text-[0.62rem] font-medium text-white backdrop-blur">
              <span
                aria-hidden
                className="size-1.5 rounded-full bg-[#d9628a]"
              />
              Le produit, en 29 s
            </span>

            <button
              type="button"
              onClick={basculer}
              aria-label={
                joue ? "Mettre le film en pause" : "Reprendre le film"
              }
              title={joue ? "Mettre en pause" : "Reprendre"}
              className="absolute bottom-2.5 right-2.5 grid size-8 place-items-center rounded-full bg-black/55 text-white/90 backdrop-blur transition hover:bg-black/75 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              {joue ? (
                <svg
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  aria-hidden
                  className="size-3.5"
                >
                  <rect x="6" y="5" width="4" height="14" rx="1" />
                  <rect x="14" y="5" width="4" height="14" rx="1" />
                </svg>
              ) : (
                <Triangle className="size-3.5 translate-x-px" />
              )}
            </button>
          </>
        )}
      </div>

      {legende && (
        <figcaption className="mt-3 text-sm leading-relaxed text-muted">
          {legende}
        </figcaption>
      )}
    </figure>
  );
}

function Triangle({ className }: { className: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
      className={className}
    >
      <path d="M8 5.2 19 12 8 18.8Z" />
    </svg>
  );
}
