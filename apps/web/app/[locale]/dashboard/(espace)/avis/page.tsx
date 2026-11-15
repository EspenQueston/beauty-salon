import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Reviews } from "@/features/dashboard/Reviews";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("avis") };
}

export default function ReviewsPage() {
  return <Reviews />;
}
