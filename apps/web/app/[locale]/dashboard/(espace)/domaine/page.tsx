import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { DomainePerso } from "@/features/dashboard/DomainePerso";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("domaine") };
}

export default function DomainePage() {
  return <DomainePerso />;
}
