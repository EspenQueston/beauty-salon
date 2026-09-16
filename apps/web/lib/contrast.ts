/**
 * Lisibilité d'une palette : mesure, note, et correction.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi une mesure, et pas un avis
 * ---------------------------------------------------------------------------
 *
 * Un salon choisit ses couleurs à l'œil, sur un écran d'ordinateur bien
 * réglé, dans une pièce éclairée. Ses clientes lisent la même page sur un
 * téléphone d'entrée de gamme, en plein soleil. Un jaune pâle sur blanc qui
 * « passe bien » chez lui devient illisible chez elles — et c'est le salon
 * qui perd la réservation, sans jamais savoir pourquoi.
 *
 * D'où un chiffre plutôt qu'un ressenti : le rapport de contraste WCAG 2.1,
 * calculé sur la luminance relative des deux couleurs. C'est la même mesure
 * qu'utilisent les outils d'audit d'accessibilité, et elle est reproductible.
 *
 * ---------------------------------------------------------------------------
 * Du rapport au pourcentage
 * ---------------------------------------------------------------------------
 *
 * Le rapport va de 1 (identique, invisible) à 21 (noir sur blanc). Ces
 * chiffres ne parlent à personne. On les ramène à un pourcentage ancré sur
 * les seuils qui comptent réellement :
 *
 *     4,5:1  → 70 %   seuil AA pour du texte courant
 *     7:1    → 85 %   seuil AAA
 *     21:1   → 100 %
 *
 * L'échelle est donc volontairement *non linéaire* : elle est construite
 * pour que « 70 % » signifie exactement « conforme AA », et non un point
 * arbitraire sur une droite. Un salon qui vise 70 sait ce qu'il obtient.
 */

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

/** Accepte #abc et #aabbcc. Renvoie null sur tout le reste. */
export function parseHex(value: string): Rgb | null {
  const hex = value.trim().replace(/^#/, "");

  if (hex.length === 3 && /^[0-9a-f]{3}$/i.test(hex)) {
    return {
      r: parseInt(hex[0] + hex[0], 16),
      g: parseInt(hex[1] + hex[1], 16),
      b: parseInt(hex[2] + hex[2], 16),
    };
  }
  if (hex.length === 6 && /^[0-9a-f]{6}$/i.test(hex)) {
    return {
      r: parseInt(hex.slice(0, 2), 16),
      g: parseInt(hex.slice(2, 4), 16),
      b: parseInt(hex.slice(4, 6), 16),
    };
  }
  return null;
}

export function toHex({ r, g, b }: Rgb): string {
  const part = (value: number) =>
    Math.max(0, Math.min(255, Math.round(value)))
      .toString(16)
      .padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`.toUpperCase();
}

/**
 * Luminance relative, formule WCAG 2.1.
 *
 * Les canaux sont d'abord linéarisés : l'œil ne perçoit pas la luminosité
 * proportionnellement à la valeur du pixel, et sauter cette étape fausse
 * lourdement le résultat sur les tons moyens.
 */
export function luminance({ r, g, b }: Rgb): number {
  const channel = (value: number) => {
    const ratio = value / 255;
    return ratio <= 0.03928
      ? ratio / 12.92
      : Math.pow((ratio + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** Rapport de contraste entre deux couleurs, de 1 à 21. */
export function contrastRatio(a: string, b: string): number | null {
  const first = parseHex(a);
  const second = parseHex(b);
  if (!first || !second) return null;

  const lighter = Math.max(luminance(first), luminance(second));
  const darker = Math.min(luminance(first), luminance(second));
  return (lighter + 0.05) / (darker + 0.05);
}

export type ContrastVerdict = "insuffisant" | "limite" | "bon" | "excellent";

export interface ContrastScore {
  ratio: number;
  /** 0 à 100, ancré sur les seuils WCAG. */
  percent: number;
  verdict: ContrastVerdict;
  /** Formulation destinée au salon, pas à un développeur. */
  label: string;
  /** Ce que ça change concrètement pour ses clientes. */
  detail: string;
}

/**
 * Interpolation par paliers entre les seuils qui font sens.
 *
 * Une simple règle de trois sur 1→21 donnerait 21 % à un contraste de 4,5:1,
 * alors que c'est précisément le minimum acceptable. Le score serait
 * décourageant pour une palette correcte, et l'outil cesserait d'être cru.
 */
function toPercent(ratio: number): number {
  const stops: [number, number][] = [
    [1, 0],
    [3, 45],
    [4.5, 70],
    [7, 85],
    [21, 100],
  ];

  for (let index = 0; index < stops.length - 1; index += 1) {
    const [lowRatio, lowScore] = stops[index];
    const [highRatio, highScore] = stops[index + 1];
    if (ratio <= highRatio) {
      const share = (ratio - lowRatio) / (highRatio - lowRatio);
      return Math.round(lowScore + share * (highScore - lowScore));
    }
  }
  return 100;
}

export function scoreContrast(
  foreground: string,
  background: string,
): ContrastScore | null {
  const ratio = contrastRatio(foreground, background);
  if (ratio === null) return null;

  const percent = toPercent(ratio);

  if (ratio < 3) {
    return {
      ratio,
      percent,
      verdict: "insuffisant",
      label: "Illisible",
      detail:
        "Ces deux couleurs se confondent. Vos prix et vos boutons seront difficiles à lire sur un téléphone.",
    };
  }
  if (ratio < 4.5) {
    return {
      ratio,
      percent,
      verdict: "limite",
      label: "Juste",
      detail:
        "Lisible pour les gros titres, mais fatigant pour le reste. Foncez un peu la couleur principale.",
    };
  }
  if (ratio < 7) {
    return {
      ratio,
      percent,
      verdict: "bon",
      label: "Bon",
      detail: "Lisible partout, y compris en plein soleil sur un petit écran.",
    };
  }
  return {
    ratio,
    percent,
    verdict: "excellent",
    label: "Excellent",
    detail: "Confort de lecture maximal, quel que soit l'écran.",
  };
}

/**
 * Assombrit ou éclaircit une couleur jusqu'à atteindre le contraste visé.
 *
 * On ne change que la luminosité, jamais la teinte : le salon garde *sa*
 * couleur, on la rend seulement lisible. Proposer un autre rose reviendrait
 * à décider de son identité à sa place.
 *
 * Recherche par dichotomie sur le facteur de mélange, plutôt qu'à l'aveugle
 * par pas fixes : une vingtaine d'itérations suffisent à approcher le seuil
 * au centième près.
 */
export function adjustForContrast(
  color: string,
  background: string,
  target = 4.5,
): string | null {
  const source = parseHex(color);
  const ground = parseHex(background);
  if (!source || !ground) return null;

  const current = contrastRatio(color, background);
  if (current === null || current >= target) return null;

  // Vers le noir si le fond est clair, vers le blanc sinon.
  const towards: Rgb =
    luminance(ground) > 0.5 ? { r: 0, g: 0, b: 0 } : { r: 255, g: 255, b: 255 };

  const mix = (amount: number): Rgb => ({
    r: source.r + (towards.r - source.r) * amount,
    g: source.g + (towards.g - source.g) * amount,
    b: source.b + (towards.b - source.b) * amount,
  });

  let low = 0;
  let high = 1;
  let best: string | null = null;

  for (let step = 0; step < 20; step += 1) {
    const middle = (low + high) / 2;
    const candidate = toHex(mix(middle));
    const ratio = contrastRatio(candidate, background) ?? 0;

    if (ratio >= target) {
      // Assez lisible : on essaie de moins dénaturer la couleur.
      best = candidate;
      high = middle;
    } else {
      low = middle;
    }
  }

  return best;
}
