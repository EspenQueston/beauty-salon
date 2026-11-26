import { CoquilleCompte } from "@/features/account/CoquilleCompte";

/**
 * Écrans de compte : mot de passe oublié, mot de passe à choisir, invitation.
 *
 * Sans colonne de réassurance : ces trois écrans s'adressent à quelqu'un qui a
 * déjà décidé et qui veut seulement reprendre la main sur son compte. Lui
 * montrer le produit à côté ne l'aiderait pas, ça le retiendrait.
 *
 * L'inscription, elle, a la sienne — voir
 * `app/dashboard/(creation)/inscription/layout.tsx`.
 */
export default function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <CoquilleCompte>{children}</CoquilleCompte>;
}
