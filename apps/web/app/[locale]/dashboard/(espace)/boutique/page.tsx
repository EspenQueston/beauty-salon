import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Store } from "@/features/dashboard/Store";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("boutique") };
}

export default function Page() {
  return <Store />;
}
