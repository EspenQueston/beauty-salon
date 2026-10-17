import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Billing } from "@/features/dashboard/Billing";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("abonnement") };
}

export default function BillingPage() {
  return <Billing />;
}
