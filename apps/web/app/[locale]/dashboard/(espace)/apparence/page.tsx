import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Apparence } from "@/features/dashboard/Apparence";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("apparence") };
}

export default function ApparencePage() {
  return <Apparence />;
}
