import { NextIntlClientProvider } from "next-intl";

/**
 * L'espace professionnel reçoit le catalogue de traductions complet.
 *
 * La racine n'envoie au navigateur que les sections de la page d'accueil
 * (voir `i18n/messages.ts`) ; un fournisseur imbriqué remplace celui du
 * dessus, il ne s'y ajoute pas. Sans `messages`, celui-ci envoie tout.
 */
export default function EspaceProLayout({ children }: { children: React.ReactNode }) {
  return <NextIntlClientProvider>{children}</NextIntlClientProvider>;
}
