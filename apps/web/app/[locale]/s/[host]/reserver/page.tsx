import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { BookingFlow } from "@/features/booking/BookingFlow";
import { fetchSalon } from "@/lib/salon-serveur";

type Props = {
  params: Promise<{ host: string }>;
  searchParams: Promise<{ service?: string }>;
};

/* Le titre suit la langue de l'adresse : `export const metadata` est figé
   à la compilation et ne peut pas la connaître. */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("salon.titres");
  return { title: t("reserver") };
}

export default async function BookingPage({ params, searchParams }: Props) {
  const [{ host }, query] = await Promise.all([params, searchParams]);
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  // Arriver depuis une carte du catalogue évite de rechoisir la prestation
  // qu'on vient justement de désigner.
  return (
    <BookingFlow salon={salon} host={host} initialServiceId={query.service} />
  );
}
