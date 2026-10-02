import { Suspense } from "react";

import { NewPasswordForm } from "@/features/account/PasswordForms";

// Le jeton est dans l'adresse : il ne doit pas partir en en-tete Referer.
export const metadata = { title: "Nouveau mot de passe", referrer: "no-referrer" };

export default function NewPasswordPage() {
  // useSearchParams impose une frontiere Suspense au prerendu.
  return (
    <Suspense fallback={<p className="text-sm">Chargement…</p>}>
      <NewPasswordForm />
    </Suspense>
  );
}
