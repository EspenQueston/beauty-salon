import { Suspense } from "react";

import { InvitationForm } from "@/features/account/InvitationForm";

export const metadata = { title: "Invitation" };

export default function InvitationPage() {
  return (
    <Suspense fallback={<p className="text-sm">Chargement…</p>}>
      <InvitationForm />
    </Suspense>
  );
}
