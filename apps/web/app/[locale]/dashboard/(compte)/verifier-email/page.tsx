import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { VerifierEmail } from "@/features/account/VerifierEmail";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("compte.titres");
  return { title: t("verifier"), referrer: "no-referrer" };
}

export default function VerifierEmailPage() {
  return <VerifierEmail />;
}
