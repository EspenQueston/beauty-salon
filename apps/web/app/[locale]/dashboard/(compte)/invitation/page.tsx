import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { InvitationForm } from "@/features/account/InvitationForm";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("compte.titres");
  return { title: t("invitation") };
}

export default function InvitationPage() {
  return (
    <Suspense fallback={null}>
      <InvitationForm />
    </Suspense>
  );
}
