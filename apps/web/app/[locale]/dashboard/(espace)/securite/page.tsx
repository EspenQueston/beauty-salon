import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Securite } from "@/features/dashboard/Securite";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("securite") };
}

export default function SecuritePage() {
  return <Securite />;
}
