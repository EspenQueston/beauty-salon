import { notFound } from "next/navigation";

import { MotDePasse } from "@/features/client/MotDePasse";
import { fetchSalon } from "@/lib/salon-serveur";

type Props = {
  params: Promise<{ host: string }>;
  searchParams: Promise<{ uid?: string; token?: string }>;
};

export const metadata = {
  title: "Nouveau mot de passe",
  // Le jeton est dans l'adresse : elle ne doit ni s'indexer, ni partir
  // en en-tete Referer vers une autre origine.
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

/** Page ouverte depuis l'e-mail : le nouveau mot de passe de la cliente. */
export default async function NouveauMotDePassePage({ params, searchParams }: Props) {
  const [{ host }, query] = await Promise.all([params, searchParams]);
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  return (
    <MotDePasse
      salon={salon}
      host={host}
      mode="nouveau"
      uid={query.uid ?? ""}
      token={query.token ?? ""}
    />
  );
}
