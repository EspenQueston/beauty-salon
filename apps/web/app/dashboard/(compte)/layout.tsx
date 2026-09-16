import { AuthShell } from "@/features/ui/AuthShell";
import { ToastProvider } from "@/features/ui/Toast";
import { ThemeToggle } from "@/features/ui/ThemeToggle";
import { platformUrl } from "@/lib/site";

/**
 * Écrans de compte : inscription, mot de passe oublié, invitation.
 *
 * Ils vivent sous le même hôte que l'espace professionnel — c'est là que la
 * session doit s'ouvrir — mais en dehors de sa coquille, puisque personne
 * n'est encore connecté.
 *
 * Ni menu ni pied de page : sur un écran d'identification, tout ce qui est
 * cliquable et qui n'est pas le formulaire est une occasion d'abandonner.
 * Le retour au site reste, en une seule sortie explicite — `app.` et le site
 * public sont deux hôtes différents, un lien relatif ramènerait ici.
 */
export default function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ToastProvider>
      <AuthShell
        homeHref={platformUrl}
        action={<ThemeToggle />}
        brand={
          <>
            <span className="inline-flex size-8 items-center justify-center rounded-xl bg-salon text-sm font-semibold text-white">
              BS
            </span>
            <span className="font-semibold tracking-tight text-ink">
              Beauty Salon
            </span>
          </>
        }
      >
        {children}
      </AuthShell>
    </ToastProvider>
  );
}
