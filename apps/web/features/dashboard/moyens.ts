/**
 * Les moyens d’encaissement des acomptes : leurs noms, et comment ils se règlent.
 *
 * Le salon encaisse sur son propre compte — la plateforme n'est jamais sur
 * le chemin de l'argent. En Chine, c'est un QR code WeChat Pay ou Alipay ;
 * à Douala, Brazzaville ou Kinshasa, un numéro Mobile Money que la cliente
 * compose à la main, ou un virement.
 */

/** Les marques s'écrivent telles quelles, dans toutes les langues. */
const MARQUES: Record<string, string> = {
  wechat: "WeChat Pay",
  alipay: "Alipay",
  mobile_money: "Mobile Money",
  orange_money: "Orange Money",
  airtel_money: "Airtel Money",
};

/** Le nom d'un moyen ; `virement` est le libellé traduit du virement bancaire. */
export function nomDuMoyen(kind: string, virement: string): string {
  return MARQUES[kind] ?? (kind === "bank" ? virement : kind);
}

/**
 * Les moyens qui se règlent avec un numéro (ou des coordonnées) plutôt
 * qu'un QR code : le QR y reste possible, mais facultatif.
 */
export function parNumero(kind: string): boolean {
  return kind !== "wechat" && kind !== "alipay";
}
