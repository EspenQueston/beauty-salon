import { adjustForContrast } from "./contrast";
import type { PublicService, ThemeConfig } from "./types";

const LOCALE = "fr-FR";

/**
 * Les montants XAF et CDF n'ont pas de decimales dans l'usage courant :
 * afficher « 25 000 FCFA » plutot que « 25 000,00 » evite de faire passer
 * un tarif simple pour un devis comptable.
 */
const ZERO_DECIMAL = new Set(["XAF", "CDF", "JPY"]);

export function formatPrice(amount: string | number, currency: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  const digits = ZERO_DECIMAL.has(currency) ? 0 : 2;

  return new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatServicePrice(service: PublicService, currency: string): string {
  if (service.price_kind === "quote") return "Sur devis";
  const price = formatPrice(service.price_amount, currency);
  return service.price_kind === "from" ? `À partir de ${price}` : price;
}

export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  if (rest === 0) return `${hours} h`;
  return `${hours} h ${rest.toString().padStart(2, "0")}`;
}

/** Heure locale du salon, quel que soit le fuseau de la visiteuse. */
export function formatTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat(LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(new Date(iso));
}

export function formatDate(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat(LOCALE, {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone,
  }).format(new Date(iso));
}

export function formatDayKey(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone,
  }).format(new Date(iso));
}

/**
 * Le jour du calendrier, tel que le salon le vit.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ce n'est pas `new Date().toISOString().slice(0, 10)`
 * ---------------------------------------------------------------------------
 *
 * Parce que cette formule-là donne la date **UTC**, et qu'aucun salon ne vit
 * à UTC. À Shanghai il est déjà 1 h du matin le 16 quand le serveur croit
 * encore être le 15 : une recette du 16 tombe alors hors de la fenêtre
 * « jusqu'à aujourd'hui », et l'écran des comptes affiche un montant amputé
 * pendant huit heures chaque nuit. À Brazzaville le décalage est d'une heure,
 * et il déplace la frontière de minuit à 23 h.
 *
 * C'est un bogue qui ne se voit jamais depuis un poste réglé sur UTC — donc
 * jamais en développement, et tous les soirs en production.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi le fuseau du salon, et non celui du navigateur
 * ---------------------------------------------------------------------------
 *
 * La gérante consulte parfois ses comptes en voyage. Ses livres ne doivent
 * pas changer de bornes parce qu'elle a changé de pays : la journée
 * comptable est celle du salon, pas celle de qui la regarde.
 *
 * `en-CA` est le seul format qu'`Intl` produit déjà en ISO (2026-09-16), ce
 * qui évite de recomposer la date à la main.
 */
export function isoDateIn(timeZone: string, shiftDays = 0): string {
  const today = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone,
  }).format(new Date());

  if (!shiftDays) return today;

  // Arithmétique de calendrier, pas d'horloge : décaler de N × 24 h en
  // millisecondes se décale d'un jour entier lors d'un changement d'heure
  // d'été. `Date.UTC` sur une date nue ne peut pas dériver.
  const [year, month, day] = today.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + shiftDays))
    .toISOString()
    .slice(0, 10);
}

const WEEKDAYS = [
  "Lundi",
  "Mardi",
  "Mercredi",
  "Jeudi",
  "Vendredi",
  "Samedi",
  "Dimanche",
];

export function weekdayLabel(index: number): string {
  return WEEKDAYS[index] ?? "";
}

/** "09:00:00" -> "09:00" */
export function shortTime(value: string): string {
  return value.slice(0, 5);
}

/**
 * Traduit le theme du salon en variables CSS.
 *
 * Seules les cles connues sont lues, et elles sont validees cote API : un
 * JSON de theme ne doit pas pouvoir injecter de CSS arbitraire dans la page.
 */
export function themeToCssVars(theme: ThemeConfig): Record<string, string> {
  const vars: Record<string, string> = {};
  if (isSafeColor(theme.primary)) vars["--salon-primary"] = theme.primary!;
  if (isSafeColor(theme.accent)) vars["--salon-accent"] = theme.accent!;
  if (isSafeColor(theme.surface)) vars["--salon-surface"] = theme.surface!;
  if (theme.radius && /^[0-9.]+(px|rem|em)$/.test(theme.radius)) {
    vars["--salon-radius"] = theme.radius;
  }

  /*
    Les deux encres posées sur un fond clair.

    Elles sont calculées ici, et pas dans la feuille de style, parce qu'ici
    on connaît les couleurs réelles : on peut mesurer le contraste au lieu
    de l'estimer. `adjustForContrast` ne fonce la teinte du salon que si
    elle en a besoin, et seulement du strict nécessaire — sur les dix
    palettes proposées, sept passent déjà et ressortent inchangées.

    Le repli de `app/globals.css`, lui, assombrit à l'aveugle : il ne voit
    pas l'accent. Voir le commentaire qui accompagne `--salon-ink-accent`.
  */
  const marque = isSafeColor(theme.primary) ? theme.primary! : PRIMAIRE_PAR_DEFAUT;
  if (isSafeColor(theme.accent)) {
    vars["--salon-ink-accent"] = encreSurFondClair(marque, theme.accent!);
  }
  if (isSafeColor(theme.primary)) {
    vars["--salon-ink-white"] = encreSurFondClair(marque, "#ffffff");
  }

  return vars;
}

/**
 * La couleur de marque par défaut, celle de `--salon-primary` dans
 * `app/globals.css`. Elle sert de base quand le salon a choisi une couleur
 * secondaire sans toucher à sa couleur principale.
 */
const PRIMAIRE_PAR_DEFAUT = "#b4436c";

/**
 * La couleur de marque, rendue lisible sur un fond clair donné.
 *
 * Le seuil est celui du texte courant (4,5:1) et non celui des icônes (3:1) :
 * ces deux variables habillent aussi bien la pastille « Acompte » que le
 * bouton « Réserver maintenant ». Viser le seuil le plus exigeant des deux
 * évite d'avoir à se demander, à chaque usage, lequel s'applique.
 *
 * `adjustForContrast` rend `null` quand le contraste est déjà suffisant : la
 * couleur du salon passe alors telle quelle, sans être dénaturée.
 */
function encreSurFondClair(marque: string, fond: string): string {
  return adjustForContrast(marque, fond, 4.5) ?? marque;
}

function isSafeColor(value?: string): boolean {
  return !!value && /^#[0-9a-fA-F]{3,8}$/.test(value);
}
