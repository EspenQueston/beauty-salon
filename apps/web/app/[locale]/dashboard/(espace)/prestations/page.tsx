import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Services } from "@/features/dashboard/Services";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("prestations") };
}

export default function ServicesPage() {
  return <Services />;
}
