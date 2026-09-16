import { DashboardShell } from "@/features/dashboard/DashboardShell";

export const metadata = { title: "Espace professionnel" };

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
