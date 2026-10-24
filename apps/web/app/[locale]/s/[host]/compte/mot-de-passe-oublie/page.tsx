import { notFound } from "next/navigation";

import { MotDePasse } from "@/features/client/MotDePasse";
import { fetchSalon } from "@/lib/salon-serveur";

type Props = { params: Promise<{ host: string }> };

export const metadata = {
  title: "Mot de passe oublié",
  robots: { index: false, follow: false },
};

/** Demande d'un lien pour choisir un nouveau mot de passe (espace cliente). */
export default async function MotDePasseOubliePage({ params }: Props) {
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  return <MotDePasse salon={salon} host={host} mode="demande" />;
}
