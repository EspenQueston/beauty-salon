"use client";

/**
 * Le panneau de réglages de l'espace.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'il règle, et ce qu'il ne règle pas
 * ---------------------------------------------------------------------------
 *
 * Uniquement l'apparence de la coquille : la couleur d'accent de la
 * navigation, son fond, si la barre du haut suit le défilement, le thème
 * clair ou sombre, et si la colonne est visible.
 *
 * Rien de ce qui touche au salon — son nom, ses horaires, ses prix — n'a sa
 * place ici. Ces réglages-là engagent les clientes et vivent sur le serveur ;
 * ceux-ci n'engagent que l'écran de la personne devant le clavier.
 *
 * ---------------------------------------------------------------------------
 * Où vivent ces préférences
 * ---------------------------------------------------------------------------
 *
 * Dans `localStorage`, comme le thème, et pour la même raison : elles
 * dépendent de l'écran et du moment, pas du compte. La même gérante veut sa
 * colonne repliée sur le portable du salon et dépliée sur son grand écran du
 * bureau — les stocker côté serveur imposerait un seul choix aux deux.
 *
 * Le magasin est exposé par `useSyncExternalStore` plutôt que par un
 * contexte : il vit hors de React, et un `useEffect` qui lirait le stockage
 * au montage provoquerait un second rendu à chaque changement de page.
 */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { Toggle } from "@/features/ui";
import { setTheme, useThemeChoice } from "@/features/ui/ThemeToggle";
import { Icon } from "./icons";

/* --------------------------------------------------------------------------
 * Les préférences
 * ---------------------------------------------------------------------- */

export type NavType = "dark" | "transparent" | "light";
export type AccentName =
  | "salon"
  | "graphite"
  | "azur"
  | "emeraude"
  | "ambre"
  | "grenat";

export interface ShellPrefs {
  accent: AccentName;
  navType: NavType;
  /** La barre du haut reste en place quand le contenu défile. */
  navbarFixed: boolean;
  /** Colonne de navigation masquée sur grand écran. */
  sidebarHidden: boolean;
}

const KEY = "beauty-salon-shell";

const DEFAULTS: ShellPrefs = {
  accent: "salon",
  navType: "dark",
  navbarFixed: true,
  sidebarHidden: false,
};

/**
 * Six accents, et le premier est celui du salon.
 *
 * Mettre la couleur de la boutique en tête n'est pas une politesse : c'est
 * le réglage par défaut, et le seul qui relie la navigation au mini-site que
 * les clientes voient. Les cinq autres existent pour qui gère deux salons
 * dans deux onglets et veut les distinguer d'un coup d'œil.
 */
export const ACCENTS: Record<AccentName, { label: string; color: string }> = {
  salon: { label: "Couleur du salon", color: "var(--salon-primary)" },
  graphite: { label: "Graphite", color: "#42424a" },
  azur: { label: "Azur", color: "#1a73e8" },
  emeraude: { label: "Émeraude", color: "#43a047" },
  ambre: { label: "Ambre", color: "#fb8c00" },
  grenat: { label: "Grenat", color: "#e53935" },
};

export function accentGradient(accent: AccentName): string {
  const color = ACCENTS[accent].color;
  return `linear-gradient(195deg, color-mix(in srgb, ${color} 70%, white) 0%, ${color} 100%)`;
}

/**
 * L'accent, repeint sur **tout** l'espace et pas seulement sur la colonne.
 *
 * ---------------------------------------------------------------------------
 * Le défaut que ça corrige
 * ---------------------------------------------------------------------------
 *
 * Le réglage ne touchait que la navigation. Choisir « Émeraude » donnait une
 * colonne verte à côté d'un contenu resté rose : deux couleurs franches sur
 * le même écran, qui ne se répondaient pas. Ce n'était pas un choix, c'était
 * un réglage à moitié appliqué.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi redéfinir `--salon-primary` ne falsifie rien
 * ---------------------------------------------------------------------------
 *
 * Cette variable habille le produit — boutons, états actifs, accents de
 * texte. Elle porte aussi, sur le mini-site, la couleur de marque du salon ;
 * mais le mini-site vit sur un autre hôte et ne traverse jamais cette
 * coquille.
 *
 * Restait le risque sérieux : les écrans où le salon **choisit** ses
 * couleurs de marque. Ils s'en tirent parce qu'ils peignent en valeurs
 * explicites, lues dans `theme_config` — palettes, aperçu du mini-site,
 * mesure de contraste. Aucun ne lit la variable. Un salon qui met sa colonne
 * en émeraude voit donc toujours sa vraie couleur dans son aperçu.
 *
 * Les trois variables bougent ensemble. N'en redéfinir qu'une laissait les
 * fonds tendres et les dégradés sur l'ancienne teinte — le même défaut, en
 * plus discret.
 *
 * `transparent` plutôt que `white` dans le mélange tendre : la même règle
 * doit tenir sur fond clair et sur fond sombre, et un mélange vers le blanc
 * produit une pastille laiteuse la nuit.
 */
/** Les six variables que l'accent repeint, et rien d'autre. */
const ACCENT_VARS = [
  "--salon-primary",
  "--salon-primary-soft",
  "--salon-accent",
  "--color-salon",
  "--color-salon-soft",
  "--color-salon-accent",
] as const;

/**
 * Pose l'accent sur `<html>`, ou l'enlève.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi la racine, et pas la coquille
 * ---------------------------------------------------------------------------
 *
 * Une première version posait ces variables sur le `<div>` de la coquille,
 * ce qui semblait plus propre — la portée épousait exactement l'espace
 * professionnel.
 *
 * Ça ne marchait qu'à moitié, et la mesure l'a montré : le dégradé de la
 * colonne virait bien à l'émeraude, mais les boutons du contenu restaient
 * roses. `.salon-gradient` est une règle écrite à la main qui lit
 * `var(--salon-primary)` au moment du rendu, donc elle héritait. `bg-salon`
 * et `text-salon`, eux, sont produits par Tailwind depuis le bloc `@theme`,
 * et ne se laissent pas redéfinir depuis un descendant — vérifié en
 * surchargeant les trois noms candidats sur l'élément lui-même : aucun n'a
 * eu d'effet.
 *
 * `<html>` est le seul niveau où la surcharge l'emporte à coup sûr, et c'est
 * déjà là que vit le thème clair/sombre. Le risque de déborder est nul : la
 * page du mini-site vit sur un autre hôte et ne partage pas ce document.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi six variables
 * ---------------------------------------------------------------------------
 *
 * Deux familles, deux publics. `--salon-*` sert aux règles écrites à la main,
 * `--color-salon*` aux utilitaires. N'en repeindre qu'une laissait les fonds
 * tendres et les dégradés sur l'ancienne teinte — le même défaut, en plus
 * discret.
 *
 * `transparent` plutôt que `white` dans le mélange tendre : la règle doit
 * tenir sur fond clair comme sur fond sombre, et un mélange vers le blanc
 * donne une pastille laiteuse la nuit.
 */
export function applyAccent(accent: AccentName): void {
  const root = document.documentElement;

  // « Couleur du salon » n'est pas une surcharge : c'est son absence. On
  // retire, et la feuille de style reprend la main.
  if (accent === "salon") {
    for (const name of ACCENT_VARS) root.style.removeProperty(name);
    return;
  }

  const color = ACCENTS[accent].color;
  const soft = `color-mix(in srgb, ${color} 14%, transparent)`;
  const pale = `color-mix(in srgb, ${color} 42%, white)`;

  root.style.setProperty("--salon-primary", color);
  root.style.setProperty("--salon-primary-soft", soft);
  root.style.setProperty("--salon-accent", pale);
  root.style.setProperty("--color-salon", color);
  root.style.setProperty("--color-salon-soft", soft);
  root.style.setProperty("--color-salon-accent", pale);
}

/**
 * Les trois habillages de la colonne, classe par classe.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi une table plutôt que des conditions dans le composant
 * ---------------------------------------------------------------------------
 *
 * La colonne peint une douzaine d'éléments : le nom du produit, les titres de
 * groupe, les rubriques, le filet du mode replié, la fiche du salon, le lien
 * vers le mini-site. Trois habillages × douze éléments écrits en ternaires
 * dans le rendu donneraient trente-six conditions dispersées, et un oubli se
 * verrait par un texte blanc sur fond blanc.
 *
 * ---------------------------------------------------------------------------
 * La transparence s'arrête au téléphone
 * ---------------------------------------------------------------------------
 *
 * Sur grand écran, la colonne est posée à côté du contenu : la laisser voir
 * le fond de page est un parti pris défendable. Sur téléphone, c'est un
 * tiroir qui recouvre la page — transparent, on lirait la liste des
 * rubriques par-dessus l'agenda. D'où le `lg:` : solide tant qu'elle est un
 * tiroir, transparente une fois qu'elle est une colonne.
 */
export interface NavSkin {
  aside: string;
  brand: string;
  item: string;
  rule: string;
  edge: string;
  chip: string;
  strong: string;
  faint: string;
  link: string;
  select: string;
  hover: string;
}

const ON_LIGHT = {
  brand: "text-ink",
  item: "text-muted hover:bg-surface-hover hover:text-ink",
  rule: "bg-line-strong",
  edge: "border-line",
  chip: "bg-surface-muted text-ink",
  strong: "text-ink",
  faint: "text-subtle",
  link: "text-muted hover:text-ink",
  select: "border-line bg-surface text-ink",
  hover: "hover:bg-surface-hover",
};

export const NAV_SKINS: Record<NavType, NavSkin> = {
  dark: {
    aside: "bg-[#17141c]",
    brand: "text-white",
    item: "text-white/60 hover:bg-white/[0.06] hover:text-white",
    rule: "bg-white/15",
    edge: "border-white/[0.08]",
    chip: "bg-white/[0.08] text-white",
    strong: "text-white",
    faint: "text-white/45",
    link: "text-white/50 hover:text-white",
    // `text-black` sur les options : sous Windows, la liste déroulante est
    // peinte par le système sur fond clair, et un texte blanc y devient
    // invisible.
    select: "border-white/10 bg-white/[0.06] text-white",
    hover: "hover:bg-white/[0.06]",
  },
  transparent: { aside: "bg-surface lg:bg-transparent", ...ON_LIGHT },
  light: { aside: "bg-surface lg:border-r lg:border-line", ...ON_LIGHT },
};

const NAV_TYPES: { value: NavType; label: string; hint: string }[] = [
  { value: "dark", label: "Sombre", hint: "fond constant, quel que soit le thème" },
  { value: "transparent", label: "Transparente", hint: "la page passe dessous" },
  { value: "light", label: "Claire", hint: "suit le thème clair ou sombre" },
];

/* ----- Magasin ---------------------------------------------------------- */

let current: ShellPrefs = DEFAULTS;
let hydrated = false;
const listeners = new Set<() => void>();

function read(): ShellPrefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<ShellPrefs>;
    return {
      // Chaque champ est revalidé : un stockage écrit par une version
      // antérieure, ou trafiqué à la main, ne doit pas pouvoir peindre la
      // navigation avec une valeur qui n'existe pas.
      accent: parsed.accent && parsed.accent in ACCENTS ? parsed.accent : DEFAULTS.accent,
      navType: NAV_TYPES.some((type) => type.value === parsed.navType)
        ? (parsed.navType as NavType)
        : DEFAULTS.navType,
      navbarFixed:
        typeof parsed.navbarFixed === "boolean"
          ? parsed.navbarFixed
          : DEFAULTS.navbarFixed,
      sidebarHidden:
        typeof parsed.sidebarHidden === "boolean"
          ? parsed.sidebarHidden
          : DEFAULTS.sidebarHidden,
    };
  } catch {
    // Navigation privée, stockage refusé : les valeurs par défaut suffisent.
    return DEFAULTS;
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  // `storage` ne se déclenche que dans les *autres* onglets : deux onglets
  // ouverts restent d'accord sur l'apparence.
  const sync = () => {
    current = read();
    listener();
  };
  window.addEventListener("storage", sync);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", sync);
  };
}

function snapshot(): ShellPrefs {
  /*
    La première lecture doit venir du stockage, mais elle ne peut pas avoir
    lieu au rendu serveur. On la fait donc paresseusement, une seule fois, et
    on renvoie ensuite toujours le même objet : `useSyncExternalStore` compare
    les instantanés par identité, et un objet neuf à chaque appel ferait
    boucler le rendu indéfiniment.
  */
  if (!hydrated) {
    current = read();
    hydrated = true;
  }
  return current;
}

/** Le serveur ne connaît pas le choix : il rend l'état neutre, et c'est le
 *  même objet que celui du premier rendu client tant que rien n'est stocké. */
const serverSnapshot = (): ShellPrefs => DEFAULTS;

export function useShellPrefs(): ShellPrefs {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}

/**
 * « Le système est-il en sombre ? », lu comme un magasin externe.
 *
 * Par `useSyncExternalStore` et non par un effet qui poserait un état : le
 * rendu serveur répond « non », l'hydratation compare le même « non », et la
 * vraie valeur arrive juste après sans jamais produire de HTML divergent.
 * Un `useEffect` qui appellerait `setState` ferait clignoter la bascule et
 * tomberait sous `react-hooks/set-state-in-effect`.
 */
function subscribeSystem(listener: () => void) {
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  query.addEventListener("change", listener);
  return () => query.removeEventListener("change", listener);
}

const systemIsDark = () =>
  window.matchMedia("(prefers-color-scheme: dark)").matches;

export function setShellPrefs(patch: Partial<ShellPrefs>) {
  current = { ...snapshot(), ...patch };
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Le réglage vaut au moins pour cette session, et c'est déjà mieux que
    // de refuser le clic.
  }
  for (const listener of listeners) listener();
}

/* --------------------------------------------------------------------------
 * Le panneau
 * ---------------------------------------------------------------------- */

export function Configurator() {
  const prefs = useShellPrefs();
  const theme = useThemeChoice();
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  // Échap referme : c'est le geste attendu d'un tiroir, et il évite d'avoir
  // à viser une croix de 24 pixels au clavier.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  /*
    « Sombre » ici veut dire « sombre », pas « système ». La bascule du
    panneau est binaire parce qu'elle est lue comme un interrupteur ; le
    bouton à trois états — dont « suivre le système » — reste dans la barre
    du haut, où sa nuance a la place d'être expliquée par son icône.

    Quand le choix vaut « système », l'interrupteur doit tout de même montrer
    l'état réel : affiché à « clair » sur un téléphone en sombre, il ferait
    croire à une panne.
  */
  const systemDark = useSyncExternalStore(
    subscribeSystem,
    systemIsDark,
    () => false,
  );
  const dark = theme === "dark" || (theme === "system" && systemDark);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-label="Réglages d'affichage"
        title="Réglages d'affichage"
        className="salon-gradient group fixed bottom-5 right-5 z-30 flex size-12 items-center justify-center rounded-full text-white shadow-float transition hover:brightness-110 active:scale-95"
      >
        {/* Les curseurs pivotent au survol : posé par-dessus le contenu, un
            bouton parfaitement immobile se lit comme une image collée. Un
            quart de tour suffit à dire qu'il répond. */}
        <Icon
          name="sliders"
          className="size-5 transition-transform duration-300 group-hover:rotate-90"
        />
      </button>

      {open && (
        <button
          type="button"
          aria-label="Fermer les réglages"
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-[45] bg-black/40 backdrop-blur-[2px]"
        />
      )}

      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-label="Réglages d'affichage"
        aria-hidden={!open}
        // `translate-x-full` plutôt que le démontage : le tiroir glisse au
        // lieu d'apparaître, et son contenu garde sa position de défilement
        // d'une ouverture à l'autre.
        className={`fixed inset-y-0 right-0 z-50 flex w-[min(22rem,90vw)] flex-col border-l border-line bg-surface shadow-float transition-transform duration-300 ${
          open ? "translate-x-0" : "pointer-events-none translate-x-full"
        }`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-ink">
              Réglages d&apos;affichage
            </h2>
            <p className="mt-0.5 text-xs text-muted">
              Ils valent pour cet appareil, pas pour votre salon.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Fermer"
            className="-mr-1.5 rounded-lg p-1.5 text-muted transition hover:bg-surface-hover hover:text-ink"
          >
            <Icon name="close" className="size-5" />
          </button>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
          {/* ----- Accent ------------------------------------------------ */}
          <section>
            <h3 className="text-sm font-semibold text-ink">
              Couleur de l&apos;espace
            </h3>
            {/* Le libellé disait « Couleur de la navigation », et le réglage
                ne touchait effectivement que la colonne : on obtenait une
                colonne verte à côté d'un contenu rose. Il repeint désormais
                tout l'espace, et le titre le dit. */}
            <p className="mt-0.5 text-xs text-muted">
              Colonne, boutons et états actifs, ensemble.
            </p>

            <div className="mt-3 flex flex-wrap gap-2.5">
              {(Object.keys(ACCENTS) as AccentName[]).map((name) => {
                const chosen = prefs.accent === name;
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => setShellPrefs({ accent: name })}
                    aria-pressed={chosen}
                    title={ACCENTS[name].label}
                    aria-label={ACCENTS[name].label}
                    style={{ backgroundImage: accentGradient(name) }}
                    className={`flex size-8 items-center justify-center rounded-full text-white transition hover:scale-110 ${
                      chosen
                        ? "ring-2 ring-ink ring-offset-2 ring-offset-[var(--ui-surface)]"
                        : ""
                    }`}
                  >
                    {/* La coche double l'anneau : un anneau seul se voit mal
                        sur la pastille sombre, et la couleur choisie ne doit
                        pas se deviner. */}
                    {chosen && <Icon name="check" className="size-4" />}
                  </button>
                );
              })}
            </div>
          </section>

          {/* ----- Fond de la colonne ------------------------------------ */}
          <section>
            <h3 className="text-sm font-semibold text-ink">
              Fond de la colonne
            </h3>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {NAV_TYPES.map((type) => {
                const chosen = prefs.navType === type.value;
                return (
                  <button
                    key={type.value}
                    type="button"
                    onClick={() => setShellPrefs({ navType: type.value })}
                    aria-pressed={chosen}
                    title={type.hint}
                    className={`rounded-xl border px-2 py-2.5 text-xs font-medium transition ${
                      chosen
                        ? "border-transparent text-white shadow-sm"
                        : "border-line text-muted hover:border-line-strong hover:text-ink"
                    }`}
                    style={
                      chosen
                        ? { backgroundImage: accentGradient(prefs.accent) }
                        : undefined
                    }
                  >
                    {type.label}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-xs text-muted">
              {NAV_TYPES.find((type) => type.value === prefs.navType)?.hint}
            </p>
          </section>

          <hr className="border-line" />

          {/* ----- Bascules ---------------------------------------------- */}
          <div className="space-y-5">
            <Toggle
              checked={prefs.navbarFixed}
              onChange={(value) => setShellPrefs({ navbarFixed: value })}
              label="Barre du haut fixe"
              hint={
                prefs.navbarFixed
                  ? "Elle reste en place quand la page défile."
                  : "Elle remonte avec la page et libère de la hauteur."
              }
            />

            <Toggle
              checked={dark}
              onChange={(value) => setTheme(value ? "dark" : "light")}
              label="Thème sombre"
              hint="Le bouton de la barre du haut propose en plus « suivre le système »."
            />

            {/*
              La demande explicite : masquer la colonne.

              Distincte du repli aux icônes — celui-là garde la navigation à
              portée de clic, celui-ci la fait disparaître pour donner toute
              la largeur à un agenda en vue mois. Sur téléphone elle reste
              accessible par le bouton menu : masquer la colonne ne doit
              jamais enfermer quelqu'un sur une page.
            */}
            <Toggle
              checked={!prefs.sidebarHidden}
              onChange={(value) => setShellPrefs({ sidebarHidden: !value })}
              label="Afficher la colonne de navigation"
              hint={
                prefs.sidebarHidden
                  ? "Masquée : le bouton en haut à gauche la fait revenir."
                  : "Visible. Le même bouton la replie aux icônes seules."
              }
            />
          </div>

          <hr className="border-line" />

          <button
            type="button"
            onClick={() => setShellPrefs(DEFAULTS)}
            className="w-full rounded-xl border border-line px-4 py-2.5 text-sm font-medium text-muted transition hover:bg-surface-hover hover:text-ink"
          >
            Revenir à l&apos;apparence d&apos;origine
          </button>
        </div>
      </div>
    </>
  );
}
