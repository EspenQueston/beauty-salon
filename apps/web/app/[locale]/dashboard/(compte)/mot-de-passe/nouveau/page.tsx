import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { NewPasswordForm } from "@/features/account/PasswordForms";

// Le jeton est dans l'adresse : il ne doit pas partir en en-tete Referer.
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("compte.titres");
  return { title: t("nouveau"), referrer: "no-referrer" };
}

export default function NewPasswordPage() {
  // useSearchParams impose une frontiere Suspense au prerendu.
  return (
    <Suspense fallback={null}>
      <NewPasswordForm />
    </Suspense>
  );
}
