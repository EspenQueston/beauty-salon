import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Schedule } from "@/features/dashboard/Schedule";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("horaires") };
}

export default function SchedulePage() {
  return <Schedule />;
}
