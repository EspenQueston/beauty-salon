import { notFound } from "next/navigation";

import { PaymentPage } from "@/features/booking/PaymentPage";
import { fetchSalon } from "@/lib/salon-serveur";

type Props = {
  params: Promise<{ host: string }>;
  searchParams: Promise<{ token?: string }>;
};

export const metadata = {
  title: "Régler l'acompte",
  // Un lien de paiement porte un jeton : il n'a rien à faire dans un index.
  robots: { index: false, follow: false },
};

export default async function Page({ params, searchParams }: Props) {
  const [{ host }, query] = await Promise.all([params, searchParams]);
  const salon = await fetchSalon(host);
  if (!salon) notFound();

  return (
    <main className="mx-auto w-full max-w-4xl px-4 pb-12 pt-24 sm:pb-16 sm:pt-28">
      <PaymentPage
        host={host}
        token={query.token ?? ""}
        currency={salon.currency}
        timeZone={salon.timezone}
        salonName={salon.name}
      />
    </main>
  );
}
