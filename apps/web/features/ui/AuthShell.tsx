"use client";

/**
 * La coquille de toutes les pages d'identification de la plateforme.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi une page à part, sans menu ni pied de page
 * ---------------------------------------------------------------------------
 *
 * Se connecter et s'inscrire sont les deux seuls écrans du produit où
 * **toute** autre chose à cliquer est une fuite. Le menu propose sept
 * destinations, le pied de page une vingtaine : chacune est une occasion
 * d'abandonner un formulaire qu'on avait commencé à remplir.
 *
 * Il ne reste donc qu'une sortie, explicite et unique — le retour au site.
 * Ce n'est pas une restriction : c'est ce qui rend la page lisible d'un coup
 * d'œil, et c'est la pratique de tous les produits qui prennent leur tunnel
 * d'inscription au sérieux.
 *
 * ---------------------------------------------------------------------------
 * Le fond
 * ---------------------------------------------------------------------------
 *
 * Il est composé à partir des variables du thème **courant** — celui du
 * salon sur un mini-site, celui du produit sur l'espace professionnel. Un
 * dégradé figé aurait obligé à choisir une couleur, donc à trahir la charte
 * de l'un ou de l'autre.
 *
 * Trois voiles flous dérivent lentement, en `transform` et `opacity`
 * seulement : le navigateur les compose sans recalculer la page, ce qui les
 * rend gratuits même sur un téléphone d'entrée de gamme. `prefers-reduced-
 * motion` les fige — le dégradé reste, le mouvement s'arrête.
 *
 * Le contenu est posé au-dessus d'une carte opaque : un formulaire lu à
 * travers un dégradé animé est un formulaire qu'on remplit mal.
 */

import type { ReactNode } from "react";

/* --------------------------------------------------------------------------
 * Le système commun aux deux écrans
 * --------------------------------------------------------------------------
 *
 * Se connecter à son salon et se connecter à son compte cliente sont deux
 * publics différents, mais un seul geste. Les deux écrans partagent donc la
 * même largeur de carte, les mêmes champs, la même hiérarchie — et seuls le
 * texte et l'illustration changent. Quand ils divergeaient, c'était toujours
 * par accident : un titre au-dessus de la carte d'un côté, dedans de
 * l'autre, et deux tailles de champ.
 * ---------------------------------------------------------------------- */

/** La carte du formulaire. Bordure fine, ombre discrète, surface neutre. */
export const authCard =
  "rounded-2xl border border-line bg-surface p-5 shadow-card sm:p-6";

/**
 * Un champ de saisie.
 *
 * 16 px de texte : en dessous, iOS zoome de lui-même au premier appui et la
 * page reste agrandie une fois le clavier refermé. La hauteur suit — autour
 * de 48 px, la cible d'un pouce.
 */
export const authInput =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-3 text-base text-ink " +
  "transition placeholder:text-subtle focus:border-salon focus:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-salon/30";

/** Le titre de la carte : 24 px sur téléphone, 30 px ensuite. */
export const authTitle =
  "text-2xl font-semibold tracking-tight text-ink sm:text-3xl";

/** La phrase sous le titre. Assez contrastée pour être lue, pas pour crier. */
export const authLead = "mt-2 text-[0.95rem] leading-relaxed text-ink/75";

/** Un lien secondaire, à la couleur de l'accent courant. */
export const authLink =
  "rounded font-medium text-salon underline-offset-4 transition hover:underline " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-salon)]";

export function AuthShell({
  brand,
  homeHref,
  homeLabel = "Retour au site",
  action,
  children,
  aside,
}: {
  /** Logo + nom, à gauche de la barre. */
  brand: ReactNode;
  /** Où ramène la seule sortie de la page. */
  homeHref: string;
  homeLabel?: string;
  /** Bascule de thème, ou rien. */
  action?: ReactNode;
  children: ReactNode;
  /**
   * Colonne de réassurance, à droite sur grand écran.
   *
   * Elle porte ce qui décide vraiment : ce qu'on obtient, ce qu'on risque,
   * ce que d'autres en disent.
   *
   * Sur téléphone elle passe **sous** le formulaire — elle n'est plus
   * masquée. La cacher revenait à dire que l'argument ne vaut que pour qui
   * a un grand écran ; la mettre au-dessus repousserait le premier champ
   * sous la ligne de flottaison. En dessous, elle ne coûte rien à celle qui
   * vient se connecter, et reste lisible pour celle qui hésite. Les
   * illustrations, elles, restent réservées au grand écran : c'est le
   * panneau lui-même qui décide.
   */
  aside?: ReactNode;
}) {
  return (
    <div className="auth-shell relative flex min-h-svh flex-col overflow-hidden bg-bg">
      <AnimatedBackdrop />

      <header className="relative z-10 px-5 pt-4 sm:px-6 sm:pt-5">
        <div className="mx-auto flex max-w-[70rem] items-center gap-3">
          <a
            href={homeHref}
            className="flex min-w-0 items-center gap-2.5"
            aria-label={homeLabel}
          >
            {brand}
          </a>

          <div className="ml-auto flex items-center gap-2">
            {action}
            <a
              href={homeHref}
              className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/80 px-3 py-2 text-sm font-medium text-muted backdrop-blur transition hover:text-ink"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                aria-hidden
                className="size-4"
              >
                <path
                  d="M15 6l-6 6 6 6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span className="hidden sm:inline">{homeLabel}</span>
            </a>
          </div>
        </div>
      </header>

      {/*
        Aligné en haut, jamais centré verticalement.

        Un bloc centré dans la hauteur de la fenêtre se déplace dès que
        quelque chose change au-dessus ou en dessous — une erreur qui
        apparaît, un clavier de téléphone qui s'ouvre. Sur un petit écran en
        paysage, le champ qu'on remplissait se retrouve hors cadre pendant
        qu'on tape dedans. Posé en haut, il ne bouge pas, et la page défile
        normalement quand il n'y a plus la place.

        Le grand écran retrouve un centrage optique par le seul rembourrage
        haut — qui, lui, ne dépend pas de la hauteur du contenu.
      */}
      <main className="relative z-10 flex flex-1 justify-center px-5 pb-12 pt-6 sm:px-6 sm:pt-10 lg:pt-16">
        <div
          className={`mx-auto grid w-full gap-10 lg:gap-14 ${
            aside
              ? "max-w-[70rem] lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] lg:items-start"
              : "max-w-md"
          }`}
        >
          <div className="w-full">{children}</div>
          {aside}
        </div>
      </main>
    </div>
  );
}

/**
 * Trois voiles de couleur qui dérivent.
 *
 * Les teintes viennent des variables du thème courant, donc la page se
 * reteinte toute seule quand un salon change sa palette ou quand on passe
 * en mode sombre — sans une ligne de JavaScript.
 */
function AnimatedBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      <span className="auth-blob auth-blob-1" />
      <span className="auth-blob auth-blob-2" />
      <span className="auth-blob auth-blob-3" />

      {/*
        Le voile, qui porte aussi le dégradé.

        Il ne fait plus seulement baisser les taches : il pose par-dessus
        trois masses de couleur choisies, à une densité réglée par thème
        (`--auth-teinte`). Voir `.auth-voile` dans `globals.css`.

        Une couleur de fond et une image de fond se peignent dans cet ordre
        sur un même élément : une seule couche fait donc les deux gestes,
        là où il en fallait deux et où la couleur n'arrivait pas à l'écran.

        La carte du formulaire reste opaque, donc le contraste de ce qui est
        dedans ne dépend pas de ce fond. Seuls le titre et les mentions posés
        à côté sont concernés, et ils sont mesurés.
      */}
      <span className="auth-voile" />
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Réassurance
 * ---------------------------------------------------------------------- */

/**
 * Un argument de la colonne de droite.
 *
 * Trois au maximum : au-delà, on ne lit plus une liste, on la survole. Ils
 * répondent dans cet ordre aux trois questions qui retiennent quelqu'un
 * devant un formulaire — qu'est-ce que j'obtiens, qu'est-ce que ça
 * m'engage, et qui l'a déjà fait.
 */
export function AuthPoint({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    /*
      Deux formes pour un même argument.

      Sur téléphone, c'est une vignette : le titre seul, dans une carte, deux
      par ligne. La phrase explicative disparaît — sous le formulaire, elle
      ajoutait trois paragraphes que personne ne fait défiler pour lire, et
      elle repoussait le pied de page hors de portée. Le titre, lui, se
      retient d'un coup d'œil, et c'est tout ce qu'on lui demande à cet
      endroit.

      À partir de `lg`, la colonne de droite a la place : la puce revient,
      la phrase aussi.
    */
    <li className="rounded-xl border border-line bg-surface/60 p-3 lg:flex lg:gap-3 lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0">
      <span
        aria-hidden
        className="mb-1.5 block size-1.5 rounded-full bg-salon lg:mb-0 lg:mt-[0.4rem] lg:shrink-0"
      />
      <span className="min-w-0">
        <span className="block text-[0.8rem] font-medium leading-snug text-ink lg:text-sm">
          {title}
        </span>
        <span className="mt-0.5 hidden text-sm leading-relaxed text-ink/70 lg:block">
          {children}
        </span>
      </span>
    </li>
  );
}

/**
 * La liste des arguments.
 *
 * Elle existe pour que les deux écrans ne choisissent pas chacun sa grille :
 * c'est exactement par là qu'ils avaient divergé la première fois.
 */
export function AuthPoints({ children }: { children: ReactNode }) {
  return (
    /*
      La dernière vignette occupe la ligne entière quand elle s'y retrouve
      seule. Trois arguments sur deux colonnes laissent sinon un trou à
      droite, qui se lit comme une carte qui n'a pas fini de charger.
    */
    <ul className="mt-4 grid grid-cols-2 gap-2 lg:mt-5 lg:grid-cols-1 lg:gap-3.5 [&>li:last-child:nth-child(odd)]:col-span-2 lg:[&>li:last-child:nth-child(odd)]:col-span-1">
      {children}
    </ul>
  );
}

/**
 * L'en-tête du panneau de droite.
 *
 * Il existe pour que les deux écrans ne se mettent pas à écrire leur titre
 * de panneau chacun à sa taille — c'est exactement la dérive qui avait donné
 * un « 2xl » d'un côté et un titre hors carte de l'autre.
 */
export function AuthAsideTitle({ children }: { children: ReactNode }) {
  return (
    // Plus discret sur téléphone : il y introduit trois vignettes, pas une
    // section. À `lg` il redevient le titre de la colonne.
    <h2 className="text-base font-semibold tracking-tight text-ink lg:text-2xl">
      {children}
    </h2>
  );
}
