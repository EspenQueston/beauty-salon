import { notFound } from "next/navigation";

import { VerifierEmailCliente } from "@/features/client/VerifierEmailCliente";
import { fetchSalon } from "@/lib/salon-serveur";

type Props = { params: Promise<{ host: string }> };

export const metadata = {
  title: "Confirmer mon adresse e-mail",
  // Le jeton est dans l'adresse : ni indexation, ni en-tete Referer.
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

/** Page ouverte depuis l'e-mail de confirmation d'adresse d'une cliente. */
export default async function VerifierEmailPage({ params }: Props) {
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();
  return <VerifierEmailCliente salon={salon} host={host} />;
}
