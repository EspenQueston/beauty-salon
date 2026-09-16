"use client";

/**
 * Prestataires et compétences.
 *
 * Les compétences ne sont pas décoratives : le moteur de créneaux ne propose
 * une personne que pour les prestations qu'elle sait faire. Un prestataire
 * sans compétence n'apparaît nulle part à la réservation — l'écran le dit
 * franchement plutôt que de laisser découvrir le problème côté cliente.
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
  GhostButton,
  PageHeader,
  Skeleton,
  Toggle,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { Icon } from "./icons";
import { useDashboard } from "./DashboardShell";
import { MediaPicker, type PickableMedia } from "./MediaPicker";
import { rows, useResource, type Page } from "./useResource";

interface StaffService {
  id: string;
  name: string;
}

interface StaffMember {
  id: string;
  name: string;
  specialty: string;
  bio: string;
  photo: string | null;
  active: boolean;
  services: StaffService[];
  /** A-t-elle un compte pour ouvrir cet espace ? */
  has_access: boolean;
  access_email: string;
}

interface Service {
  id: string;
  name: string;
  category_name: string;
}

export function StaffMembers() {
  const { membership } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const canEdit = ["owner", "manager"].includes(membership.role);

  const staff = useResource<Page<StaffMember>>(
    "/api/v1/staff-members/?page_size=100",
    tenantId,
  );
  const services = useResource<Page<Service>>("/api/v1/services/?page_size=200", tenantId);

  const [editing, setEditing] = useState<Partial<StaffMember> | null>(null);

  // La réserve de médias sert au choix du portrait. Chargée ici plutôt que
  // dans le formulaire : un téléversement doit rafraîchir la liste sans
  // remonter le composant, ce qui perdrait la saisie en cours.
  const media = useResource<Page<PickableMedia>>(
    "/api/v1/media/?page_size=100",
    tenantId,
  );

  const staffRows = rows(staff.data);
  const serviceRows = rows(services.data);

  async function remove(member: StaffMember) {
    /*
      Le serveur décide, et dit ce qu'il a fait.
      
      Trois issues possibles : suppression réelle si la personne n'a jamais
      eu de rendez-vous, retrait de la liste si elle n'en a que des passés,
      refus motivé s'il en reste à venir. Le message vient de l'API plutôt
      que d'ici : lui seul connaît le nombre exact et la date du prochain,
      et un texte figé côté navigateur mentirait dans deux cas sur trois.
    */
    try {
      const result = await dashboardFetch<{ detail?: string; code?: string }>(
        `/api/v1/staff-members/${member.id}/`,
        { method: "DELETE" },
        tenantId,
      );
      toast.success(result?.detail ?? `${member.name} retiré de la liste.`);
      staff.reload();
    } catch (caught) {
      toast.error(
        caught instanceof Error
          ? caught.message
          : `${member.name} n'a pas pu être retiré.`,
      );
    }
  }

  return (
    <section>
      <PageHeader
        title="Prestataires"
        description="Qui réalise les prestations, et lesquelles. Une fiche suffit pour l’agenda : le compte pour se connecter est distinct, et se donne depuis Équipe."
        action={
          canEdit && (
            <Button
              type="button"
              icon={<Icon name="plus" className="size-4" />}
              onClick={() =>
                setEditing({ name: "", specialty: "", bio: "", active: true, services: [] })
              }
            >
              Ajouter
            </Button>
          )
        }
      />

      {staff.error && <ErrorState>Impossible de charger les prestataires.</ErrorState>}

      {editing && (
        <StaffForm
          tenantId={tenantId}
          services={serviceRows}
          media={rows(media.data)}
          onMediaChanged={media.reload}
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            staff.reload();
          }}
        />
      )}

      {staff.data === null && !staff.error && <Skeleton rows={3} />}

      {staffRows.length === 0 && staff.data !== null && (
        <EmptyState
          title="Aucun prestataire"
          action={
            canEdit && (
              <Button
                type="button"
                onClick={() =>
                  setEditing({ name: "", specialty: "", bio: "", active: true, services: [] })
                }
              >
                Ajouter la première personne
              </Button>
            )
          }
        >
          Même si vous travaillez seule, créez votre fiche : c&apos;est elle qui
          porte vos horaires et vos rendez-vous.
        </EmptyState>
      )}

      <ul className="space-y-2.5">
        {staffRows.map((member) => (
          <li key={member.id}>
            <Card>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
                    {member.name}
                    {!member.active && <Badge>Inactif</Badge>}
                    {/* Réaliser des prestations et pouvoir se connecter sont
                        deux choses distinctes. Sans cette mention, cette
                        liste semblait contredire celle de l'Équipe. */}
                    {member.has_access ? (
                      <Badge tone="success">Accès à l&apos;espace</Badge>
                    ) : (
                      <Badge>Sans compte</Badge>
                    )}
                  </p>
                  {member.has_access && member.access_email && (
                    <p className="mt-0.5 text-xs text-subtle">
                      {member.access_email}
                    </p>
                  )}
                  {member.specialty && (
                    <p className="mt-0.5 text-sm text-muted">{member.specialty}</p>
                  )}

                  <div className="mt-2">
                    {member.services.length === 0 ? (
                      <Badge tone="warning">
                        Aucune compétence — n&apos;apparaît pas à la réservation
                      </Badge>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {member.services.map((service) => (
                          <Badge key={service.id}>{service.name}</Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {canEdit && (
                  <div className="flex shrink-0 gap-2">
                    <GhostButton type="button" onClick={() => setEditing(member)}>
                      Modifier
                    </GhostButton>
                    <DangerButton type="button" onClick={() => remove(member)}>
                      Supprimer
                    </DangerButton>
                  </div>
                )}
              </div>
            </Card>
          </li>
        ))}
      </ul>

      {!canEdit && (
        <p className="mt-6 text-sm text-muted">
          Seuls le propriétaire et le gérant peuvent modifier l&apos;équipe.
        </p>
      )}
    </section>
  );
}

function StaffForm({
  tenantId,
  services,
  media,
  onMediaChanged,
  initial,
  onClose,
  onSaved,
}: {
  tenantId: string;
  services: Service[];
  media: PickableMedia[];
  onMediaChanged: () => void;
  initial: Partial<StaffMember>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(initial.name ?? "");
  const [specialty, setSpecialty] = useState(initial.specialty ?? "");
  const [bio, setBio] = useState(initial.bio ?? "");
  const [photo, setPhoto] = useState<string | null>(initial.photo ?? null);
  const [active, setActive] = useState(initial.active ?? true);
  const [selected, setSelected] = useState<string[]>(
    (initial.services ?? []).map((s) => s.id),
  );
  const [pending, setPending] = useState(false);

  const isNew = !initial.id;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);

    const ok = await toast.run(
      () =>
        dashboardFetch(
          isNew ? "/api/v1/staff-members/" : `/api/v1/staff-members/${initial.id}/`,
          {
            method: isNew ? "POST" : "PATCH",
            body: JSON.stringify({
              name,
              specialty,
              bio,
              photo,
              active,
              service_ids: selected,
            }),
          },
          tenantId,
        ),
      {
        success: isNew ? `${name} ajouté à l'équipe.` : `Fiche de ${name} enregistrée.`,
      },
    );

    setPending(false);
    if (ok) onSaved();
  }

  return (
    <Card className="mb-7">
      <form onSubmit={submit}>
        <h2 className="mb-5 text-base font-semibold text-ink">
          {isNew ? "Nouveau prestataire" : `Modifier « ${initial.name} »`}
        </h2>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nom">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              className={inputClass}
            />
          </Field>

          <Field label="Spécialité" hint="Affichée sur le mini-site.">
            <input
              value={specialty}
              onChange={(event) => setSpecialty(event.target.value)}
              placeholder="Tresses et perruques"
              className={inputClass}
            />
          </Field>

          <Field label="Présentation" className="sm:col-span-2">
            <textarea
              value={bio}
              onChange={(event) => setBio(event.target.value)}
              rows={2}
              className={inputClass}
            />
          </Field>

          {/*
            Le portrait.

            Il existait côté serveur et s'affichait sur le mini-site, mais
            aucun écran ne permettait de le choisir : la page « L'équipe »
            montrait des initiales pour tout le monde, alors qu'un visage est
            ce qui décide une cliente hésitante.
          */}
          <div className="sm:col-span-2">
            <MediaPicker
              tenantId={tenantId}
              assets={media}
              value={photo}
              onChange={setPhoto}
              onUploaded={onMediaChanged}
              label="Portrait"
              hint="Affiché sur votre mini-site. Sans photo, ses initiales sont utilisées."
              kind="staff"
            />
          </div>
        </div>

        <fieldset className="mt-5">
          <legend className="mb-1 text-sm font-medium text-ink">Compétences</legend>
          <p className="mb-3 text-xs text-muted">
            Seules les prestations cochées seront proposées avec cette personne.
          </p>

          {services.length === 0 ? (
            <p className="text-sm text-muted">Créez d&apos;abord des prestations.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {services.map((service) => {
                const checked = selected.includes(service.id);
                return (
                  <label
                    key={service.id}
                    className={`cursor-pointer rounded-full border px-3 py-1.5 text-sm transition ${
                      checked
                        ? "border-salon bg-salon text-white"
                        : "border-line bg-surface text-muted hover:bg-surface-hover"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        setSelected((current) =>
                          current.includes(service.id)
                            ? current.filter((id) => id !== service.id)
                            : [...current, service.id],
                        )
                      }
                      className="sr-only"
                    />
                    {service.name}
                  </label>
                );
              })}
            </div>
          )}
        </fieldset>

        <div className="mt-5">
          <Toggle
            checked={active}
            onChange={setActive}
            label="Accepte des rendez-vous"
            hint="Décochez pendant un congé long, sans supprimer la fiche."
          />
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Button type="submit" pending={pending}>
            {isNew ? "Ajouter" : "Enregistrer"}
          </Button>
          <GhostButton type="button" onClick={onClose}>
            Annuler
          </GhostButton>
        </div>
      </form>
    </Card>
  );
}
