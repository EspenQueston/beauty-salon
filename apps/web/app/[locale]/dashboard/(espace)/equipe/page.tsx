import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Team } from "@/features/dashboard/Team";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("equipe") };
}

export default function TeamPage() {
  return <Team />;
}
