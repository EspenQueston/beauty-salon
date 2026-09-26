import { Suspense } from "react";

import { Agenda } from "@/features/dashboard/Agenda";

/**
 * L'agenda lit l'URL — d'où la frontière de suspension.
 *
 * Depuis que la cloche y renvoie avec `?rdv=` ou `?attente=`, le composant
 * appelle `useSearchParams()`. Sur une route prérendue, ce hook fait basculer
 * tout l'arbre au-dessus de la plus proche frontière `<Suspense>` en rendu
 * côté client — sans frontière, c'est la page entière, et la construction s'en
 * plaint.
 *
 * Elle est ici et pas plus haut pour que la coquille du tableau de bord —
 * navigation, barre du haut, cloche — reste prérendue et s'affiche
 * immédiatement.
 */
export default function AgendaPage() {
  return (
    <Suspense fallback={null}>
      <Agenda />
    </Suspense>
  );
}
