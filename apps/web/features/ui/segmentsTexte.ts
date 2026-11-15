/**
 * Le texte d'un assistant, découpé en morceaux affichables.
 *
 * Les réponses d'un modèle arrivent en texte brut, avec parfois un lien
 * Markdown (`[Réserver en ligne](https://…)`), une adresse nue ou du gras.
 * Affichées telles quelles, elles montraient la syntaxe au lieu d'un lien
 * cliquable.
 *
 * On ne rend **jamais** ce texte comme du HTML : il vient d'un modèle, qui
 * peut être amené à écrire n'importe quoi. Le découpage produit des morceaux
 * typés, que le composant transforme en éléments React ; seuls les liens
 * `http(s)` deviennent des liens.
 */

export type Morceau =
  | { type: "texte"; texte: string }
  | { type: "gras"; texte: string }
  | { type: "lien"; texte: string; href: string };

// Un lien Markdown, une adresse nue, ou du gras — dans cet ordre de priorité.
const MOTIF =
  /\[([^\]\n]{1,120})\]\s{0,8}\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s<>()]+)|\*\*([^*\n]{1,200})\*\*/g;

// Ponctuation collée à une adresse nue en fin de phrase : elle n'en fait pas partie.
const PONCTUATION_FINALE = /[.,;:!?»"')\]]+$/;

/**
 * « reserver_en_ligne » -> « Reserver en ligne ».
 *
 * Un modèle recopie parfois le nom d'un champ comme libellé ; mieux vaut un
 * libellé lisible qu'une variable à l'écran.
 */
export function libelleLisible(libelle: string): string {
  const net = libelle.trim();
  if (!/^[a-z0-9]+(_[a-z0-9]+)+$/i.test(net)) return net;
  const mots = net.replace(/_/g, " ").toLowerCase();
  return mots.charAt(0).toUpperCase() + mots.slice(1);
}

function lienSur(adresse: string): string | null {
  try {
    const url = new URL(adresse);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

export function decouper(texte: string): Morceau[] {
  const morceaux: Morceau[] = [];
  let curseur = 0;

  const ajouterTexte = (valeur: string) => {
    if (!valeur) return;
    const dernier = morceaux[morceaux.length - 1];
    if (dernier?.type === "texte") dernier.texte += valeur;
    else morceaux.push({ type: "texte", texte: valeur });
  };

  for (const trouve of texte.matchAll(MOTIF)) {
    const debut = trouve.index ?? 0;
    ajouterTexte(texte.slice(curseur, debut));
    const [brut, libelle, cibleMarkdown, adresseNue, gras] = trouve;

    if (libelle !== undefined && cibleMarkdown !== undefined) {
      const href = lienSur(cibleMarkdown);
      if (href) morceaux.push({ type: "lien", texte: libelleLisible(libelle), href });
      else ajouterTexte(brut);
    } else if (adresseNue !== undefined) {
      const reste = adresseNue.match(PONCTUATION_FINALE)?.[0] ?? "";
      const adresse = reste ? adresseNue.slice(0, -reste.length) : adresseNue;
      const href = lienSur(adresse);
      if (href) morceaux.push({ type: "lien", texte: adresse, href });
      else ajouterTexte(adresse);
      ajouterTexte(reste);
    } else if (gras !== undefined) {
      morceaux.push({ type: "gras", texte: gras });
    } else {
      ajouterTexte(brut);
    }
    curseur = debut + brut.length;
  }
  ajouterTexte(texte.slice(curseur));
  return morceaux;
}
