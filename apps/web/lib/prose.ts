/**
 * Mise en paragraphes d'un texte saisi dans un champ libre.
 *
 * ---------------------------------------------------------------------------
 * Le problème
 * ---------------------------------------------------------------------------
 *
 * Un salon écrit sa présentation dans une zone de texte, souvent d'un trait,
 * parfois collée depuis WhatsApp. Découper sur les lignes vides — la règle
 * évidente — donne alors **un seul** paragraphe : un pavé de quinze lignes
 * que personne ne lit, avec une lettrine au début et rien d'autre.
 *
 * On ne peut pas demander au salon de mettre des sauts de ligne : il écrit ce
 * qu'il a à dire, la mise en page n'est pas son métier. C'est donc au site de
 * respirer à sa place.
 *
 * ---------------------------------------------------------------------------
 * La règle, du plus fidèle au plus interventionniste
 * ---------------------------------------------------------------------------
 *
 *   1. Lignes vides — l'intention explicite de l'auteur. On s'y tient.
 *   2. Sauts de ligne simples, si un bloc reste trop long.
 *   3. Regroupement de phrases, en dernier recours.
 *
 * On ne réécrit jamais un mot, on n'en supprime aucun, et on ne remonte
 * jamais d'un niveau : un texte déjà paragraphé garde exactement sa forme.
 */

/** Au-delà, un bloc devient un mur : environ six lignes en pleine largeur. */
const TOO_LONG = 420;

/** Longueur visée quand on coupe soi-même : trois à quatre lignes. */
const TARGET = 280;

export function toParagraphs(text: string): string[] {
  const explicit = split(text, /\n{2,}/);
  return explicit.flatMap(loosen);
}

function loosen(block: string): string[] {
  if (block.length <= TOO_LONG) return [block];

  // 2. L'auteur est allé à la ligne sans sauter de ligne : c'est déjà une
  //    intention, on la respecte avant d'inventer la nôtre.
  const lines = split(block, /\n+/);
  if (lines.length > 1) return lines.flatMap(loosen);

  // 3. Rien à quoi se raccrocher : on groupe les phrases. La coupe se fait
  //    après la ponctuation finale, donc jamais au milieu d'une idée.
  return groupSentences(block);
}

/**
 * Regroupe les phrases en paragraphes d'une longueur comparable.
 *
 * Grouper par *nombre* de phrases paraissait plus simple, mais trois phrases
 * courtes font un paragraphe maigre et trois phrases longues refont le mur
 * qu'on voulait éviter — mesuré à 463 caractères sur un texte réel. C'est
 * donc la longueur qui décide, et la coupe tombe toujours après une
 * ponctuation finale : jamais au milieu d'une idée.
 */
function groupSentences(block: string): string[] {
  const sentences = block.match(/[^.!?…]+(?:[.!?…]+["»”')\]]*\s*|$)/g);
  if (!sentences || sentences.length <= 1) return [block];

  const groups: string[] = [];
  let current = "";

  for (const sentence of sentences) {
    // Une phrase qui dépasse à elle seule reste entière : la découper
    // trahirait le texte, et l'auteur reste maître de sa ponctuation.
    if (current && current.length + sentence.length > TARGET) {
      groups.push(current.trim());
      current = sentence;
    } else {
      current += sentence;
    }
  }
  if (current.trim()) groups.push(current.trim());

  // Une queue d'une seule phrase courte pend tristement en fin de texte :
  // elle rejoint le groupe précédent.
  if (groups.length > 1) {
    const last = groups[groups.length - 1];
    if (last.length < 90) {
      groups[groups.length - 2] += ` ${last}`;
      groups.pop();
    }
  }

  return groups;
}

function split(text: string, on: RegExp): string[] {
  return text
    .split(on)
    .map((part) => part.trim())
    .filter(Boolean);
}

/**
 * Temps de lecture, arrondi à la minute la plus proche, minimum une.
 *
 * Il ne sert pas à impressionner : il dit à une visiteuse pressée si elle
 * peut lire maintenant ou si elle revient plus tard. 200 mots par minute est
 * la moyenne admise pour une lecture confortable à l'écran.
 */
export function readingMinutes(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 200));
}
