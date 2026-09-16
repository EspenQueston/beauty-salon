"use client";

/**
 * Ce dont le salon n'a qu'un nombre limité.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi cet écran existe
 * ---------------------------------------------------------------------------
 *
 * Le moteur de créneaux vérifiait qu'une coiffeuse est libre. Il ne vérifiait
 * pas qu'il reste un bac à shampooing. Un salon avec trois coiffeuses et deux
 * bacs pouvait proposer le même créneau de lavage à trois clientes — et la
 * troisième attendait debout.
 *
 * Une ressource se compte, elle ne se réserve pas nominativement : on ne dit
 * pas « le fauteuil n° 2 », on dit « il en reste un sur trois ».
 *
 * ---------------------------------------------------------------------------
 * Ce que la première version affichait mal
 * ---------------------------------------------------------------------------
 *
 * Chaque ressource occupait une carte entière — champ de quantité, pastille,
 * phrase d'explication, deux boutons — et quatre ressources mangeaient un
 * écran. Pire : la carte disait « prise en compte » sans jamais dire **par
 * quoi**. Or c'est la seule chose qu'on vient vérifier ici : « mon bac, il
 * sert à quelles prestations ? »
 *
 * D'où une ligne compacte, qui porte la réponse : les prestations rattachées,
 * en clair, et modifiables sur place. La phrase d'explication n'apparaît plus
 * que là où elle apprend quelque chose — sur une ressource que personne ne
 * réclame, donc qui ne limite rien.
 */

import { useMemo, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import {
  Button,
  Card,
  ErrorState,
  GhostButton,
  SectionTitle,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { Icon } from "./icons";
import { rows, useResource, type Page } from "./useResource";

export interface SalonResource {
  id: string;
  name: string;
  kind: "chair" | "basin" | "room" | "equipment";
  capacity: number;
  active: boolean;
}

interface Link {
  id: string;
  service: string;
  service_name: string;
  resource: string;
}

interface ServiceRow {
  id: string;
  name: string;
  active: boolean;
}

const KINDS: {
  value: SalonResource["kind"];
  label: string;
  short: string;
  hint: string;
}[] = [
  { value: "basin", label: "Bac à shampooing", short: "Bac", hint: "Lavage" },
  { value: "chair", label: "Fauteuil", short: "Fauteuil", hint: "Poste de travail" },
  { value: "room", label: "Cabine", short: "Cabine", hint: "Espace fermé" },
  { value: "equipment", label: "Matériel", short: "Matériel", hint: "Casque, vapeur…" },
];

const KIND_LABELS = Object.fromEntries(KINDS.map((k) => [k.value, k.label]));

/** Plafond aligné sur le serveur : au-delà, c'est une faute de frappe. */
const MAX_CAPACITY = 999;

export function Resources({
  tenantId,
  canEdit,
}: {
  tenantId: string;
  canEdit: boolean;
}) {
  const toast = useToast();
  const resources = useResource<Page<SalonResource>>("/api/v1/resources/", tenantId);
  const links = useResource<Page<Link>>("/api/v1/service-resources/", tenantId);
  const services = useResource<Page<ServiceRow>>(
    "/api/v1/services/?page_size=200",
    tenantId,
  );

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const list = rows(resources.data);
  const allLinks = rows(links.data);
  const serviceRows = rows(services.data);

  // Groupé une fois pour toutes plutôt qu'un filtre par ligne : avec vingt
  // prestations et dix ressources, le filtre naïf fait deux cents passages
  // à chaque frappe.
  const byResource = useMemo(() => {
    const map = new Map<string, Link[]>();
    for (const link of allLinks) {
      const bucket = map.get(link.resource);
      if (bucket) bucket.push(link);
      else map.set(link.resource, [link]);
    }
    return map;
  }, [allLinks]);

  async function patch(resource: SalonResource, changes: Partial<SalonResource>) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/resources/${resource.id}/`,
          { method: "PATCH", body: JSON.stringify(changes) },
          tenantId,
        ),
      { success: "Ressource mise à jour." },
    );
    if (ok) resources.reload();
  }

  async function remove(resource: SalonResource) {
    const used = byResource.get(resource.id)?.length ?? 0;
    if (used > 0) {
      toast.error(
        `« ${resource.name} » est réclamée par ${used} prestation${
          used > 1 ? "s" : ""
        }. Détachez-la d'abord.`,
      );
      return;
    }

    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/resources/${resource.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: `« ${resource.name} » supprimée.` },
    );
    if (ok) {
      resources.reload();
      links.reload();
    }
  }

  async function toggleLink(resource: SalonResource, service: ServiceRow) {
    const existing = byResource
      .get(resource.id)
      ?.find((link) => link.service === service.id);

    const ok = await toast.run(
      () =>
        existing
          ? dashboardFetch(
              `/api/v1/service-resources/${existing.id}/`,
              { method: "DELETE" },
              tenantId,
            )
          : dashboardFetch(
              "/api/v1/service-resources/",
              {
                method: "POST",
                body: JSON.stringify({ service: service.id, resource: resource.id }),
              },
              tenantId,
            ),
      {
        success: existing
          ? `« ${service.name} » ne mobilise plus ${resource.name}.`
          : `« ${service.name} » mobilise ${resource.name}.`,
      },
    );
    if (ok) links.reload();
  }

  async function create(name: string, kind: string, capacity: string) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/resources/",
          {
            method: "POST",
            body: JSON.stringify({
              name,
              kind,
              capacity: clamp(capacity),
            }),
          },
          tenantId,
        ),
      { success: `« ${name} » ajoutée.` },
    );
    if (ok) {
      resources.reload();
      setCreating(false);
    }
    return ok;
  }

  const loading = resources.data === null && !resources.error;

  return (
    <section>
      <div className="mb-4">
        <SectionTitle>Ressources</SectionTitle>
        <p className="-mt-2 text-sm text-muted">
          Ce dont vous n&apos;avez qu&apos;un nombre limité. Une prestation qui
          réclame un bac ne sera plus proposée quand tous vos bacs sont pris,
          même si la coiffeuse est libre.
        </p>
      </div>

      {resources.error && <ErrorState>Impossible de charger les ressources.</ErrorState>}
      {loading && <Skeleton rows={2} />}

      {resources.data !== null && list.length === 0 && !creating && (
        <Card>
          <p className="text-sm text-muted">
            Aucune ressource déclarée. Vos créneaux ne dépendent aujourd&apos;hui
            que de la disponibilité des prestataires.
          </p>
        </Card>
      )}

      {list.length > 0 && (
        <ul className="space-y-2">
          {list.map((resource) => (
            <ResourceRow
              key={resource.id}
              resource={resource}
              links={byResource.get(resource.id) ?? []}
              services={serviceRows}
              canEdit={canEdit}
              expanded={editing === resource.id}
              onExpand={() =>
                setEditing((current) =>
                  current === resource.id ? null : resource.id,
                )
              }
              onPatch={(changes) => patch(resource, changes)}
              onRemove={() => remove(resource)}
              onToggleService={(service) => toggleLink(resource, service)}
            />
          ))}
        </ul>
      )}

      {canEdit && (
        <div className="mt-3">
          {creating ? (
            <NewResource onCancel={() => setCreating(false)} onCreate={create} />
          ) : (
            <GhostButton
              type="button"
              onClick={() => setCreating(true)}
              icon={<Icon name="plus" className="size-4" />}
            >
              Ajouter une ressource
            </GhostButton>
          )}
        </div>
      )}
    </section>
  );
}

function clamp(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 1;
  return Math.min(MAX_CAPACITY, Math.max(1, Math.round(parsed)));
}

/**
 * Une ressource, sur une ligne.
 *
 * L'information principale est la liste des prestations qui la réclament :
 * c'est la question qu'on vient poser à cet écran. Elle est donc en clair,
 * pas derrière une pastille, et elle se modifie sans quitter la ligne.
 */
function ResourceRow({
  resource,
  links,
  services,
  canEdit,
  expanded,
  onExpand,
  onPatch,
  onRemove,
  onToggleService,
}: {
  resource: SalonResource;
  links: Link[];
  services: ServiceRow[];
  canEdit: boolean;
  expanded: boolean;
  onExpand: () => void;
  onPatch: (changes: Partial<SalonResource>) => void;
  onRemove: () => void;
  onToggleService: (service: ServiceRow) => void;
}) {
  const [capacity, setCapacity] = useState(String(resource.capacity));
  const linkedIds = new Set(links.map((link) => link.service));

  function commit(next: number) {
    setCapacity(String(next));
    if (next !== resource.capacity) onPatch({ capacity: next });
  }

  return (
    <li
      className={`rounded-xl border transition ${
        resource.active
          ? "border-line bg-surface"
          : "border-dashed border-line bg-surface-muted"
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3">
        {/* Nom et type : le type en dessous, pas à droite. Aligné à droite,
            il se faisait pousser hors de l'écran par un nom long. */}
        <div className="min-w-0 flex-1">
          <p
            className={`truncate font-medium ${
              resource.active ? "text-ink" : "text-muted line-through"
            }`}
            title={resource.name}
          >
            {resource.name}
          </p>
          <p className="text-xs text-subtle">{KIND_LABELS[resource.kind]}</p>
        </div>

        {/* Quantité : un pas-à-pas, pas un champ libre. On passe de 2 à 3
            bacs, on ne tape pas « 15454 ». */}
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            disabled={!canEdit || resource.capacity <= 1}
            onClick={() => commit(resource.capacity - 1)}
            aria-label={`Retirer un ${resource.name}`}
            className="flex size-8 items-center justify-center rounded-lg border border-line text-muted transition hover:text-ink disabled:opacity-40"
          >
            −
          </button>
          <input
            value={capacity}
            onChange={(event) => setCapacity(event.target.value)}
            onBlur={() => commit(clamp(capacity))}
            disabled={!canEdit}
            inputMode="numeric"
            aria-label={`Quantité de ${resource.name}`}
            className="tabular w-12 rounded-lg border border-line bg-surface py-1.5 text-center text-sm text-ink"
          />
          <button
            type="button"
            disabled={!canEdit || resource.capacity >= MAX_CAPACITY}
            onClick={() => commit(resource.capacity + 1)}
            aria-label={`Ajouter un ${resource.name}`}
            className="flex size-8 items-center justify-center rounded-lg border border-line text-muted transition hover:text-ink disabled:opacity-40"
          >
            +
          </button>
        </div>
      </div>

      {/* Ce que la ressource limite réellement. */}
      <div className="border-t border-line px-3 py-2.5">
        {links.length > 0 ? (
          <ul className="flex flex-wrap items-center gap-1.5">
            {links.map((link) => (
              <li
                key={link.id}
                className="truncate rounded-full bg-salon-soft px-2.5 py-1 text-xs font-medium text-ink"
              >
                {link.service_name}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted">
            Aucune prestation ne la réclame — elle ne limite donc aucun créneau.
          </p>
        )}

        {canEdit && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={onExpand}
              aria-expanded={expanded}
              className="text-xs font-medium text-salon underline-offset-2 hover:underline"
            >
              {expanded ? "Terminer" : "Choisir les prestations"}
            </button>
            <span aria-hidden className="text-subtle">
              ·
            </span>
            <button
              type="button"
              onClick={() => onPatch({ active: !resource.active })}
              className="text-xs text-muted underline-offset-2 hover:text-ink hover:underline"
            >
              {resource.active ? "Suspendre" : "Réactiver"}
            </button>
            <span aria-hidden className="text-subtle">
              ·
            </span>
            <button
              type="button"
              onClick={onRemove}
              className="text-xs text-danger underline-offset-2 hover:underline"
            >
              Supprimer
            </button>
          </div>
        )}
      </div>

      {/* Rattachement, déplié sur place.
          Deux colonnes dès le téléphone : ce sont des étiquettes courtes,
          une seule colonne allongerait la liste pour rien. */}
      {expanded && canEdit && (
        <div className="border-t border-line bg-surface-muted/50 p-3">
          {services.length === 0 ? (
            <p className="text-xs text-muted">
              Créez d&apos;abord une prestation.
            </p>
          ) : (
            <ul className="grid grid-cols-2 gap-1.5 lg:grid-cols-3">
              {services.map((service) => {
                const on = linkedIds.has(service.id);
                return (
                  <li key={service.id}>
                    <button
                      type="button"
                      onClick={() => onToggleService(service)}
                      aria-pressed={on}
                      className={`flex w-full items-center gap-1.5 rounded-lg border px-2.5 py-2 text-left text-xs transition ${
                        on
                          ? "border-salon bg-salon-soft text-ink"
                          : "border-line bg-surface text-muted hover:border-line-strong"
                      }`}
                    >
                      <span
                        aria-hidden
                        className={`flex size-3.5 shrink-0 items-center justify-center rounded border ${
                          on ? "border-salon bg-salon text-white" : "border-line"
                        }`}
                      >
                        {on && <Icon name="check" className="size-2.5" />}
                      </span>
                      <span className="truncate">{service.name}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

function NewResource({
  onCancel,
  onCreate,
}: {
  onCancel: () => void;
  onCreate: (name: string, kind: string, capacity: string) => Promise<boolean>;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<SalonResource["kind"]>("basin");
  const [capacity, setCapacity] = useState("1");
  const [pending, setPending] = useState(false);

  async function submit(event: { preventDefault: () => void }) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;

    setPending(true);
    await onCreate(trimmed, kind, capacity);
    setPending(false);
    setName("");
    setCapacity("1");
  }

  return (
    /*
      Un <div>, pas un <form> : ce bloc peut se retrouver à l'intérieur d'un
      autre formulaire, et deux <form> imbriqués font recharger la page à la
      première soumission. La touche Entrée est gérée à la main.
    */
    <div
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          void submit(event);
        }
      }}
      className="rounded-xl border border-dashed border-line p-3"
    >
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_11rem_5rem]">
        <input
          autoFocus
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={120}
          placeholder="Bac à shampooing"
          aria-label="Nom de la ressource"
          className={inputClass}
        />
        <select
          value={kind}
          onChange={(event) => setKind(event.target.value as SalonResource["kind"])}
          aria-label="Type de ressource"
          className={inputClass}
        >
          {KINDS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <input
          value={capacity}
          onChange={(event) => setCapacity(event.target.value)}
          inputMode="numeric"
          aria-label="Quantité disponible"
          className={`${inputClass} tabular text-center`}
        />
      </div>

      <div className="mt-2 flex items-center gap-2">
        <Button
          type="button"
          pending={pending}
          disabled={!name.trim()}
          onClick={(event) => void submit(event)}
        >
          Ajouter
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-2 py-2 text-sm text-muted transition hover:text-ink"
        >
          Annuler
        </button>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Rattachement depuis la fiche d'une prestation
 * ---------------------------------------------------------------------- */

/**
 * Le même rattachement, vu depuis l'autre bout.
 *
 * Les deux écrans écrivent la même table. On rattache depuis la prestation
 * quand on la crée — « ce soin demande un bac » — et depuis la ressource
 * quand on en ajoute une — « mon nouveau bac sert à ces quatre prestations ».
 * Imposer un seul des deux sens obligerait à traverser le panneau une fois
 * sur deux.
 */
export function ServiceResources({
  tenantId,
  serviceId,
  canEdit,
}: {
  tenantId: string;
  serviceId: string;
  canEdit: boolean;
}) {
  const toast = useToast();
  const resources = useResource<Page<SalonResource>>("/api/v1/resources/", tenantId);
  const links = useResource<Page<Link>>(
    `/api/v1/service-resources/?service=${serviceId}`,
    tenantId,
  );

  const all = rows(resources.data).filter((resource) => resource.active);
  const linked = new Map(rows(links.data).map((link) => [link.resource, link.id]));

  if (all.length === 0) return null;

  async function toggle(resource: SalonResource) {
    const existing = linked.get(resource.id);

    const ok = await toast.run(
      () =>
        existing
          ? dashboardFetch(
              `/api/v1/service-resources/${existing}/`,
              { method: "DELETE" },
              tenantId,
            )
          : dashboardFetch(
              "/api/v1/service-resources/",
              {
                method: "POST",
                body: JSON.stringify({ service: serviceId, resource: resource.id }),
              },
              tenantId,
            ),
      {
        success: existing
          ? `« ${resource.name} » n'est plus requise.`
          : `« ${resource.name} » est maintenant requise.`,
      },
    );
    if (ok) links.reload();
  }

  return (
    <div className="rounded-xl border border-line bg-surface-muted/40 p-3 sm:p-4">
      <p className="mb-1 text-sm font-medium text-ink">Ressources mobilisées</p>
      <p className="mb-3 text-xs text-muted">
        Une unité par rendez-vous. Quand tout est pris, le créneau disparaît.
      </p>

      <ul className="grid grid-cols-2 gap-1.5 lg:grid-cols-3">
        {all.map((resource) => {
          const active = linked.has(resource.id);
          return (
            <li key={resource.id}>
              <button
                type="button"
                disabled={!canEdit}
                onClick={() => toggle(resource)}
                aria-pressed={active}
                className={`w-full rounded-lg border px-2.5 py-2 text-left transition ${
                  active
                    ? "border-salon bg-salon-soft text-ink"
                    : "border-line bg-surface text-muted hover:border-line-strong"
                } disabled:opacity-60`}
              >
                <span className="block truncate text-sm font-medium">
                  {resource.name}
                </span>
                <span className="tabular text-xs text-subtle">
                  {resource.capacity} disponible{resource.capacity > 1 ? "s" : ""}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
