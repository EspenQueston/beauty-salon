import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Finances } from "@/features/dashboard/Finances";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("comptes") };
}

export default function Page() {
  return <Finances />;
}
