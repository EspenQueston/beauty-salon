import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Waitlist } from "@/features/dashboard/Waitlist";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("listeAttente") };
}

export default function Page() {
  return <Waitlist />;
}
