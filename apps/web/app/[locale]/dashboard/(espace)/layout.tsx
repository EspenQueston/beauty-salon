import { DashboardShell } from "@/features/dashboard/DashboardShell";
import { Installer } from "@/features/ui/Installer";

export const metadata = { title: "Espace professionnel" };

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <DashboardShell>{children}</DashboardShell>

      {/*
        L'invitation à installer, ici plus qu'ailleurs.

        Une gérante ouvre cet écran plusieurs fois par jour, souvent d'une
        main, entre deux clientes. Posé sur l'écran d'accueil, il s'ouvre en
        un geste au lieu de trois — et sans la barre d'adresse, qui mange un
        dixième de la hauteur sur un téléphone.

        Elle n'apparaît qu'à la deuxième visite, et une seule fois.
      */}
      <Installer nom="votre espace" />
    </>
  );
}
