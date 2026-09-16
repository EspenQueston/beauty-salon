import { notFound } from "next/navigation";

import { BookingStatus } from "@/features/booking/BookingStatus";
import { fetchSalon } from "@/lib/api";

type Props = {
  params: Promise<{ host: string }>;
  searchParams: Promise<{ token?: string }>;
};

export const metadata = {
  title: "Mon rendez-vous",
  // Un lien de suivi porte un jeton : il n'a rien à faire dans un index.
  robots: { index: false, follow: false },
};

export default async function Page({ params, searchParams }: Props) {
  const [{ host }, query] = await Promise.all([params, searchParams]);
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  return (
    <main className="mx-auto w-full max-w-4xl px-4 pb-12 pt-24 sm:pb-16 sm:pt-28">
      <BookingStatus salon={salon} host={host} token={query.token ?? ""} />
    </main>
  );
}
