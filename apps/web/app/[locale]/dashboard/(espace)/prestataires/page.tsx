import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { StaffMembers } from "@/features/dashboard/StaffMembers";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("prestataires") };
}

export default function StaffPage() {
  return <StaffMembers />;
}
