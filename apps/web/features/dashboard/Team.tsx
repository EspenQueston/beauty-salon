"use client";

/**
 * Équipe du salon : membres et invitations.
 *
 * C'est l'écran qui rend un salon autonome. Sans lui, ajouter une
 * réceptionniste imposerait de passer par l'administration de la plateforme.
 */

import { useTranslations } from "next-intl";
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

/** Libellés et aides sous `pro.equipe.roles`. */
const ROLES = ["staff", "receptionist", "manager", "owner"];

const INVITATION_TONES: Record<
  string,
  "warning" | "success" | "neutral" | "danger"
> = {
  pending: "warning",
  accepted: "success",
  revoked: "neutral",
  expired: "danger",
};


export function Team() {
  const t = useTranslations("pro.equipe");
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
      { success: t("invitationAnnulee", { email: invitation.email }) },
    );
    if (ok) invitations.reload();
  }

  return (
    <section>
      <PageHeader
        title={t("titre")}
        description={t("description")}
      />

      {members.error && (
        <ErrorState>{t("erreur")}</ErrorState>
      )}

      <WithoutAccount staff={rows(staff.data)} />

      {canManage && (
        <InviteForm tenantId={tenantId} onInvited={invitations.reload} />
      )}

      <div className="mt-7">
        <SectionTitle>{t("membres")}</SectionTitle>
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
                      {ROLES.includes(member.role) ? t(`roles.${member.role}.libelle`) : member.role}
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
          <SectionTitle>{t("invitations")}</SectionTitle>

          {rows(invitations.data).length === 0 && invitations.data !== null && (
            <EmptyState title={t("vide.titre")}>{t("vide.corps")}</EmptyState>
          )}

          <ul className="space-y-2.5">
            {rows(invitations.data).map((invitation) => (
              <li key={invitation.id}>
                <Card>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-ink">{invitation.email}</p>
                      <p className="mt-0.5 text-sm text-muted">
                        {ROLES.includes(invitation.role)
                          ? t(`roles.${invitation.role}.libelle`)
                          : invitation.role}
                        {invitation.invited_by_name &&
                          ` · ${t("inviteePar", { nom: invitation.invited_by_name })}`}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <Badge
                        tone={INVITATION_TONES[invitation.status] ?? "neutral"}
                      >
                        {invitation.status in INVITATION_TONES
                          ? t(`statuts.${invitation.status}`)
                          : invitation.status}
                      </Badge>
                      {invitation.status === "pending" && (
                        <DangerButton
                          type="button"
                          onClick={() => revoke(invitation)}
                        >
                          {t("annuler")}
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
          {t("lectureSeule")}
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
  const t = useTranslations("pro.equipe");
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("staff");
  const [pending, setPending] = useState(false);

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
        success: t("invitationEnvoyee", { email }),
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
      <SectionTitle>{t("inviter")}</SectionTitle>

      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <Field label={t("email")} className="min-w-[16rem] flex-1">
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder={t("emailExemple")}
            required
            className={inputClass}
          />
        </Field>

        <Field label={t("role")} hint={t(`roles.${role}.aide`)} className="min-w-[12rem]">
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
            className={inputClass}
          >
            {ROLES.map((option) => (
              <option key={option} value={option}>
                {t(`roles.${option}.libelle`)}
              </option>
            ))}
          </select>
        </Field>

        <Button type="submit" pending={pending} className="mb-0.5">
          {t("envoyer")}
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
  const t = useTranslations("pro.equipe.sansCompte");
  const orphans = staff.filter((member) => !member.has_access);
  if (orphans.length === 0) return null;

  return (
    <div className="mb-5 mt-5 rounded-xl border border-line bg-surface-muted/50 p-3.5">
      <p className="text-sm text-ink">
        {t.rich("titre", {
          n: orphans.length,
          gras: (texte) => <span className="font-medium">{texte}</span>,
        })}{" "}
        <span className="text-muted">
          {orphans.map((member) => member.name).join(", ")}
        </span>
      </p>
      <p className="mt-1 text-xs text-muted">{t("aide", { n: orphans.length })}</p>
    </div>
  );
}
