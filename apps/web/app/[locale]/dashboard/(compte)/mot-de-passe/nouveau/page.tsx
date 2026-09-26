import { Suspense } from "react";

import { NewPasswordForm } from "@/features/account/PasswordForms";

export const metadata = { title: "Nouveau mot de passe" };

export default function NewPasswordPage() {
  // useSearchParams impose une frontiere Suspense au prerendu.
  return (
    <Suspense fallback={<p className="text-sm">Chargement…</p>}>
      <NewPasswordForm />
    </Suspense>
  );
}
