"use client";

/**
 * Un ciel de particules derrière le contenu de l'accueil des mini-sites.
 *
 * Fixé à l'écran, sous tout le contenu : il habille la page en dessous du
 * haut de page, que ses photos occupent déjà. Son coût est celui d'un écran,
 * quelle que soit la longueur de la page.
 *
 * ---------------------------------------------------------------------------
 * La profondeur, sans scène 3D
 * ---------------------------------------------------------------------------
 *
 * Chaque particule porte une profondeur entre 0 (lointaine) et 1 (proche).
 * Tout en découle : une particule proche est plus grosse, plus lumineuse,
 * monte plus vite et se décale davantage quand on fait défiler la page
 * (parallaxe). Trois indices que l'œil lit comme de la profondeur — sans
 * bibliothèque 3D, sans WebGL, un simple canvas 2D.
 *
 * Le halo de chaque particule est pré-rendu une fois dans une petite image,
 * puis recopié : dessiner deux cents dégradés radiaux à chaque image coûterait
 * bien plus cher que deux cents copies.
 *
 * ---------------------------------------------------------------------------
 * Ce qui l'arrête
 * ---------------------------------------------------------------------------
 *
 * La boucle ne tourne que si le ciel est à l'écran, l'onglet visible, le
 * fond pas mis en pause, et le mouvement non réduit. Dans les autres cas, une
 * image fixe reste affichée — le décor demeure, rien ne bouge.
 *
 * Le canvas est décoratif : `aria-hidden`, jamais focalisable, et il laisse
 * passer clics et défilement (`pointer-events: none`). Si le JavaScript
 * échoue, il reste vide et transparent — la page n'en dépend pas.
 */

import { useEffect, useRef } from "react";

import { CIEL, type ZoneCiel } from "./effets";
import { useMouvementReduit, usePauseFond } from "./fondPause";

interface Etoile {
  x: number; // 0..1 de la largeur
  y: number; // 0..1 de la hauteur
  z: number; // profondeur, 0 lointaine .. 1 proche
  phase: number;
  pulsation: number;
}

interface Filante {
  x: number;
  y: number;
  dx: number;
  dy: number;
  vitesse: number; // px/s
  trainee: number; // px
  age: number;
  duree: number;
}

const entre = (a: number, b: number) => a + Math.random() * (b - a);

/** L'opacité du fondu vertical à la hauteur `y` (voir `CIEL.fondu`). */
function fondu(zone: ZoneCiel, y: number, hauteur: number): number {
  const paliers = CIEL.fondu[zone];
  const t = hauteur > 0 ? y / hauteur : 0;
  let valeur: number = paliers[paliers.length - 1][1];
  for (let i = 1; i < paliers.length; i++) {
    const [p0, a0] = paliers[i - 1];
    const [p1, a1] = paliers[i];
    if (t <= p1) {
      valeur = a0 + ((a1 - a0) * (t - p0)) / Math.max(p1 - p0, 1e-6);
      break;
    }
  }
  return valeur;
}

/** Une couleur CSS quelconque (`color-mix`, `oklch`…) ramenée en RVB. */
function enRvb(css: string): [number, number, number] {
  const toile = document.createElement("canvas");
  toile.width = toile.height = 1;
  const ctx = toile.getContext("2d", { willReadFrequently: true });
  if (!ctx) return [255, 255, 255];
  ctx.fillStyle = "#fff";
  ctx.fillStyle = css;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return [r, g, b];
}

/** Le halo d'une particule : un point net au centre, une lueur qui s'efface. */
function halo([r, g, b]: [number, number, number]): HTMLCanvasElement {
  const taille = 32;
  const toile = document.createElement("canvas");
  toile.width = toile.height = taille;
  const ctx = toile.getContext("2d");
  if (ctx) {
    const degrade = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
    degrade.addColorStop(0, `rgba(${r},${g},${b},1)`);
    degrade.addColorStop(0.22, `rgba(${r},${g},${b},0.85)`);
    degrade.addColorStop(0.45, `rgba(${r},${g},${b},0.22)`);
    degrade.addColorStop(1, `rgba(${r},${g},${b},0)`);
    ctx.fillStyle = degrade;
    ctx.fillRect(0, 0, taille, taille);
  }
  return toile;
}

export function CielEtoile({
  zone,
  className = "",
}: {
  zone: ZoneCiel;
  className?: string;
}) {
  const toile = useRef<HTMLCanvasElement>(null);
  const commande = useRef<((animer: boolean) => void) | null>(null);
  const pause = usePauseFond();
  const calme = useMouvementReduit();

  useEffect(() => {
    const canvas = toile.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    let largeur = 0;
    let hauteur = 0;
    let mobile = false;
    const etoiles: Etoile[] = [];
    let filantes: Filante[] = [];
    let couleur: [number, number, number] = [255, 255, 255];
    let intensite = 1;
    let sprite = halo(couleur);
    let temps = 0;
    let prochaineFilante = 0;
    let raf = 0;
    let dernier = 0;
    let aLEcran = false;
    let permis = false; // ni pause, ni mouvement réduit

    function nouvelleEtoile(): Etoile {
      return {
        x: Math.random(),
        y: Math.random(),
        z: Math.random() ** CIEL.profondeurExposant,
        phase: Math.random() * Math.PI * 2,
        pulsation: entre(...CIEL.scintillement),
      };
    }

    function lireTheme() {
      const style = getComputedStyle(canvas!);
      couleur = enRvb(style.color);
      intensite = Number.parseFloat(style.getPropertyValue("--ciel-intensite")) || 1;
      sprite = halo(couleur);
    }

    function dimensionner() {
      const cadre = canvas!.getBoundingClientRect();
      largeur = cadre.width;
      hauteur = cadre.height;
      mobile = largeur < CIEL.largeurMobile;
      const ratio = Math.min(
        window.devicePixelRatio || 1,
        mobile ? CIEL.ratioMax.mobile : CIEL.ratioMax.bureau,
      );
      canvas!.width = Math.max(1, Math.round(largeur * ratio));
      canvas!.height = Math.max(1, Math.round(hauteur * ratio));
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0);

      const reglage = mobile ? CIEL.densite.mobile : CIEL.densite.bureau;
      const voulu = Math.min(
        reglage.max,
        Math.max(12, Math.round((largeur * hauteur) / reglage.pixelsParEtoile)),
      );
      // On garde les particules existantes : un redimensionnement ne doit
      // pas faire « sauter » le ciel.
      while (etoiles.length < voulu) etoiles.push(nouvelleEtoile());
      etoiles.length = voulu;
    }

    function planifierFilante() {
      const [min, max] = CIEL.filantes[zone];
      prochaineFilante = temps + entre(min, max) * (mobile ? CIEL.filantes.facteurMobile : 1);
    }

    function lancerFilante() {
      const angle = (entre(...CIEL.filantes.angle) * Math.PI) / 180;
      const sens = Math.random() < 0.5 ? -1 : 1;
      filantes.push({
        x: entre(0.15, 0.85) * largeur,
        y: entre(0, 0.45) * hauteur,
        dx: Math.cos(angle) * sens,
        dy: Math.sin(angle),
        vitesse: entre(...CIEL.filantes.vitesse) * Math.max(largeur, 480),
        trainee: entre(...CIEL.filantes.trainee) * (mobile ? 0.7 : 1),
        age: 0,
        duree: entre(...CIEL.filantes.duree),
      });
    }

    function avancer(dt: number) {
      temps += dt;
      for (const e of etoiles) {
        const elan = 0.25 + 0.75 * e.z;
        e.y -= CIEL.vitesse * elan * dt;
        e.x += CIEL.vitesse * CIEL.derive * elan * dt;
        e.y -= Math.floor(e.y);
        e.x -= Math.floor(e.x);
      }
      for (const f of filantes) f.age += dt;
      filantes = filantes.filter((f) => f.age < f.duree);
      if (temps >= prochaineFilante) {
        if (prochaineFilante > 0) lancerFilante();
        planifierFilante();
      }
    }

    function dessiner() {
      ctx!.clearRect(0, 0, largeur, hauteur);
      if (!largeur || !hauteur) return;
      const decalage = window.scrollY * CIEL.parallaxe;
      const [rMin, rMax] = CIEL.rayon;
      const [oMin, oMax] = CIEL.opacite;

      for (const e of etoiles) {
        const rayon = rMin + e.z * (rMax - rMin);
        const lueur = rayon * (e.z > 0.7 ? 3.4 : 2.6);
        const px = e.x * largeur;
        let py = (e.y * hauteur - decalage * e.z) % hauteur;
        if (py < 0) py += hauteur;
        const scintille =
          1 - CIEL.scintillementAmplitude * (0.5 + 0.5 * Math.sin(e.phase + temps * e.pulsation));
        const alpha = (oMin + e.z * (oMax - oMin)) * scintille * intensite * fondu(zone, py, hauteur);
        if (alpha < 0.01) continue;
        ctx!.globalAlpha = Math.min(1, alpha);
        ctx!.drawImage(sprite, px - lueur, py - lueur, lueur * 2, lueur * 2);
      }

      const [r, g, b] = couleur;
      for (const f of filantes) {
        const vie = Math.sin((Math.PI * f.age) / f.duree) * fondu(zone, f.y, hauteur); // 0 -> 1 -> 0
        const tx = f.x + f.dx * f.vitesse * f.age;
        const ty = f.y + f.dy * f.vitesse * f.age;
        const queue = f.trainee * (0.4 + 0.6 * vie);
        const degrade = ctx!.createLinearGradient(tx, ty, tx - f.dx * queue, ty - f.dy * queue);
        degrade.addColorStop(0, `rgba(${r},${g},${b},${0.9 * vie * intensite})`);
        degrade.addColorStop(1, `rgba(${r},${g},${b},0)`);
        ctx!.globalAlpha = 1;
        ctx!.strokeStyle = degrade;
        ctx!.lineWidth = mobile ? 1 : 1.3;
        ctx!.lineCap = "round";
        ctx!.beginPath();
        ctx!.moveTo(tx, ty);
        ctx!.lineTo(tx - f.dx * queue, ty - f.dy * queue);
        ctx!.stroke();
        ctx!.globalAlpha = Math.min(1, vie * intensite);
        ctx!.drawImage(sprite, tx - 4, ty - 4, 8, 8);
      }
      ctx!.globalAlpha = 1;
    }

    function image(maintenant: number) {
      raf = requestAnimationFrame(image);
      const ips = mobile ? CIEL.imagesParSeconde.mobile : CIEL.imagesParSeconde.bureau;
      const ecart = maintenant - dernier;
      if (ecart < 1000 / ips - 2) return;
      dernier = maintenant;
      // Un onglet retrouvé après une longue absence ne doit pas faire faire
      // un bond de plusieurs minutes au ciel.
      avancer(Math.min(ecart / 1000, 0.05));
      dessiner();
    }

    function actualiser() {
      const tourner = aLEcran && permis && !document.hidden;
      if (tourner && !raf) {
        dernier = performance.now();
        raf = requestAnimationFrame(image);
      } else if (!tourner && raf) {
        cancelAnimationFrame(raf);
        raf = 0;
        // L'arrêt laisse une image nette : pas d'étoile filante figée en
        // plein vol.
        filantes = [];
        dessiner();
      }
    }

    lireTheme();
    dimensionner();
    planifierFilante();
    dessiner();
    canvas.dataset.pret = "";

    const surVisibilite = () => actualiser();
    document.addEventListener("visibilitychange", surVisibilite);

    /*
     * Ce qu'on observe, c'est le contenu que le ciel habille (le parent du
     * canvas), pas le canvas : fixé à l'écran, celui-ci y est toujours. Le
     * ciel s'arrête dès que ce contenu n'est plus visible.
     */
    const ecran = new IntersectionObserver(([entree]) => {
      aLEcran = entree.isIntersecting;
      actualiser();
    });
    ecran.observe(canvas.parentElement ?? canvas);

    const taille = new ResizeObserver(() => {
      dimensionner();
      if (!raf) dessiner();
    });
    taille.observe(canvas);

    // Le mode clair/sombre change les couleurs : on les relit.
    const racine = canvas.closest("[data-mode]");
    const mode = new MutationObserver(() => {
      lireTheme();
      if (!raf) dessiner();
    });
    if (racine) mode.observe(racine, { attributes: true, attributeFilter: ["data-mode"] });

    commande.current = (animer: boolean) => {
      permis = animer;
      actualiser();
    };

    return () => {
      commande.current = null;
      cancelAnimationFrame(raf);
      raf = 0;
      document.removeEventListener("visibilitychange", surVisibilite);
      ecran.disconnect();
      taille.disconnect();
      mode.disconnect();
    };
  }, [zone]);

  useEffect(() => {
    commande.current?.(!pause && !calme);
  }, [pause, calme]);

  return (
    <canvas
      ref={toile}
      aria-hidden
      className={`ciel ciel--${zone} pointer-events-none ${className}`}
    />
  );
}
