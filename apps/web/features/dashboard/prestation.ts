/**
 * Le formulaire d'une prestation, sans React : validation, détection des
 * modifications, corps de la requête.
 *
 * Tenu à part pour deux raisons : l'écran et ses tests lisent les mêmes
 * règles (`tests/prestation.test.mjs`, lancé par `node --test`), et ces
 * règles reprennent celles du serveur (`catalog/models.py`) — nom de 150
 * caractères au plus, durée d'au moins 5 minutes, prix jamais négatif. Le
 * serveur reste juge ; ceci évite seulement un aller-retour pour une erreur
 * que l'écran peut voir.
 */

export type TypeTarif = "fixed" | "from" | "quote";
export type Lieu = "salon" | "home" | "hybrid";

export interface ValeursPrestation {
  id?: string;
  category?: string;
  name?: string;
  description?: string;
  duration_minutes?: number | string;
  price_kind?: TypeTarif;
  price_amount?: string;
  requires_deposit?: boolean;
  location_mode?: Lieu;
  active?: boolean;
  image?: string | null;
}

export type ErreursPrestation = Partial<
  Record<"name" | "category" | "duration_minutes" | "price_amount", string>
>;

export const NOM_MAX = 150;
export const DUREE_MIN = 5;
export const DUREE_MAX = 24 * 60;

/** Les erreurs visibles avant l'envoi, champ par champ. Vide : on peut envoyer. */
export function validerPrestation(valeurs: ValeursPrestation): ErreursPrestation {
  const erreurs: ErreursPrestation = {};
  const nom = (valeurs.name ?? "").trim();
  if (!nom) erreurs.name = "Donnez un nom à la prestation.";
  else if (nom.length > NOM_MAX) erreurs.name = `${NOM_MAX} caractères au plus.`;

  if (!valeurs.category) erreurs.category = "Choisissez une catégorie.";

  const duree = Number(valeurs.duration_minutes);
  if (!Number.isInteger(duree) || duree < DUREE_MIN) {
    erreurs.duration_minutes = `Au moins ${DUREE_MIN} minutes, en nombre entier.`;
  } else if (duree > DUREE_MAX) {
    erreurs.duration_minutes = "Une prestation dure au plus 24 heures.";
  }

  if (valeurs.price_kind !== "quote") {
    const brut = String(valeurs.price_amount ?? "").trim();
    const prix = Number(brut);
    if (brut === "" || !Number.isFinite(prix)) erreurs.price_amount = "Indiquez un prix.";
    else if (prix < 0) erreurs.price_amount = "Le prix ne peut pas être négatif.";
  }
  return erreurs;
}

/** Ce que l'écran envoie : les seuls champs modifiables, normalisés. */
export function corpsPrestation(valeurs: ValeursPrestation) {
  return {
    category: valeurs.category,
    name: (valeurs.name ?? "").trim(),
    description: (valeurs.description ?? "").trim(),
    duration_minutes: Number(valeurs.duration_minutes),
    price_kind: valeurs.price_kind ?? "fixed",
    price_amount: valeurs.price_kind === "quote" ? "0" : String(valeurs.price_amount ?? "0"),
    requires_deposit: valeurs.requires_deposit ?? false,
    location_mode: valeurs.location_mode ?? "salon",
    active: valeurs.active ?? true,
    image: valeurs.image ?? null,
  };
}

/**
 * Le formulaire a-t-il été modifié depuis son ouverture ?
 *
 * Comparé sur ce qui serait envoyé : « 45 » et 45, « 12.5 » et « 12.50 »
 * ne sont pas des modifications ; un prix saisi puis remis à l'identique
 * non plus. C'est ce qui décide si fermer demande confirmation.
 */
export function estModifiee(depart: ValeursPrestation, valeurs: ValeursPrestation): boolean {
  const a = corpsPrestation(depart);
  const b = corpsPrestation(valeurs);
  return (Object.keys(a) as (keyof typeof a)[]).some((cle) => {
    if (cle === "price_amount") return Number(a[cle]) !== Number(b[cle]);
    return a[cle] !== b[cle];
  });
}

/** Le premier champ en erreur, dans l'ordre de l'écran : c'est lui qui reçoit le focus. */
export function premierChampEnErreur(erreurs: ErreursPrestation): keyof ErreursPrestation | null {
  const ordre: (keyof ErreursPrestation)[] = ["name", "category", "duration_minutes", "price_amount"];
  return ordre.find((champ) => erreurs[champ]) ?? null;
}
