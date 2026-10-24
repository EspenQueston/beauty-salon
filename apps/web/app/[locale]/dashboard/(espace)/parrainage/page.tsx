import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Parrainage } from "@/features/dashboard/Parrainage";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("parrainage") };
}

export default function ParrainagePage() {
  return <Parrainage />;
}
