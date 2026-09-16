import { notFound } from "next/navigation";

import { BookingFlow } from "@/features/booking/BookingFlow";
import { fetchSalon } from "@/lib/api";

type Props = {
  params: Promise<{ host: string }>;
  searchParams: Promise<{ service?: string }>;
};

export const metadata = { title: "Réserver" };

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
