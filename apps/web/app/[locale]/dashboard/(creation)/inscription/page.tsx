import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { SignupForm } from "@/features/account/SignupForm";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("compte.titres");
  return { title: t("inscription") };
}

export default function SignupPage() {
  return <SignupForm />;
}
