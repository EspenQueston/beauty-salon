"use client";

/**
 * Catalogue du salon : catégories et prestations.
 *
 * Le prix accepte trois formes — ferme, « à partir de », sur devis — parce
 * qu'une pose de perruque ne se chiffre pas comme une manucure, et qu'obliger
 * à un montant exact ferait fuir les prestataires.
 */

import { useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { formatDuration, formatPrice } from "@/lib/format";
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
  SectionTitle,
  Skeleton,
  Toggle,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { Icon } from "./icons";
import { CatalogFilter, EMPTY_FILTER, type FilterState } from "./CatalogFilter";
import { MediaPicker, type PickableMedia } from "./MediaPicker";
import { ServiceOptions } from "./ServiceOptions";
import { Resources, ServiceResources } from "./Resources";
import { useDashboard } from "./DashboardShell";
import { rows, useResource, type Page } from "./useResource";

interface Category {
  id: string;
  name: string;
  position: number;
  active: boolean;
  service_count: number;
}

interface Service {
  id: string;
  category: string;
  category_name: string;
  name: string;
  description: string;
  duration_minutes: number;
  price_kind: "fixed" | "from" | "quote";
  price_amount: string;
  requires_deposit: boolean;
  location_mode: "salon" | "home" | "hybrid";
  active: boolean;
  /** Photo de la prestation. Identifiant du média, ou null. */
  image: string | null;
}

const PRICE_KINDS = [
  { value: "fixed", label: "Prix ferme" },
  { value: "from", label: "À partir de" },
  { value: "quote", label: "Sur devis" },
];

const LOCATIONS = [
  { value: "salon", label: "Au salon" },
  { value: "home", label: "À domicile" },
  { value: "hybrid", label: "Les deux" },
];

/**
 * La règle d'acompte du salon, telle que la fiche du salon la définit.
 *
 * Elle est lue ici pour une seule raison : montrer, sous l'interrupteur, ce
 * que « demande un acompte » va réellement coûter à la cliente pour *cette*
 * prestation. Sans ce chiffre, la personne qui coche doit ouvrir un autre
 * écran, y lire un pourcentage, et faire la multiplication de tête — ce que
 * personne ne fait, d'où le réglage posé au hasard.
 */
interface DepositRule {
  deposit_rate: number;
  deposit_minimum: string;
  /** Le lieu que le salon a declare : il sert de valeur de depart ici. */
  service_mode: Service["location_mode"];
}

/**
 * Ce que l'acompte vaudra pour cette prestation, en toutes lettres.
 *
 * Le calcul reproduit celui du serveur — pourcentage du temps, plancher du
 * salon — volontairement limité à la prestation seule : les options et les
 * fournitures dépendent de ce que la cliente choisira, et les inclure ici
 * annoncerait un montant qu'on ne peut pas tenir.
 */
function depositHint(
  values: Partial<Service>,
  rule: DepositRule | null,
  currency: string,
): string {
  if (!values.requires_deposit) {
    return "Aucun acompte ne sera demandé à la réservation.";
  }
  if (!rule) return "Le montant vient de la règle de votre salon.";

  const rate = rule.deposit_rate || 0;
  const minimum = Number(rule.deposit_minimum) || 0;

  if (rate === 0 && minimum === 0) {
    return "Votre règle ne demande rien : réglez un pourcentage ou un minimum dans Profil du salon → Acompte.";
  }

  const price = values.price_kind === "quote" ? 0 : Number(values.price_amount) || 0;
  const due = Math.floor(Math.max(minimum, (price * rate) / 100));

  if (values.price_kind === "quote") {
    return `Règle du salon : ${rate} % de la prestation, minimum ${formatPrice(
      String(minimum),
      currency,
    )}. Le montant sera fixé au devis.`;
  }

  return `Soit ${formatPrice(String(due), currency)} pour cette prestation — ${rate} % du prix, minimum ${formatPrice(String(minimum), currency)}. Les fournitures s'ajoutent.`;
}

/** Le même calcul, en une étiquette courte pour la liste. */
function depositLabel(
  service: Pick<Service, "price_kind" | "price_amount">,
  rule: DepositRule | null,
  currency: string,
): string {
  if (!rule) return "demandé";
  const rate = rule.deposit_rate || 0;
  const minimum = Number(rule.deposit_minimum) || 0;
  if (rate === 0 && minimum === 0) return "non réglé";
  if (service.price_kind === "quote") return `${rate} %`;

  const price = Number(service.price_amount) || 0;
  return formatPrice(
    String(Math.floor(Math.max(minimum, (price * rate) / 100))),
    currency,
  );
}

const EMPTY: Partial<Service> = {
  name: "",
  description: "",
  duration_minutes: 60,
  price_kind: "fixed",
  price_amount: "0",
  requires_deposit: false,
  active: true,
};

export function Services() {
  const { membership } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const currency = membership.tenant.currency;
  const canEdit = ["owner", "manager"].includes(membership.role);

  const categories = useResource<Page<Category>>(
    "/api/v1/service-categories/?page_size=100",
    tenantId,
  );
  const services = useResource<Page<Service>>("/api/v1/services/?page_size=200", tenantId);
  // Les photos déjà téléversées : le formulaire en rattache une sans quitter
  // l'écran.
  const media = useResource<Page<PickableMedia>>(
    "/api/v1/media/?page_size=100",
    tenantId,
  );

  const [editing, setEditing] = useState<Partial<Service> | null>(null);

  /*
   * Deux parties, deux onglets.
   *
   * Le catalogue et les ressources répondent à deux questions différentes —
   * « qu'est-ce que je vends » et « qu'est-ce qui me limite ». Empilés sur
   * une même page, le second poussait le premier sous la ligne de
   * flottaison alors qu'on ouvre cet écran neuf fois sur dix pour le
   * premier.
   */
  const [tab, setTab] = useState<"catalogue" | "ressources">("catalogue");

  // Chargé ici seulement pour le compteur de l'onglet : l'écran des
  // ressources recharge sa propre liste quand on l'ouvre.
  const resources = useResource<Page<{ id: string }>>(
    "/api/v1/resources/",
    tenantId,
  );
  const resourceCount = rows(resources.data).length;

  // La règle d'acompte du salon : elle alimente l'aperçu sous l'interrupteur
  // de chaque prestation. Chargée ici plutôt que dans le formulaire, qui se
  // monte et se démonte à chaque ouverture.
  const rule = useResource<DepositRule>("/api/v1/salon-profile", tenantId);
  const [filter, setFilter] = useState<FilterState>(EMPTY_FILTER);

  const categoryRows = rows(categories.data);

  /**
   * Une prestation neuve, préremplie comme le salon s'est décrit.
   *
   * Le lieu partait de « Au salon », quoi qu'ait déclaré le salon par
   * ailleurs. Une gérante qui réglait son profil sur « au salon ou à
   * domicile », déclarait ses quartiers et leurs forfaits, puis créait ses
   * prestations, obtenait un parcours de réservation où l'étape « à
   * domicile » n'apparaissait jamais — deux réglages qui parlent de la même
   * chose, dans deux écrans, sans rien pour les relier.
   *
   * Le serveur applique la même valeur de départ pour qui passe par l'API.
   * Ici, on la met aussi à l'écran : un champ qui affiche autre chose que ce
   * qui sera enregistré vaut moins que pas de champ du tout.
   */
  function nouvelle(): Partial<Service> {
    return {
      ...EMPTY,
      category: categoryRows[0]?.id,
      location_mode: rule.data?.service_mode ?? "salon",
    };
  }
  const serviceRows = rows(services.data);
  const mediaRows = rows(media.data);

  /*
   * Filtrage dérivé, jamais stocké.
   *
   * Garder une liste filtrée dans un état obligerait à la recalculer à
   * chaque écriture — et une prestation qu'on vient de renommer
   * disparaîtrait de l'écran jusqu'au rechargement suivant.
   */
  const needle = filter.query.trim().toLowerCase();
  const visible = serviceRows.filter((service) => {
    if (filter.activeOnly && !service.active) return false;
    if (filter.categoryId && service.category !== filter.categoryId) return false;
    if (!needle) return true;
    return (
      service.name.toLowerCase().includes(needle) ||
      (service.description ?? "").toLowerCase().includes(needle)
    );
  });

  const counts = Object.fromEntries(
    categoryRows.map((category) => [
      category.id,
      serviceRows.filter((service) => service.category === category.id).length,
    ]),
  );

  function reloadAll() {
    categories.reload();
    services.reload();
    media.reload();
  }

  async function remove(service: Service) {
    const ok = await toast.run(
      () =>
        dashboardFetch(`/api/v1/services/${service.id}/`, { method: "DELETE" }, tenantId),
      {
        success: `« ${service.name} » supprimée.`,
        error:
          "Suppression impossible : cette prestation a des rendez-vous. Désactivez-la plutôt.",
      },
    );
    if (ok) reloadAll();
  }

  async function toggle(service: Service) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/services/${service.id}/`,
          { method: "PATCH", body: JSON.stringify({ active: !service.active }) },
          tenantId,
        ),
      {
        success: service.active
          ? `« ${service.name} » n'est plus réservable.`
          : `« ${service.name} » est de nouveau réservable.`,
      },
    );
    if (ok) services.reload();
  }

  return (
    <section>
      <PageHeader
        title="Prestations"
        description="Ce que vos clientes voient et réservent sur votre mini-site."
        action={
          canEdit &&
          tab === "catalogue" &&
          categoryRows.length > 0 && (
            <Button
              type="button"
              icon={<Icon name="plus" className="size-4" />}
              onClick={() => setEditing(nouvelle())}
            >
              Nouvelle prestation
            </Button>
          )
        }
      />

      {(services.error || categories.error) && (
        <ErrorState>Impossible de charger le catalogue.</ErrorState>
      )}

      <div
        role="tablist"
        aria-label="Parties de la page"
        className="mb-5 flex rounded-lg border border-line bg-surface p-0.5"
      >
        {(
          [
            ["catalogue", "Prestations", serviceRows.length],
            ["ressources", "Ressources", resourceCount],
          ] as ["catalogue" | "ressources", string, number][]
        ).map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm transition ${
              tab === key
                ? "bg-salon font-medium text-white"
                : "text-muted hover:text-ink"
            }`}
          >
            {label}
            {count > 0 && (
              <span
                className={`tabular text-xs ${
                  tab === key ? "text-white/70" : "text-subtle"
                }`}
              >
                {count}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === "ressources" && (
        <Resources tenantId={tenantId} canEdit={canEdit} />
      )}

      {tab === "catalogue" && canEdit && (
        <CategoryManager
          tenantId={tenantId}
          categories={categoryRows}
          onChange={reloadAll}
        />
      )}

      {tab === "catalogue" && editing && (
        <ServiceForm
          tenantId={tenantId}
          currency={currency}
          rule={rule.data}
          categories={categoryRows}
          media={mediaRows}
          onMediaChanged={media.reload}
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reloadAll();
          }}
        />
      )}

      {tab === "catalogue" && (
        <>
      {services.data === null && !services.error && <Skeleton rows={3} />}

      {categoryRows.length === 0 && categories.data !== null && (
        <EmptyState title="Commencez par une catégorie">
          Coiffure, ongles, maquillage, soins… Les catégories organisent votre
          mini-site et aident vos clientes à s&apos;y retrouver.
        </EmptyState>
      )}

      {categoryRows.length > 0 && serviceRows.length === 0 && services.data !== null && (
        <EmptyState
          title="Aucune prestation"
          action={
            canEdit && (
              <Button
                type="button"
                onClick={() => setEditing(nouvelle())}
              >
                Créer ma première prestation
              </Button>
            )
          }
        >
          Sans prestation, vos clientes n&apos;ont rien à réserver.
        </EmptyState>
      )}

      {serviceRows.length > 3 && (
        <CatalogFilter
          categories={categoryRows}
          counts={counts}
          value={filter}
          onChange={setFilter}
          total={serviceRows.length}
          shown={visible.length}
        />
      )}

      {visible.length === 0 && serviceRows.length > 0 && (
        <EmptyState title="Aucun résultat">
          Aucune prestation ne correspond à cette recherche. Essayez une autre
          orthographe, ou retirez les filtres.
        </EmptyState>
      )}

      <div className="mt-7 space-y-8">
        {categoryRows.map((category) => {
          const list = visible.filter((s) => s.category === category.id);
          if (list.length === 0) return null;

          return (
            <div key={category.id}>
              <SectionTitle>{category.name}</SectionTitle>
              <ul className="space-y-2.5">
                {list.map((service) => (
                  <li key={service.id}>
                    <Card>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
                            {service.name}
                            {!service.active && <Badge>Inactive</Badge>}
                          </p>
                          <p className="mt-1 text-sm text-muted">
                            {formatDuration(service.duration_minutes)}
                            {/* Le montant réel, calculé avec la règle du
                                salon — et non le montant de la fiche, qui
                                n'était pas celui qu'on facturait. */}
                            {service.requires_deposit &&
                              ` · acompte ${depositLabel(service, rule.data, currency)}`}
                            {service.location_mode !== "salon" &&
                              ` · ${LOCATIONS.find((l) => l.value === service.location_mode)?.label}`}
                          </p>
                          {service.description && (
                            <p className="mt-1.5 text-sm leading-relaxed text-subtle">
                              {service.description}
                            </p>
                          )}
                        </div>

                        <span className="tabular shrink-0 font-semibold text-salon">
                          {service.price_kind === "quote"
                            ? "Sur devis"
                            : `${service.price_kind === "from" ? "dès " : ""}${formatPrice(
                                service.price_amount,
                                currency,
                              )}`}
                        </span>
                      </div>

                      {canEdit && (
                        <div className="mt-4 flex flex-wrap gap-2">
                          <GhostButton type="button" onClick={() => setEditing(service)}>
                            Modifier
                          </GhostButton>
                          <GhostButton type="button" onClick={() => toggle(service)}>
                            {service.active ? "Désactiver" : "Activer"}
                          </GhostButton>
                          <DangerButton type="button" onClick={() => remove(service)}>
                            Supprimer
                          </DangerButton>
                        </div>
                      )}
                    </Card>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>

        </>
      )}

      {!canEdit && (
        <p className="mt-6 text-sm text-muted">
          Seuls le propriétaire et le gérant peuvent modifier le catalogue.
        </p>
      )}
    </section>
  );
}

function CategoryManager({
  tenantId,
  categories,
  onChange,
}: {
  tenantId: string;
  categories: Category[];
  onChange: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    const ok = await toast.run(
      () =>
        dashboardFetch(
          "/api/v1/service-categories/",
          { method: "POST", body: JSON.stringify({ name, position: categories.length }) },
          tenantId,
        ),
      {
        success: `Catégorie « ${name} » ajoutée.`,
        error: "Cette catégorie existe déjà.",
      },
    );
    setPending(false);
    if (ok) {
      setName("");
      onChange();
    }
  }

  async function remove(category: Category) {
    if (category.service_count > 0) {
      toast.error(
        `« ${category.name} » contient ${category.service_count} prestation(s). Videz-la d'abord.`,
      );
      return;
    }
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/service-categories/${category.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: `Catégorie « ${category.name} » supprimée.` },
    );
    if (ok) onChange();
  }

  return (
    <Card className="mb-7">
      <SectionTitle>Catégories</SectionTitle>

      {categories.length > 0 && (
        <ul className="mb-4 flex flex-wrap gap-2">
          {categories.map((category) => (
            <li
              key={category.id}
              className="flex items-center gap-2 rounded-full bg-surface-muted py-1 pl-3 pr-1.5 text-sm text-ink"
            >
              {category.name}
              <span className="tabular text-xs text-subtle">
                {category.service_count}
              </span>
              <button
                type="button"
                onClick={() => remove(category)}
                aria-label={`Supprimer la catégorie ${category.name}`}
                className="rounded-full p-1 text-subtle transition hover:bg-danger-bg hover:text-danger"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="size-3.5">
                  <path d="m6 6 12 12M18 6 6 18" strokeWidth="2.5" strokeLinecap="round" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <Field label="Ajouter une catégorie" className="min-w-[14rem] flex-1">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Coiffure, ongles…"
            required
            className={inputClass}
          />
        </Field>
        <Button type="submit" pending={pending} className="mb-0.5">
          Ajouter
        </Button>
      </form>
    </Card>
  );
}

function ServiceForm({
  tenantId,
  currency,
  rule,
  categories,
  media,
  onMediaChanged,
  initial,
  onClose,
  onSaved,
}: {
  tenantId: string;
  currency: string;
  rule: DepositRule | null;
  categories: Category[];
  media: PickableMedia[];
  onMediaChanged: () => void;
  initial: Partial<Service>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [values, setValues] = useState<Partial<Service>>(initial);
  const [pending, setPending] = useState(false);
  const isNew = !initial.id;

  function set<K extends keyof Service>(key: K, value: Service[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);

    const ok = await toast.run(
      () =>
        dashboardFetch(
          isNew ? "/api/v1/services/" : `/api/v1/services/${initial.id}/`,
          {
            method: isNew ? "POST" : "PATCH",
            body: JSON.stringify({
              category: values.category,
              name: values.name,
              description: values.description ?? "",
              duration_minutes: Number(values.duration_minutes),
              price_kind: values.price_kind,
              price_amount: values.price_kind === "quote" ? "0" : values.price_amount,
              requires_deposit: values.requires_deposit ?? false,
              location_mode: values.location_mode,
              active: values.active ?? true,
              image: values.image ?? null,
            }),
          },
          tenantId,
        ),
      {
        success: isNew
          ? `« ${values.name} » ajoutée au catalogue.`
          : `« ${values.name} » enregistrée.`,
      },
    );

    setPending(false);
    if (ok) onSaved();
  }

  return (
    <Card className="mb-7">
      <form onSubmit={submit}>
        <h2 className="mb-5 text-base font-semibold text-ink">
          {isNew ? "Nouvelle prestation" : `Modifier « ${initial.name} »`}
        </h2>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <MediaPicker
              tenantId={tenantId}
              assets={media}
              value={values.image ?? null}
              onChange={(id) => set("image", id)}
              onUploaded={onMediaChanged}
              label="Photo de la prestation"
              hint="Elle s'affiche sur votre mini-site et pendant la réservation. Sans photo, une image d'ambiance est utilisée."
            />
          </div>

          <Field label="Nom" className="sm:col-span-2">
            <input
              value={values.name ?? ""}
              onChange={(event) => set("name", event.target.value)}
              placeholder="Tresses collées"
              required
              className={inputClass}
            />
          </Field>

          <Field label="Catégorie">
            <select
              value={values.category ?? ""}
              onChange={(event) => set("category", event.target.value)}
              required
              className={inputClass}
            >
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Durée (minutes)" hint="Temps réellement bloqué dans l'agenda.">
            <input
              type="number"
              min={5}
              step={5}
              value={values.duration_minutes ?? 60}
              onChange={(event) => set("duration_minutes", Number(event.target.value))}
              required
              className={inputClass}
            />
          </Field>

          <Field label="Type de tarif">
            <select
              value={values.price_kind ?? "fixed"}
              onChange={(event) =>
                set("price_kind", event.target.value as Service["price_kind"])
              }
              className={inputClass}
            >
              {PRICE_KINDS.map((kind) => (
                <option key={kind.value} value={kind.value}>
                  {kind.label}
                </option>
              ))}
            </select>
          </Field>

          {values.price_kind !== "quote" && (
            <Field label={`Prix (${currency})`}>
              <input
                type="number"
                min={0}
                step="0.01"
                value={values.price_amount ?? "0"}
                onChange={(event) => set("price_amount", event.target.value)}
                className={inputClass}
              />
            </Field>
          )}

          {/*
            Un interrupteur, plus un montant.

            Ce champ demandait autrefois une somme, et cette somme n'était pas
            celle que la cliente payait : la règle du salon — un pourcentage —
            l'emportait. Le mini-site annonçait « acompte de 5 000 », la page
            de règlement en réclamait 7 500. Deux réglages pour une même
            notion, à deux endroits, qui se contredisaient.

            La fiche ne dit plus que oui ou non. Le montant vit dans la règle
            du salon, et l'aperçu ci-dessous montre ce que cela donne pour
            *cette* prestation — pour qu'on n'ait pas à faire le calcul de
            tête ni à ouvrir un autre écran.
          */}
          <div className="sm:col-span-2">
            <Toggle
              checked={values.requires_deposit ?? false}
              onChange={(value) => set("requires_deposit", value)}
              label="Cette prestation demande un acompte"
              hint={depositHint(values, rule, currency)}
            />
          </div>

          <Field
            label="Lieu"
            hint={
              values.location_mode === "salon"
                ? "Cette prestation ne sera pas proposée à domicile, même si votre salon se déplace."
                : "La cliente choisira son quartier à la réservation, et le forfait s'ajoutera au total."
            }
          >
            <select
              value={values.location_mode ?? "salon"}
              onChange={(event) =>
                set("location_mode", event.target.value as Service["location_mode"])
              }
              className={inputClass}
            >
              {LOCATIONS.map((location) => (
                <option key={location.value} value={location.value}>
                  {location.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Description" className="sm:col-span-2">
            <textarea
              value={values.description ?? ""}
              onChange={(event) => set("description", event.target.value)}
              rows={3}
              placeholder="Ce que la prestation comprend, ce qu'il faut prévoir…"
              className={inputClass}
            />
          </Field>

          <div className="sm:col-span-2">
            <Toggle
              checked={values.active ?? true}
              onChange={(value) => set("active", value)}
              label="Réservable en ligne"
              hint="Décochez pour la retirer du mini-site sans la supprimer."
            />
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Button type="submit" pending={pending}>
            {isNew ? "Créer la prestation" : "Enregistrer"}
          </Button>
          <GhostButton type="button" onClick={onClose}>
            Annuler
          </GhostButton>
        </div>
      </form>

      {/*
        Les options vivent hors du formulaire, et volontairement.

        Elles s'enregistrent une par une, dès qu'on quitte un champ ; les
        inclure dans le <form> les ferait partir avec le bouton
        « Enregistrer » — donc jamais pour une prestation qu'on n'a pas
        modifiée par ailleurs. Elles n'apparaissent qu'une fois la
        prestation créée : une option sans prestation n'existe pas.
      */}
      {!isNew && values.id && (
        <div className="mt-6 space-y-4 border-t border-line pt-5">
          <ServiceOptions
            tenantId={tenantId}
            serviceId={values.id}
            serviceName={values.name ?? "cette prestation"}
            baseMinutes={Number(values.duration_minutes) || 0}
            currency={currency}
            canEdit
          />
          <ServiceResources
            tenantId={tenantId}
            serviceId={values.id}
            canEdit
          />
        </div>
      )}
    </Card>
  );
}
