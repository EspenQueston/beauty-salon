import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ForgotPasswordForm } from "@/features/account/PasswordForms";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("compte.titres");
  return { title: t("oubli") };
}

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
