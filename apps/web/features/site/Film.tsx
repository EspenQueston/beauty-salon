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
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { Relief } from "@/features/ui/Relief";

/*
 * ---------------------------------------------------------------------------
 * Deux films, un par thème
 * ---------------------------------------------------------------------------
 *
 * En mode sombre, le film d'origine, sur fond noir. En mode clair, le second
 * film, tourné sur fond blanc et rose : le film sombre au milieu d'une page
 * claire faisait un trou noir dans le haut de page. Chacun a ses chapitres —
 * ils décrivent ce qu'on voit, et les deux films ne montrent pas la même chose
 * au même moment.
 *
 * Deux définitions par film, choisies au moment de charger : 720p pour un
 * écran qui l'affiche vraiment (cadre × densité de pixels), 540p sinon, ou sur
 * une connexion lente. Toutes pèsent moins de la moitié de l'ancien fichier
 * 1080p (3 Mo), sans différence visible sur ces images d'interface.
 */
type Mode = "clair" | "sombre";

const FILMS: Record<Mode, { base: string; moments: { t: string; cle: string }[] }> = {
  sombre: {
    base: "/film/sombre",
    moments: [
      /* L'horodatage ne se traduit pas ; le repère, si. */
      { t: "00:00", cle: "demandes" },
      { t: "00:07", cle: "promesse" },
      { t: "00:11", cle: "outils" },
      { t: "00:24", cle: "double" },
    ],
  },
  clair: {
    base: "/film/clair",
    moments: [
      { t: "00:00", cle: "accumulent" },
      { t: "00:03", cle: "miniSite" },
      { t: "00:06", cle: "reservent" },
      { t: "00:10", cle: "acompte" },
      { t: "00:14", cle: "agenda" },
      { t: "00:23", cle: "essai" },
    ],
  },
};

/** Le thème réellement affiché : choix de la personne, sinon celui de l'appareil. */
function modeAffiche(): Mode {
  const choix = document.documentElement.dataset.theme;
  if (choix === "light") return "clair";
  if (choix === "dark") return "sombre";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "clair" : "sombre";
}

function suivreLeMode(rappel: () => void) {
  const observateur = new MutationObserver(rappel);
  observateur.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  const media = window.matchMedia("(prefers-color-scheme: light)");
  media.addEventListener("change", rappel);
  return () => {
    observateur.disconnect();
    media.removeEventListener("change", rappel);
  };
}

/*
 * Le film attend que la page ait fini de charger, et que le navigateur
 * souffle, avant de télécharger quoi que ce soit.
 *
 * Il est dans le haut de page : l'observateur le voyait à l'écran dès le
 * premier rendu, et son mégaoctet partait en même temps que les polices et
 * les scripts — sur un téléphone en 4G, c'est lui qui retardait l'affichage
 * de tout le reste. Un clic sur « lecture » n'attend pas, lui.
 */
function apresLeChargement(rappel: () => void): () => void {
  let annule = false;
  let minuteur: ReturnType<typeof setTimeout> | undefined;
  const lancer = () => {
    if (annule) return;
    const fenetre = window as Window & {
      requestIdleCallback?: (f: () => void, o?: { timeout: number }) => number;
    };
    if (fenetre.requestIdleCallback) fenetre.requestIdleCallback(() => !annule && rappel(), { timeout: 2500 });
    // Safari n'a pas `requestIdleCallback` : un court délai après `load`.
    else minuteur = setTimeout(() => !annule && rappel(), 600);
  };
  if (document.readyState === "complete") lancer();
  else window.addEventListener("load", lancer, { once: true });
  return () => {
    annule = true;
    if (minuteur) clearTimeout(minuteur);
    window.removeEventListener("load", lancer);
  };
}

/** 720p si l'écran l'affiche et que la connexion le permet ; 540p sinon. */
function definition(cadre: HTMLElement | null): 540 | 720 {
  const lien = (
    navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }
  ).connection;
  if (lien?.saveData || lien?.effectiveType === "3g") return 540;
  const largeur = (cadre?.clientWidth || window.innerWidth) * (window.devicePixelRatio || 1);
  return largeur > 900 ? 720 : 540;
}

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
  // Côté serveur, le thème n'est pas connu : sombre, celui par défaut.
  // L'affiche, elle, suit le thème dès le premier pixel (`.film-affiche`).
  const mode = useSyncExternalStore(suivreLeMode, modeAffiche, () => "sombre" as Mode);
  const MOMENTS = FILMS[mode].moments;

  const [demarre, setDemarre] = useState(false);
  const [muet, setMuet] = useState(true);
  const [position, setPosition] = useState(0);
  const [duree, setDuree] = useState(29);
  const pauseTechnique = useRef(false);
  const chapitre = Math.max(0, MOMENTS.findLastIndex(moment => Number(moment.t.slice(3)) <= position));

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

  /*
   * La source, posée à la main et non dans le JSX : elle dépend de l'écran et
   * du thème, inconnus côté serveur, et un `src` différent entre le serveur
   * et le navigateur casserait l'hydratation. Elle est posée juste avant toute
   * lecture ou mise en mémoire tampon.
   */
  const assurerSource = useCallback(() => {
    const noeud = video.current;
    if (!noeud) return;
    const voulue = `${FILMS[modeAffiche()].base}-${definition(cadre.current)}.mp4`;
    if (!noeud.src.endsWith(voulue)) noeud.src = voulue;
  }, []);

  // Changer de thème change de film : on revient à l'affiche, sans rien
  // relancer à la place de la personne.
  const modePrecedent = useRef(mode);
  useLayoutEffect(() => {
    if (modePrecedent.current === mode) return;
    modePrecedent.current = mode;
    const noeud = video.current;
    if (!noeud) return;
    if (!noeud.paused) pauseTechnique.current = true;
    noeud.pause();
    noeud.removeAttribute("src");
    noeud.load();
    setDemarre(false);
    setPosition(0);
  }, [mode]);

  /** Lance la lecture, avec ou sans son, et note ce que le navigateur répond. */
  const lancer = useCallback((avecSon: boolean) => {
    const noeud = video.current;
    if (!noeud) return;

    // `muted` est posé sur l'élément et non par une propriété JSX : React ne
    // rend pas cet attribut côté serveur, et la valeur doit être juste avant
    // l'appel à `play()`, sinon le navigateur refuse la lecture.
    assurerSource();
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
  }, [assurerSource]);

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
    const automatique = departAutomatiquePermis();
    let prechargement: IntersectionObserver | undefined;
    let lecture: IntersectionObserver | undefined;
    const masquer = () => {
      if (document.hidden && !noeud.paused) {
        pauseTechnique.current = true;
        noeud.pause();
      }
    };
    document.addEventListener("visibilitychange", masquer);

    const annulerAttente = apresLeChargement(() => {

    // Premier observateur : mise en mémoire tampon un peu avant que la
    // section n'arrive, pour que l'image parte sans temps mort. Il se retire
    // dès qu'il a servi.
    prechargement = new IntersectionObserver(
      (entrees) => {
        if (!automatique || !entrees.some((e) => e.isIntersecting)) return;
        // `load()` réinitialise l'élément : sur une vidéo déjà partie il la
        // coupe et la ramène à zéro. Le cas arrive quand on entre par
        // l'ancre, où la lecture précède ce déclenchement.
        if (noeud.readyState === 0 && noeud.paused) {
          assurerSource();
          noeud.preload = "auto";
          noeud.load();
        }
        prechargement?.disconnect();
      },
      { rootMargin: "700px 0px" },
    );
    prechargement.observe(bloc);

    // Second observateur : il vit tant que la page vit, puisqu'il sert aussi
    // à mettre en pause quand la section sort du champ.
    lecture = new IntersectionObserver(
      (entrees) => {
        for (const entree of entrees) {
          if (entree.isIntersecting) {
            if (automatique && noeud.paused && !noeud.ended && !pauseVoulue.current && !document.hidden) {
              assurerSource();
              noeud.muted = muetRef.current;
              void noeud.play().then(
                () => setDemarre(true),
                () => setDemarre(false),
              );
            }
          } else if (!noeud.paused) {
            // Sortie du champ : pause technique. On ne touche pas à
            // `pauseVoulue`, qui n'enregistre que les pauses de la personne.
            pauseTechnique.current = true;
            noeud.pause();
          }
        }
      },
      // 45 % du cadre visible : le film part quand la section est vraiment
      // regardée, pas quand son premier pixel effleure le bas de l'écran.
      { threshold: 0.45 },
    );
    lecture.observe(bloc);
    });

    return () => {
      annulerAttente();
      prechargement?.disconnect();
      lecture?.disconnect();
      document.removeEventListener("visibilitychange", masquer);
    };
  }, [assurerSource]);

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
    if (pauseTechnique.current) {
      pauseTechnique.current = false;
      return;
    }

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
          preload="none"
          playsInline
          muted={muet}
          controls={demarre}
          onTimeUpdate={event => setPosition(event.currentTarget.currentTime)}
          onLoadedMetadata={event => {
            const length = event.currentTarget.duration;
            if (Number.isFinite(length) && length > 0) setDuree(length);
          }}
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
          <a href={`${FILMS[mode].base}-720.mp4`}>
            {t("film.telecharger", { poids: mode === "clair" ? 1.3 : 0.8 })}
          </a>
        </video>

        {/* L'affiche : un fond CSS qui suit le thème avant même React — une
            seule image téléchargée —, posé sur l'image tant que rien ne joue. */}
        {!demarre && <div aria-hidden className="film-affiche absolute inset-0" />}

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
              29 s · {t("film.originalSound")}
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
            {t("film.activer")}
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
      <div className="mt-3 flex min-w-0 items-center gap-3 px-1">
        <button type="button" aria-label={t("film.previous")} disabled={chapitre===0} onClick={() => {
          const node=video.current;
          if (node) { node.currentTime=Number(MOMENTS[chapitre-1].t.slice(3)); lancer(!muetRef.current); }
        }} className="grid size-11 shrink-0 place-items-center rounded-full border border-line text-ink transition hover:bg-salon-soft disabled:opacity-40">←</button>
        <input type="range" min={0} max={duree} step={0.1} value={Math.min(position,duree)} aria-label={t("film.timeline")} onChange={event => {
          const time=Number(event.target.value);
          setPosition(time);
          if (video.current) video.current.currentTime=time;
        }} className="h-11 min-w-0 flex-1 cursor-pointer accent-[var(--salon-primary)]" />
        <button type="button" aria-label={t("film.next")} disabled={chapitre===MOMENTS.length-1} onClick={() => {
          const node=video.current;
          if (node) { node.currentTime=Number(MOMENTS[chapitre+1].t.slice(3)); lancer(!muetRef.current); }
        }} className="grid size-11 shrink-0 place-items-center rounded-full border border-line text-ink transition hover:bg-salon-soft disabled:opacity-40">→</button>
      </div>
      <ol className="mt-2 grid grid-cols-2 gap-2 sm:gap-3">
        {MOMENTS.map((moment,index) => (
          <li
            key={moment.t}
            className="min-w-0"
          >
            <button type="button" aria-pressed={chapitre===index} onClick={() => {
              if (video.current) video.current.currentTime=Number(moment.t.slice(3));
              lancer(!muetRef.current);
            }} className={`film-chapter min-h-11 w-full rounded-xl border px-3 py-2 text-left transition duration-300 ${chapitre===index?"border-salon/60 bg-salon-soft shadow-sm":"border-line bg-surface/60 hover:bg-salon-soft"}`}>
            <span className="tabular block text-[0.68rem] font-semibold text-salon-ink sm:text-xs">
              {moment.t}
            </span>
            <span className="mt-0.5 block text-[0.72rem] leading-snug text-muted sm:text-[0.8rem]">
              {t(`film.chapitres.${moment.cle}`)}
            </span>
            </button>
          </li>
        ))}
      </ol>
    </Relief>
  );
}
