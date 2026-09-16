import { notFound } from "next/navigation";

import { ClientSpace } from "@/features/client/ClientSpace";
import { fetchSalon } from "@/lib/api";

type Props = { params: Promise<{ host: string }> };

export const metadata = {
  title: "Mon espace",
  // Un espace personnel n'a rien à faire dans un index de moteur de
  // recherche : il ne montre rien d'utile à qui n'est pas connecté.
  robots: { index: false, follow: false },
};

export default async function ComptePage({ params }: Props) {
  const { host } = await params;
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  // Pas de <main> ici : connectée, la cliente voit une page normale ;
  // déconnectée, elle voit un écran d'identification plein cadre. C'est
  // `ClientSpace` qui choisit, il pose donc lui-même sa mise en page.
  return <ClientSpace salon={salon} host={host} />;
}
