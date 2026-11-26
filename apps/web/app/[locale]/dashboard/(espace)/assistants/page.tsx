import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Assistants } from "@/features/dashboard/Assistants";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("assistants") };
}

export default function AssistantsPage() {
  return <Assistants />;
}
