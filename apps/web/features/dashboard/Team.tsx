"use client";

/**
 * Équipe du salon : membres et invitations.
 *
 * C'est l'écran qui rend un salon autonome. Sans lui, ajouter une
 * réceptionniste imposerait de passer par l'administration de la plateforme.
 */

import { useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import {
  Badge,
  Button,
  Card,
  DangerButton,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  SectionTitle,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { useDashboard } from "./DashboardShell";
import { rows, useResource, type Page } from "./useResource";

interface TeamMember {
  id: string;
  role: string;
  status: string;
  user_email: string;
  user_name: string;
}

interface Invitation {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  invited_by_name: string | null;
}

const ROLES = [
  {
    value: "staff",
    label: "Prestataire",
    hint: "Voit uniquement son propre agenda.",
  },
  {
    value: "receptionist",
    label: "Réceptionniste",
    hint: "Gère les rendez-vous et les clientes.",
  },
  {
    value: "manager",
    label: "Gérant",
    hint: "Gère aussi le catalogue et l'équipe.",
  },
  {
    value: "owner",
    label: "Propriétaire",
    hint: "Accès complet, facturation comprise.",
  },
];

const ROLE_LABELS = Object.fromEntries(ROLES.map((r) => [r.value, r.label]));

const INVITATION_TONES: Record<
  string,
  "warning" | "success" | "neutral" | "danger"
> = {
  pending: "warning",
  accepted: "success",
  revoked: "neutral",
  expired: "danger",
};

const INVITATION_LABELS: Record<string, string> = {
  pending: "En attente",
  accepted: "Acceptée",
  revoked: "Annulée",
  expired: "Expirée",
};

export function Team() {
  const { membership } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const canManage = ["owner", "manager"].includes(membership.role);

  const members = useResource<Page<TeamMember>>("/api/v1/team/", tenantId);

  // Les prestataires sans compte : ils expliquent l'écart entre cette liste
  // et celle des Prestataires, que rien ne rapprochait jusqu'ici.
  const staff = useResource<
    Page<{ id: string; name: string; has_access: boolean }>
  >("/api/v1/staff-members/", tenantId);
  const invitations = useResource<Page<Invitation>>(
    "/api/v1/invitations/",
    tenantId,
    {
      enabled: canManage,
    },
  );

  async function revoke(invitation: Invitation) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/invitations/${invitation.id}/revoke/`,
          { method: "POST" },
          tenantId,
        ),
      { success: `Invitation de ${invitation.email} annulée.` },
    );
    if (ok) invitations.reload();
  }

  return (
    <section>
      <PageHeader
        title="Équipe"
        description="Qui a accès à cet espace, et avec quels droits. Réaliser des prestations ne demande pas de compte : ces deux listes ne se recouvrent pas forcément."
      />

      {members.error && (
        <ErrorState>Impossible de charger l’équipe.</ErrorState>
      )}

      <WithoutAccount staff={rows(staff.data)} />

      {canManage && (
        <InviteForm tenantId={tenantId} onInvited={invitations.reload} />
      )}

      <div className="mt-7">
        <SectionTitle>Membres</SectionTitle>
        {members.data === null && !members.error && <Skeleton rows={2} />}

        <ul className="space-y-2.5">
          {rows(members.data).map((member) => (
            <li key={member.id}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">
                      {member.user_name || member.user_email}
                    </p>
                    {member.user_name && (
                      <p className="text-sm text-muted">{member.user_email}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={member.role === "owner" ? "salon" : "neutral"}>
                      {ROLE_LABELS[member.role] ?? member.role}
                    </Badge>
                    {member.status !== "active" && (
                      <Badge tone="warning">{member.status}</Badge>
                    )}
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      </div>

      {canManage && (
        <div className="mt-8">
          <SectionTitle>Invitations</SectionTitle>

          {rows(invitations.data).length === 0 && invitations.data !== null && (
            <EmptyState title="Aucune invitation en cours">
              Les personnes invitées apparaîtront ici jusqu&apos;à ce
              qu&apos;elles rejoignent l&apos;équipe.
            </EmptyState>
          )}

          <ul className="space-y-2.5">
            {rows(invitations.data).map((invitation) => (
              <li key={invitation.id}>
                <Card>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-ink">{invitation.email}</p>
                      <p className="mt-0.5 text-sm text-muted">
                        {ROLE_LABELS[invitation.role] ?? invitation.role}
                        {invitation.invited_by_name &&
                          ` · invitée par ${invitation.invited_by_name}`}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <Badge
                        tone={INVITATION_TONES[invitation.status] ?? "neutral"}
                      >
                        {INVITATION_LABELS[invitation.status] ??
                          invitation.status}
                      </Badge>
                      {invitation.status === "pending" && (
                        <DangerButton
                          type="button"
                          onClick={() => revoke(invitation)}
                        >
                          Annuler
                        </DangerButton>
                      )}
                    </div>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!canManage && (
        <p className="mt-6 text-sm text-muted">
          Seuls le propriétaire et le gérant peuvent inviter de nouvelles
          personnes.
        </p>
      )}
    </section>
  );
}

function InviteForm({
  tenantId,
  onInvited,
}: {
  tenantId: string;
  onInvited: () => void;
}) {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("staff");
  const [pending, setPending] = useState(false);

  const selected = ROLES.find((r) => r.value === role);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);

    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/invitations/",
          { method: "POST", body: JSON.stringify({ email, role }) },
          tenantId,
        ),
      {
        success: `Invitation envoyée à ${email}. Le lien est valable 7 jours.`,
      },
    );

    setPending(false);
    if (ok) {
      setEmail("");
      onInvited();
    }
  }

  return (
    <Card>
      <SectionTitle>Inviter quelqu&apos;un</SectionTitle>

      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <Field label="E-mail" className="min-w-[16rem] flex-1">
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="prenom@exemple.com"
            required
            className={inputClass}
          />
        </Field>

        <Field label="Rôle" hint={selected?.hint} className="min-w-[12rem]">
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
            className={inputClass}
          >
            {ROLES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>

        <Button type="submit" pending={pending} className="mb-0.5">
          Envoyer l&apos;invitation
        </Button>
      </form>
    </Card>
  );
}

/**
 * Le pont entre « Équipe » et « Prestataires ».
 *
 * Les deux écrans listaient des personnes sans jamais se référencer, et un
 * salon qui voit trois coiffeuses d'un côté et un seul membre de l'autre
 * conclut au bug. Il n'y en a pas : une coiffeuse figure à l'agenda sans
 * jamais se connecter, et c'est voulu — on ne force personne à créer un
 * compte pour être planifiée.
 *
 * Ce bloc l'écrit, et propose le geste qui manquait : inviter.
 */
function WithoutAccount({
  staff,
}: {
  staff: { id: string; name: string; has_access: boolean }[];
}) {
  const orphans = staff.filter((member) => !member.has_access);
  if (orphans.length === 0) return null;

  return (
    <div className="mt-5 rounded-xl border border-line bg-surface-muted/50 p-3.5">
      <p className="text-sm text-ink">
        <span className="font-medium">
          {orphans.length} prestataire{orphans.length > 1 ? "s" : ""}
        </span>{" "}
        {orphans.length > 1 ? "n'ont" : "n'a"} pas de compte :{" "}
        <span className="text-muted">
          {orphans.map((member) => member.name).join(", ")}
        </span>
      </p>
      <p className="mt-1 text-xs text-muted">
        {orphans.length > 1 ? "Elles apparaissent" : "Elle apparaît"} à
        l&apos;agenda et à la réservation sans se connecter. Invitez-
        {orphans.length > 1 ? "les" : "la"} ci-dessus seulement si{" "}
        {orphans.length > 1 ? "elles doivent" : "elle doit"} ouvrir cet espace.
      </p>
    </div>
  );
}
