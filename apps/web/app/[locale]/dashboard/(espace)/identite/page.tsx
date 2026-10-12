import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { SalonIdentityScreen } from "@/features/dashboard/SalonIdentity";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("identite") };
}

export default function Page() {
  return <SalonIdentityScreen />;
}
