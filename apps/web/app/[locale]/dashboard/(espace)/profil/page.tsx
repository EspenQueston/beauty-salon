import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { SalonProfileScreen } from "@/features/dashboard/SalonProfile";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("profil") };
}

export default function ProfilePage() {
  return <SalonProfileScreen />;
}
