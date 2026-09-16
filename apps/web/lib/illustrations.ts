/**
 * Illustrations de secours, servies par Unsplash.
 *
 * Un salon qui vient de s'inscrire n'a ni photo de prestation, ni bannière,
 * ni galerie. Sans image, son mini-site ressemble à un formulaire vide et ne
 * donne envie de rien — alors même que son catalogue est correct.
 *
 * ---------------------------------------------------------------------------
 * Ce que ces images sont, et ce qu'elles ne sont pas
 * ---------------------------------------------------------------------------
 *
 * Ce sont des **illustrations d'ambiance**, jamais le travail du salon. La
 * distinction n'est pas cosmétique : une galerie s'intitule « Réalisations »,
 * et y glisser des photos prises ailleurs ferait dire à un vrai commerce
 * quelque chose de faux sur son propre travail. Partout où elles remplacent
 * une galerie vide, l'écran le dit.
 *
 * Sur une fiche de prestation ou en fond de haut de page, elles jouent le
 * rôle d'une image d'ambiance de catalogue — usage courant et sans
 * ambiguïté.
 *
 * ---------------------------------------------------------------------------
 * Choix techniques
 * ---------------------------------------------------------------------------
 *
 *   - chaque identifiant a été vérifié : l'URL répond, et le contenu de la
 *     photo a été regardé. Une image « au hasard » sur la page publique d'un
 *     vrai commerce n'est pas acceptable ;
 *   - `auto=format` laisse Unsplash servir du WebP ou de l'AVIF selon le
 *     navigateur, et `w=` borne la taille. Sur un forfait facturé à la
 *     donnée, la différence avec un JPEG pleine résolution est d'un ordre de
 *     grandeur ;
 *   - le tirage est déterministe : la même prestation garde toujours la même
 *     photo, d'une visite à l'autre et d'un rendu serveur au suivant.
 *
 * Licence Unsplash : usage libre, y compris commercial, sans autorisation
 * préalable. L'attribution n'est pas obligatoire mais reste affichée.
 */

export type IllustrationTheme =
  | "salon"
  | "hair"
  | "braids"
  | "nails"
  | "makeup"
  | "barber"
  | "care";

export interface Illustration {
  /** Identifiant de la photo sur images.unsplash.com. */
  id: string;
  alt: string;
  themes: IllustrationTheme[];
}

export const ILLUSTRATIONS: Illustration[] = [
  {
    id: "photo-1560066984-138dadb4c035",
    alt: "Intérieur d'un salon de coiffure",
    themes: ["salon", "barber"],
  },
  {
    id: "photo-1522337360788-8b13dee7a37e",
    alt: "Chevelure longue de dos",
    themes: ["hair", "care"],
  },
  {
    id: "photo-1595476108010-b4d1f102b1b1",
    alt: "Shampooing au bac",
    themes: ["care", "salon"],
  },
  {
    id: "photo-1519699047748-de8e457a634e",
    alt: "Coiffure afro",
    themes: ["braids", "hair"],
  },
  {
    id: "photo-1516975080664-ed2fc6a32937",
    alt: "Pinceaux de maquillage",
    themes: ["makeup"],
  },
  {
    id: "photo-1503951914875-452162b0f3f1",
    alt: "Rasage chez le barbier",
    themes: ["barber"],
  },
  {
    id: "photo-1600948836101-f9ffda59d250",
    alt: "Salon de coiffure contemporain",
    themes: ["salon"],
  },
  {
    id: "photo-1580618672591-eb180b1a973f",
    alt: "Brushing au brosse ronde",
    themes: ["hair", "care"],
  },
  {
    id: "photo-1562322140-8baeececf3df",
    alt: "Séchage et mise en forme",
    themes: ["hair", "salon"],
  },
  {
    id: "photo-1610992015732-2449b76344bc",
    alt: "Mains manucurées",
    themes: ["nails"],
  },
  {
    id: "photo-1521590832167-7bcbfaa6381f",
    alt: "Espace maquillage",
    themes: ["makeup", "salon"],
  },
  {
    id: "photo-1596704017254-9b121068fb31",
    alt: "Palette de fards",
    themes: ["makeup"],
  },
];

export const UNSPLASH_CREDIT = "Photos d'illustration : Unsplash";

interface UrlOptions {
  /** Largeur demandée en pixels. Unsplash redimensionne à la source. */
  width?: number;
  /** Rapport hauteur/largeur ; sans lui, la photo garde ses proportions. */
  ratio?: number;
  quality?: number;
}

export function illustrationUrl(
  id: string,
  { width = 900, ratio, quality = 62 }: UrlOptions = {},
): string {
  const params = new URLSearchParams({
    auto: "format",
    fit: "crop",
    w: String(width),
    q: String(quality),
  });
  if (ratio) params.set("h", String(Math.round(width * ratio)));
  return `https://images.unsplash.com/${id}?${params}`;
}

/** Hachage stable : même graine, même photo, sur le serveur comme au client. */
function hash(seed: string): number {
  let value = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    value ^= seed.charCodeAt(index);
    value = Math.imul(value, 16777619);
  }
  return Math.abs(value);
}

function pool(theme?: IllustrationTheme): Illustration[] {
  if (!theme) return ILLUSTRATIONS;
  const matching = ILLUSTRATIONS.filter((entry) => entry.themes.includes(theme));
  // Un thème sans photo dédiée retombe sur l'ensemble : mieux vaut une image
  // d'ambiance générique qu'un trou dans la grille.
  return matching.length > 0 ? matching : ILLUSTRATIONS;
}

export function pickIllustration(
  seed: string,
  theme?: IllustrationTheme,
): Illustration {
  const candidates = pool(theme);
  return candidates[hash(seed) % candidates.length];
}

/** Sélection sans doublon, pour remplir une grille. */
export function pickIllustrations(seed: string, count: number): Illustration[] {
  const start = hash(seed) % ILLUSTRATIONS.length;
  return Array.from({ length: Math.min(count, ILLUSTRATIONS.length) }, (_, index) =>
    ILLUSTRATIONS[(start + index) % ILLUSTRATIONS.length],
  );
}

/**
 * Thème déduit du nom d'une catégorie.
 *
 * Le vocabulaire est celui des salons visés — « vanille » désigne des
 * tresses en Afrique centrale, pas un parfum.
 */
export function themeFromCategory(name: string): IllustrationTheme {
  const key = name
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");

  if (/ongle|nail|manucure|pedicure|vernis|gel/.test(key)) return "nails";
  if (/tresse|natte|braid|locks|twist|vanille/.test(key)) return "braids";
  if (/maquillage|makeup|levre|teint|sourcil|cil/.test(key)) return "makeup";
  if (/barbe|barbier|rasage/.test(key)) return "barber";
  if (/soin|masque|traitement|hydrat|defris|lissage|shampo/.test(key)) return "care";
  if (/perruque|tissage|coupe|coiffure|meche|brushing/.test(key)) return "hair";
  return "salon";
}

/* --------------------------------------------------------------------------
 * Articles de boutique
 * ---------------------------------------------------------------------- */

/**
 * Mots-clés qui rattachent un article à une famille d'images.
 *
 * Comparés sans accents ni casse : un salon écrit « meches » aussi souvent
 * que « mèches », et refuser la première orthographe rendrait la
 * reconnaissance inutile là où elle sert le plus.
 *
 * L'ordre compte : « kit de perruque » doit tomber sur la perruque, pas sur
 * le kit générique, donc les termes les plus spécifiques passent en premier.
 */
const PRODUCT_KEYWORDS: [RegExp, IllustrationTheme][] = [
  [/perruque|wig|lace|frontal|closure/, "hair"],
  [/meche|tresse|braid|kanekalon|extension|tissage|natte/, "braids"],
  [/ongle|nail|vernis|gel|capsule|lime/, "nails"],
  [/maquillage|make.?up|fond de teint|rouge|cil|faux.cils/, "makeup"],
  [/rasoir|tondeuse|barbe|barber/, "barber"],
  [/shampo?oing|apres.shampo?oing|masque|huile|soin|creme|hydrat|kit/, "care"],
];

/** Retire les accents pour comparer « mèches » et « meches » de la même façon. */
function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/** Famille d'images qui correspond le mieux au nom d'un article. */
export function themeFromProduct(name: string): IllustrationTheme {
  const folded = fold(name);
  for (const [pattern, theme] of PRODUCT_KEYWORDS) {
    if (pattern.test(folded)) return theme;
  }
  return "salon";
}

/**
 * Image de repli pour un article sans photo.
 *
 * Une carte vide dans une boutique se lit comme un article indisponible, ou
 * comme un site inachevé. Une image d'ambiance choisie d'après le nom vaut
 * mieux : elle est stable — même article, même image, d'un affichage à
 * l'autre — et elle ressemble à ce qu'elle désigne.
 *
 * Elle ne remplace pas la vraie photo : dès que le salon en téléverse une,
 * c'est la sienne qui s'affiche.
 */
export function productIllustrationUrl(
  name: string,
  seed: string,
  options: UrlOptions = {},
): string {
  const illustration = pickIllustration(seed, themeFromProduct(name));
  return illustrationUrl(illustration.id, { width: 400, ratio: 1, ...options });
}

/**
 * Images de repli d'une **liste** d'articles, sans doublon.
 *
 * Article par article, `productIllustrationUrl` suffit. Mis côte à côte,
 * non : les familles d'images se recoupent — une photo peut appartenir à la
 * fois aux tresses et aux perruques — et le vivier par thème compte trois ou
 * quatre entrées. Deux articles voisins tombaient donc régulièrement sur la
 * même photo, ce qui se lit comme un bug d'affichage.
 *
 * Cette fonction parcourt la liste dans l'ordre et, quand une image est déjà
 * prise, avance dans le vivier du même thème jusqu'à en trouver une libre.
 * Le résultat reste stable — même liste, mêmes images — parce que rien n'y
 * est aléatoire.
 *
 * Si le thème est épuisé, on garde le doublon plutôt que d'aller chercher
 * une image hors sujet : une perruque deux fois vaut mieux qu'un fauteuil de
 * barbier sur un paquet de mèches.
 */
export function productIllustrations(
  products: { id: string; name: string }[],
  options: UrlOptions = {},
): Map<string, string> {
  const used = new Set<string>();
  const urls = new Map<string, string>();

  for (const product of products) {
    const theme = themeFromProduct(product.name);
    const candidates = pool(theme);
    const start = hash(product.id) % candidates.length;

    let chosen = candidates[start];
    for (let step = 0; step < candidates.length; step += 1) {
      const candidate = candidates[(start + step) % candidates.length];
      if (!used.has(candidate.id)) {
        chosen = candidate;
        break;
      }
    }

    used.add(chosen.id);
    urls.set(
      product.id,
      illustrationUrl(chosen.id, { width: 400, ratio: 1, ...options }),
    );
  }

  return urls;
}

/* --------------------------------------------------------------------------
 * Prestations
 * ---------------------------------------------------------------------- */

/**
 * Images de repli d'une **liste** de prestations, sans doublon.
 *
 * Même problème que pour les articles de boutique, et il se voyait encore
 * plus : un salon de tresses range toutes ses prestations dans la même
 * catégorie, donc elles tirent toutes dans le vivier « braids » — quatre
 * photos. Sur l'accueil, les quatre cartes en vedette affichaient la même
 * image, ce qui ne se lit pas comme une illustration mais comme un défaut de
 * chargement.
 *
 * Le parcours est le même : on avance dans le vivier du thème jusqu'à
 * trouver une image libre, et l'on garde le doublon si le thème est épuisé —
 * une seconde photo de tresses vaut mieux qu'une palette de fards sur une
 * prestation capillaire.
 *
 * Déterministe : même liste, mêmes images, du rendu serveur à l'hydratation.
 */
export function serviceIllustrations(
  services: { id: string; theme: IllustrationTheme }[],
): Map<string, Illustration> {
  const used = new Set<string>();
  const chosen = new Map<string, Illustration>();

  for (const service of services) {
    /*
      Trois passes, de la plus juste à la plus tolérante.

      Chercher directement dans le vivier élargi, en partant d'un index tiré
      au hasard, donnait le pire des deux mondes : une carte « Cornrows »
      héritait d'un espace maquillage pendant que l'unique photo de tresses
      restait inutilisée. L'ordre compte plus que le tirage.
    */
    const propre = pool(service.theme);
    const start = hash(service.id) % propre.length;

    // 1. Sa propre famille, en partant du tirage stable — c'est lui qui fait
    //    qu'une prestation garde la même photo d'une visite à l'autre.
    let pick: Illustration | undefined;
    for (let step = 0; step < propre.length; step += 1) {
      const candidate = propre[(start + step) % propre.length];
      if (!used.has(candidate.id)) {
        pick = candidate;
        break;
      }
    }

    // 2. Famille épuisée : on descend chez les voisins, dans l'ordre — donc
    //    du plus proche au plus lointain, jamais au hasard.
    pick ??= vivierElargi(service.theme).find(
      (candidate) => !used.has(candidate.id),
    );

    // 3. Tout est pris : on répète. Deux fois la bonne image vaut mieux
    //    qu'une image hors sujet sur la vitrine d'un vrai commerce.
    pick ??= propre[start];

    used.add(pick.id);
    chosen.set(service.id, pick);
  }

  return chosen;
}

/**
 * Familles voisines, par ordre de parenté.
 *
 * Le vivier d'un thème est parfois plus petit que la grille qu'il doit
 * remplir : « braids » ne compte qu'une photo, et un salon de tresses affiche
 * quatre prestations en vedette. Quatre fois la même image, ce n'est pas une
 * illustration, c'est un défaut d'affichage.
 *
 * Plutôt que de répéter, on descend vers les familles voisines. L'ordre n'est
 * pas décoratif : sur une carte « Cornrows », une seconde photo de chevelure
 * passe inaperçue, un flacon de vernis se remarque immédiatement — et se lit
 * comme une erreur du salon, pas du gabarit.
 */
const VOISINS: Record<IllustrationTheme, IllustrationTheme[]> = {
  braids: ["hair", "care", "salon"],
  hair: ["braids", "care", "salon"],
  care: ["hair", "salon"],
  barber: ["hair", "salon"],
  salon: ["hair", "care"],
  nails: ["salon"],
  makeup: ["salon"],
};

/**
 * Le vivier d'un thème, prolongé par celui de ses voisins.
 *
 * Les doublons sont retirés en conservant le premier passage : les photos du
 * thème demandé restent donc en tête, et ce sont elles qui sont servies tant
 * qu'il en reste.
 */
function vivierElargi(theme: IllustrationTheme): Illustration[] {
  const vus = new Set<string>();
  const liste: Illustration[] = [];

  for (const famille of [theme, ...VOISINS[theme]]) {
    for (const entree of pool(famille)) {
      if (vus.has(entree.id)) continue;
      vus.add(entree.id);
      liste.push(entree);
    }
  }

  return liste;
}
