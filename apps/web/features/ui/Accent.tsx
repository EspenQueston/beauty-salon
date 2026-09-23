/**
 * Mise en valeur typographique des titres.
 *
 * Deux effets, deux usages :
 *
 *   <Souligne>  un mot souligné d'un trait qui se dessine après le titre.
 *               Sert à désigner la promesse — « réservent en ligne ».
 *   <Lettres>   le mot arrive lettre par lettre. Réservé au nom du salon,
 *               parce que c'est le seul endroit où ralentir la lecture d'un
 *               mot est un service rendu : on le retient.
 *
 * Ni l'un ni l'autre n'est un composant client. Tout est en CSS, et le
 * décalage de chaque lettre est écrit dans le style au rendu : l'animation
 * démarre au premier affichage, sans attendre l'hydratation — ce qui compte
 * sur les téléphones lents visés.
 */

import type { CSSProperties, ReactNode } from "react";

export function Souligne({
  children,
  color,
}: {
  children: ReactNode;
  /** Couleur du trait. À défaut, celle du salon. */
  color?: string;
}) {
  return (
    <span
      className="mot-cle"
      style={
        color ? ({ "--mot-cle-couleur": color } as CSSProperties) : undefined
      }
    >
      {children}
    </span>
  );
}

export function Lettres({
  text,
  className = "",
}: {
  text: string;
  className?: string;
}) {
  return (
    <span className={`lettres ${className}`} aria-label={text}>
      {/* Le mot entier reste lisible pour les lecteurs d'écran grâce à
          `aria-label` ; les lettres découpées leur sont masquées, sinon
          elles seraient épelées une à une. */}
      {Array.from(text).map((letter, index) => (
        <span
          key={index}
          aria-hidden
          data-espace={letter === " " ? "" : undefined}
          style={{ "--i": index } as CSSProperties}
        >
          {letter === " " ? " " : letter}
        </span>
      ))}
    </span>
  );
}

/**
 * Les mots montent de derrière une ligne, l'un après l'autre.
 *
 * ---------------------------------------------------------------------------
 * Ce que ça donne, et pourquoi c'est mieux que lettre par lettre
 * ---------------------------------------------------------------------------
 *
 * Chaque mot est enfermé dans un masque à hauteur de ligne, et part *sous*
 * ce masque. Il ne se révèle pas en s'éclaircissant : il entre dans le cadre
 * par le bas, comme une ligne composée qu'on ferait monter. C'est le geste
 * qui donne son poids au titre — on croit voir le mot arriver, pas
 * apparaître.
 *
 * La version lettre par lettre avait un défaut que trois mots suffisent à
 * révéler : au-delà d'une douzaine de caractères, l'œil suit le curseur au
 * lieu de lire, et un nom de salon en deux mots devenait long à attendre.
 * Le décalage se fait donc par mot, ce qui borne la durée totale quel que
 * soit le nombre de lettres.
 *
 * ---------------------------------------------------------------------------
 * Le masque et les jambages
 * ---------------------------------------------------------------------------
 *
 * `overflow: hidden` coupe net ce qui dépasse — et ce qui dépasse d'une
 * ligne de texte, ce sont les jambages : le g de « rouge », le p de
 * « pose ». Le masque reçoit donc une réserve en bas, reprise par une marge
 * négative de même valeur : la coupe se fait sous les jambages, et la mise
 * en page ne bouge pas d'un pixel.
 *
 * ---------------------------------------------------------------------------
 * Ce qui reste lisible sans animation
 * ---------------------------------------------------------------------------
 *
 * Tout. Les mots sont du texte normal dans un `<span>` : sans JavaScript ils
 * sont déjà en place, et `prefers-reduced-motion` les y laisse. Le titre
 * n'est jamais caché en attendant quelque chose.
 */
export function Mots({
  text,
  className = "",
  /** Décalage entre deux mots, en millisecondes. */
  stagger = 90,
  /** Attente avant le premier mot. */
  delay = 0,
}: {
  text: string;
  className?: string;
  stagger?: number;
  delay?: number;
}) {
  const mots = text.trim().split(/\s+/);

  return (
    <span className={`mots ${className}`}>
      {mots.map((mot, index) => (
        <span key={`${mot}-${index}`} className="mots-masque">
          <span
            className="mots-mot"
            style={{ animationDelay: `${delay + index * stagger}ms` }}
          >
            {mot}
          </span>
          {/* L'espace vit hors du masque : à l'intérieur, il serait coupé
              avec le reste et les mots se colleraient. */}
          {index < mots.length - 1 ? " " : null}
        </span>
      ))}
    </span>
  );
}
