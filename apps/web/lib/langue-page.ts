/**
 * La langue de la page, à joindre aux appels de l'API faits depuis le
 * navigateur.
 *
 * C'est elle, et non celle du navigateur, qui décide de la langue des
 * réponses : messages d'erreur, fil d'activité, et ce que le serveur retient
 * sur le compte. Un visiteur qui lit une page française sur un navigateur
 * réglé en anglais doit recevoir ses erreurs en français — et l'inverse.
 * Sans cet en-tête, le navigateur enverrait sa propre préférence.
 *
 * `Accept-Language` est un en-tête que les navigateurs laissent passer
 * entre domaines sans négociation préalable : l'ajouter ne change rien aux
 * règles CORS de l'API.
 */
export function langueDeLaPage(): Record<string, string> {
  if (typeof document === "undefined" || !document.documentElement.lang) return {};
  return { "Accept-Language": document.documentElement.lang };
}
