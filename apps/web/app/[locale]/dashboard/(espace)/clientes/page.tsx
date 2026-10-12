import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Customers } from "@/features/dashboard/Customers";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("clientes") };
}

export default function CustomersPage() {
  return <Customers />;
}
