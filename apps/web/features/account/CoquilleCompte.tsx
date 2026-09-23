/**
 * La coquille des écrans de compte.
 *
 * Ces écrans — inscription, mot de passe oublié, invitation — vivent sous le
 * même hôte que l'espace professionnel, c'est là que la session doit s'ouvrir,
 * mais en dehors de sa coquille puisque personne n'est encore connecté.
 *
 * Ni menu ni pied de page : sur un écran d'identification, tout ce qui est
 * cliquable et qui n'est pas le formulaire est une occasion d'abandonner. Le
 * retour au site reste, en une seule sortie explicite — `app.` et le site
 * public sont deux hôtes différents, un lien relatif ramènerait ici.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi ce composant existe, plutôt qu'une mise en page unique
 * ---------------------------------------------------------------------------
 *
 * L'inscription a besoin d'une colonne de réassurance — le film, ce qu'on
 * obtient — et les autres écrans non : un film sur une page de réinitialisation
 * de mot de passe est du bruit devant quelqu'un qui cherche à récupérer son
 * compte.
 *
 * Or une mise en page Next ne sait pas quelle page elle enveloppe. Plutôt que
 * de lui faire deviner l'URL, l'inscription vit dans son propre groupe de
 * routes avec sa propre mise en page, et les deux partagent ce composant-ci.
 * Le chemin servi reste `/dashboard/inscription`.
 */

import type { ReactNode } from "react";

import { AuthShell } from "@/features/ui/AuthShell";
import { ThemeToggle } from "@/features/ui/ThemeToggle";
import { ToastProvider } from "@/features/ui/Toast";
import { platformUrl } from "@/lib/site";

export function CoquilleCompte({
  children,
  aside,
}: {
  children: ReactNode;
  /** Colonne de réassurance, à droite sur grand écran et dessous sinon. */
  aside?: ReactNode;
}) {
  return (
    <ToastProvider>
      <AuthShell
        homeHref={platformUrl}
        action={<ThemeToggle />}
        aside={aside}
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
