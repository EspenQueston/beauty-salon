"use client";

/**
 * La boutique : ce que le salon vend au comptoir.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi deux onglets et pas une seule liste
 * ---------------------------------------------------------------------------
 *
 * Un article et une exigence répondent à deux questions différentes :
 *
 *   - **Articles** : « qu'est-ce que je vends, à quel prix, combien m'en
 *     reste-t-il ». C'est un inventaire, on l'ouvre pour corriger un stock.
 *   - **À prévoir** : « qu'est-ce qu'il faut apporter pour cette prestation ».
 *     C'est une information destinée à la cliente, et elle vaut même sans
 *     rien à vendre — un salon gagne à écrire « prévoir 3 paquets de mèches »
 *     sans les vendre lui-même.
 *
 * L'ordre compte : l'exigence existe sans l'article, jamais l'inverse. Un
 * catalogue détaché des prestations serait une boutique en ligne, ce que ce
 * produit n'est pas.
 *
 * ---------------------------------------------------------------------------
 * Le stock
 * ---------------------------------------------------------------------------
 *
 * Vide signifie « je n'en manque jamais » — le salon qui vend du shampooing
 * au litre ne veut pas tenir un inventaire. Zéro signifie « rupture », ce qui
 * n'est pas la même chose et s'affiche différemment.
 */

import { useMemo, useState } from "react";

import { dashboardFetch } from "@/lib/dashboard";
import { formatPrice } from "@/lib/format";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  GhostButton,
  PageHeader,
  SectionTitle,
  Skeleton,
  inputClass,
} from "@/features/ui";
import { useToast } from "@/features/ui/Toast";
import { useDashboard } from "./DashboardShell";
import { Icon } from "./icons";
import { ProductMedia } from "@/features/booking/ProductMedia";
import { productIllustrations } from "@/lib/illustrations";
import { MediaPicker, type PickableMedia } from "./MediaPicker";
import { rows, useResource, type Page } from "./useResource";

interface Product {
  id: string;
  name: string;
  description: string;
  price: string;
  unit: string;
  unit_label: string;
  stock: number | null;
  low_stock_at: number;
  image: string | null;
  image_url: string;
  image_type: string;
  active: boolean;
  position: number;
  in_stock: boolean;
  is_low: boolean;
}

interface Requirement {
  id: string;
  service: string;
  service_name: string;
  label: string;
  detail: string;
  mandatory: boolean;
  position: number;
  product_ids: string[];
}

interface ServiceRow {
  id: string;
  name: string;
}

const UNITS = [
  { value: "piece", label: "À l'unité" },
  { value: "pack", label: "Paquet" },
  { value: "meter", label: "Mètre" },
  { value: "gram", label: "Gramme" },
];

export function Store() {
  const { membership } = useDashboard();
  const toast = useToast();
  const tenantId = membership.tenant.id;
  const currency = membership.tenant.currency;
  const canEdit = ["owner", "manager"].includes(membership.role);

  const [tab, setTab] = useState<"articles" | "prevoir">("articles");

  const products = useResource<Page<Product>>("/api/v1/products/", tenantId);
  const requirements = useResource<Page<Requirement>>(
    "/api/v1/requirements/",
    tenantId,
  );
  const services = useResource<Page<ServiceRow>>(
    "/api/v1/services/?page_size=200",
    tenantId,
  );
  const media = useResource<Page<PickableMedia>>(
    "/api/v1/media/?page_size=100",
    tenantId,
  );

  const productRows = rows(products.data);
  const requirementRows = rows(requirements.data);
  const serviceRows = rows(services.data);

  // Les ruptures en tête : c'est la seule information de cet écran qui
  // coûte de l'argent tant qu'on ne la voit pas.
  const outOfStock = productRows.filter((p) => p.active && !p.in_stock);
  const low = productRows.filter((p) => p.active && p.is_low);

  async function patchProduct(product: Product, changes: Partial<Product>) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/products/${product.id}/`,
          { method: "PATCH", body: JSON.stringify(changes) },
          tenantId,
        ),
      { success: "Article mis à jour." },
    );
    if (ok) products.reload();
  }

  async function removeProduct(product: Product) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/products/${product.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: `« ${product.name} » retiré de la boutique.` },
    );
    if (ok) {
      products.reload();
      requirements.reload();
    }
  }

  return (
    <section>
      <PageHeader
        title="Boutique"
        description="Ce que vous vendez au comptoir, et ce qu'il faut prévoir pour chaque prestation."
      />

      {(products.error || requirements.error) && (
        <ErrorState>Impossible de charger la boutique.</ErrorState>
      )}

      {/* Une alerte, pas un tableau de bord : un article en rupture reste
          proposé à la réservation, barré, et le salon doit le savoir. */}
      {(outOfStock.length > 0 || low.length > 0) && (
        <div className="mb-5 rounded-xl border-l-4 border-l-amber-500 border-y border-r border-line bg-surface p-3.5">
          {outOfStock.length > 0 && (
            <p className="text-sm text-ink">
              <span className="font-medium">
                {outOfStock.length} article{outOfStock.length > 1 ? "s" : ""} en
                rupture
              </span>{" "}
              <span className="text-muted">
                — {outOfStock.map((p) => p.name).join(", ")}
              </span>
            </p>
          )}
          {low.length > 0 && (
            <p className="mt-1 text-sm text-muted">
              Bientôt épuisé : {low.map((p) => `${p.name} (${p.stock})`).join(", ")}
            </p>
          )}
        </div>
      )}

      <div
        role="tablist"
        aria-label="Parties de la boutique"
        className="mb-5 flex rounded-lg border border-line bg-surface p-0.5"
      >
        {(
          [
            ["articles", "Articles", productRows.length],
            ["prevoir", "À prévoir", requirementRows.length],
          ] as ["articles" | "prevoir", string, number][]
        ).map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm transition ${
              tab === key ? "bg-salon font-medium text-white" : "text-muted hover:text-ink"
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

      {tab === "articles" && (
        <Articles
          tenantId={tenantId}
          currency={currency}
          canEdit={canEdit}
          products={productRows}
          loading={products.data === null && !products.error}
          media={rows(media.data)}
          onMediaChanged={media.reload}
          onChanged={products.reload}
          onPatch={patchProduct}
          onRemove={removeProduct}
        />
      )}

      {tab === "prevoir" && (
        <ToBring
          tenantId={tenantId}
          canEdit={canEdit}
          requirements={requirementRows}
          services={serviceRows}
          products={productRows}
          currency={currency}
          loading={requirements.data === null && !requirements.error}
          onChanged={requirements.reload}
        />
      )}
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Articles
 * ---------------------------------------------------------------------- */

function Articles({
  tenantId,
  currency,
  canEdit,
  products,
  loading,
  media,
  onMediaChanged,
  onChanged,
  onPatch,
  onRemove,
}: {
  tenantId: string;
  currency: string;
  canEdit: boolean;
  products: Product[];
  loading: boolean;
  media: PickableMedia[];
  onMediaChanged: () => void;
  onChanged: () => void;
  onPatch: (product: Product, changes: Partial<Product>) => void;
  onRemove: (product: Product) => void;
}) {
  const [creating, setCreating] = useState(false);

  /*
   * Un seul article en cours de modification à la fois.
   *
   * Un identifiant plutôt qu'un booléen par carte : deux formulaires ouverts
   * côte à côte dans une grille de vignettes ne se distinguent plus l'un de
   * l'autre, et on enregistre le mauvais.
   */
  const [editing, setEditing] = useState<string | null>(null);

  // Calculé sur la liste entière : c'est le seul niveau qui sait quelles
  // images sont déjà prises par les voisins.
  const fallbacks = useMemo(() => productIllustrations(products), [products]);

  return (
    <div>
      {loading && <Skeleton rows={2} />}

      {!loading && products.length === 0 && !creating && (
        <EmptyState
          title="Votre boutique est vide"
          action={
            canEdit && (
              <Button type="button" onClick={() => setCreating(true)}>
                Ajouter un article
              </Button>
            )
          }
        >
          Mèches, perruques, kits d&apos;entretien… Ce que vous vendez ici pourra
          être proposé à vos clientes au moment où elles réservent.
        </EmptyState>
      )}

      {/*
        Deux colonnes sur téléphone, quatre sur grand écran.

        Deux dès le téléphone parce que ces cartes sont courtes : une seule
        colonne allongerait le défilement sans rien gagner en lisibilité.

        Quatre au lieu de trois en haut de gamme : trois laissaient une bande
        vide à droite d'un écran de bureau et ajoutaient une rangée tous les
        trois articles. Un inventaire se parcourt du regard — plus il en
        tient sur une ligne, moins il faut défiler pour trouver le bon.
      */}
      {products.length > 0 && (
        <ul className="grid grid-cols-2 gap-2.5 sm:gap-3 md:grid-cols-3 lg:grid-cols-4">
          {products.map((product) => (
            /*
              La carte en cours de modification prend toute la largeur.

              Un formulaire de six champs dans une demi-colonne de téléphone
              donne des cases de trois caractères ; l'article voisin, lui, ne
              sert à rien pendant qu'on corrige un prix. La ligne entière est
              le bon support, et la grille se referme dès qu'on a enregistré.
            */
            <li
              key={product.id}
              className={
                editing === product.id
                  ? "col-span-2 md:col-span-3 lg:col-span-4"
                  : undefined
              }
            >
              {editing === product.id ? (
                <ProductForm
                  tenantId={tenantId}
                  currency={currency}
                  media={media}
                  onMediaChanged={onMediaChanged}
                  product={product}
                  onCancel={() => setEditing(null)}
                  onSaved={() => {
                    onChanged();
                    setEditing(null);
                  }}
                />
              ) : (
                <ProductCard
                  product={product}
                  fallback={fallbacks.get(product.id)}
                  currency={currency}
                  canEdit={canEdit}
                  onEdit={() => {
                    setCreating(false);
                    setEditing(product.id);
                  }}
                  onPatch={(changes) => onPatch(product, changes)}
                  onRemove={() => onRemove(product)}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      {canEdit && (
        <div className="mt-3">
          {creating ? (
            <ProductForm
              tenantId={tenantId}
              currency={currency}
              media={media}
              onMediaChanged={onMediaChanged}
              onCancel={() => setCreating(false)}
              onSaved={() => {
                onChanged();
                setCreating(false);
              }}
            />
          ) : (
            products.length > 0 && (
              <GhostButton
                type="button"
                onClick={() => {
                  setEditing(null);
                  setCreating(true);
                }}
                icon={<Icon name="plus" className="size-4" />}
              >
                Ajouter un article
              </GhostButton>
            )
          )}
        </div>
      )}
    </div>
  );
}

function ProductCard({
  product,
  fallback,
  currency,
  canEdit,
  onEdit,
  onPatch,
  onRemove,
}: {
  product: Product;
  fallback?: string;
  currency: string;
  canEdit: boolean;
  onEdit: () => void;
  onPatch: (changes: Partial<Product>) => void;
  onRemove: () => void;
}) {
  const [stock, setStock] = useState(product.stock === null ? "" : String(product.stock));

  function commitStock() {
    const next = stock.trim() === "" ? null : Math.max(0, Number(stock) || 0);
    if (next !== product.stock) onPatch({ stock: next });
  }

  return (
    <Card className={product.active ? "" : "opacity-60"}>
      {/*
        Toujours une vignette, même sans média téléversé.

        Une grille de cartes vides ressemble à une boutique fermée. L'image
        d'ambiance est choisie d'après le nom de l'article et reste stable
        d'un affichage à l'autre — et elle s'efface dès que le salon met la
        sienne.
      */}
      <ProductMedia
        id={product.id}
        name={product.name}
        url={product.image_url}
        type={product.image_type}
        fallback={fallback}
        className="mb-2 aspect-square w-full rounded-lg object-cover"
      />

      <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-ink">
        <span className="min-w-0 truncate">{product.name}</span>
        {!product.active && <Badge>Retiré</Badge>}
      </p>

      <p className="tabular mt-0.5 text-sm text-salon">
        {formatPrice(product.price, currency)}
        <span className="ml-1 text-xs text-subtle">{product.unit_label}</span>
      </p>

      <div className="mt-2.5 flex items-center gap-1.5">
        <label className="flex min-w-0 items-center gap-1.5">
          <span className="sr-only">Stock de {product.name}</span>
          <input
            value={stock}
            onChange={(event) => setStock(event.target.value)}
            onBlur={commitStock}
            disabled={!canEdit}
            inputMode="numeric"
            placeholder="∞"
            aria-label={`Stock de ${product.name}`}
            className={`tabular w-16 rounded-lg border bg-surface px-2 py-1.5 text-center text-sm text-ink ${
              product.active && !product.in_stock
                ? "border-amber-500"
                : "border-line"
            }`}
          />
        </label>
        <span className="min-w-0 text-xs text-subtle">
          {product.stock === null
            ? "toujours dispo."
            : product.in_stock
              ? product.is_low
                ? "bientôt épuisé"
                : "en stock"
              : "rupture"}
        </span>
      </div>

      {canEdit && (
        /*
          Trois actions, séparées par l'espace et la couleur — plus par des
          points médians.

          À deux actions les points tenaient sur une ligne ; à trois, dans une
          demi-carte de téléphone, la ligne se casse et laisse un « · »
          orphelin en bout de ligne. La couleur suffit à distinguer les trois :
          « Modifier » porte celle du salon parce que c'est le geste courant —
          corriger un prix qui a bougé —, « Retirer » reste discret, et
          « Supprimer » est le seul en rouge.
        */
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line pt-2.5">
          <button
            type="button"
            onClick={onEdit}
            className="text-xs font-medium text-salon underline-offset-2 hover:underline"
          >
            Modifier
          </button>
          <button
            type="button"
            onClick={() => onPatch({ active: !product.active })}
            className="text-xs text-muted underline-offset-2 hover:text-ink hover:underline"
          >
            {product.active ? "Retirer" : "Remettre"}
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="text-xs text-danger underline-offset-2 hover:underline"
          >
            Supprimer
          </button>
        </div>
      )}
    </Card>
  );
}

/**
 * Le formulaire d'un article — le même pour l'ajouter et pour le corriger.
 *
 * Deux formulaires séparés auraient dérivé : le prix modifiable ici, la
 * description seulement là, et la boutique se serait retrouvée avec des
 * champs que l'on peut remplir une fois et plus jamais. Passer `product`
 * bascule en modification, l'omettre en création — rien d'autre ne change.
 */
function ProductForm({
  tenantId,
  currency,
  media,
  onMediaChanged,
  product,
  onCancel,
  onSaved,
}: {
  tenantId: string;
  currency: string;
  media: PickableMedia[];
  onMediaChanged: () => void;
  /** Absent : on crée. Présent : on corrige celui-là. */
  product?: Product;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(product?.name ?? "");
  const [price, setPrice] = useState(product ? priceInput(product.price) : "");
  const [unit, setUnit] = useState(product?.unit ?? "piece");
  const [description, setDescription] = useState(product?.description ?? "");
  const [stock, setStock] = useState(
    product?.stock == null ? "" : String(product.stock),
  );
  const [threshold, setThreshold] = useState(
    product ? String(product.low_stock_at) : "3",
  );
  const [image, setImage] = useState<string | null>(product?.image ?? null);
  const [pending, setPending] = useState(false);

  async function submit(event: { preventDefault: () => void }) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;

    const body = {
      name: trimmed,
      description: description.trim(),
      // La virgule décimale est ce qu'on tape ici ; la refuser ferait
      // répondre au serveur « un nombre valide est requis » à quelqu'un qui
      // vient d'écrire un nombre parfaitement valide.
      price: price.trim() === "" ? "0" : price.trim().replace(",", "."),
      unit,
      stock: stock.trim() === "" ? null : Math.max(0, Number(stock) || 0),
      low_stock_at:
        threshold.trim() === "" ? 0 : Math.max(0, Number(threshold) || 0),
      image,
    };

    setPending(true);
    const ok = await toast.run(
      () =>
        dashboardFetch(
          product ? `/api/v1/products/${product.id}/` : "/api/v1/products/",
          {
            method: product ? "PATCH" : "POST",
            body: JSON.stringify(body),
          },
          tenantId,
        ),
      {
        success: product
          ? `« ${trimmed} » mis à jour.`
          : `« ${trimmed} » ajouté à votre boutique.`,
      },
    );
    setPending(false);
    if (ok) onSaved();
  }

  return (
    /* Un <div>, pas un <form> : ce bloc peut se retrouver dans un autre
       formulaire, et deux <form> imbriqués font recharger la page. */
    <div
      onKeyDown={(event) => {
        // Entrée valide, sauf dans la description : là, c'est un retour à la
        // ligne, et enregistrer à sa place ferait perdre la phrase en cours.
        if (event.key !== "Enter") return;
        if ((event.target as HTMLElement).tagName !== "INPUT") return;
        event.preventDefault();
        void submit(event);
      }}
      className="rounded-xl border border-dashed border-line bg-surface p-3"
    >
      <p className="mb-3 text-sm font-medium text-ink">
        {product ? `Modifier « ${product.name} »` : "Nouvel article"}
      </p>

      {/*
        Deux colonnes dès le téléphone pour les quatre champs courts.

        Un prix, une unité, un stock et un seuil empilés font six écrans de
        défilement pour corriger un chiffre ; côte à côte, le formulaire tient
        dans la main. Le nom et la description, eux, ont besoin de la largeur
        entière — ce sont les seuls à contenir des phrases.
      */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Field label="Nom" className="col-span-2 lg:col-span-4">
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={150}
            placeholder="Mèches kanekalon"
            className={inputClass}
          />
        </Field>

        <Field label={`Prix (${currency})`}>
          <input
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            inputMode="decimal"
            placeholder="0"
            className={`${inputClass} tabular`}
          />
        </Field>

        <Field label="Vendu">
          <select
            value={unit}
            onChange={(event) => setUnit(event.target.value)}
            className={inputClass}
          >
            {UNITS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Stock" hint="Vide = illimité.">
          <input
            value={stock}
            onChange={(event) => setStock(event.target.value)}
            inputMode="numeric"
            placeholder="∞"
            className={`${inputClass} tabular`}
          />
        </Field>

        <Field label="Seuil d'alerte" hint="Alerte en dessous.">
          <input
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
            inputMode="numeric"
            placeholder="3"
            className={`${inputClass} tabular`}
          />
        </Field>
      </div>

      <div className="mt-3">
        <Field
          label="Description (facultative)"
          hint="Longueur, couleur, marque… ce qu'une cliente demanderait au comptoir."
        >
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
            className={`${inputClass} resize-y`}
          />
        </Field>
      </div>

      <div className="mt-3">
        <MediaPicker
          tenantId={tenantId}
          assets={media}
          value={image}
          onChange={setImage}
          onUploaded={onMediaChanged}
          label="Photo (facultative)"
          hint="Une photo aide la cliente à reconnaître ce qu'elle achète."
          // Photo d'article : elle vit dans la boutique, pas dans les
          // réalisations du salon.
          kind="product"
          allowVideo
        />
      </div>

      <div className="mt-3 flex items-center gap-2">
        <Button
          type="button"
          pending={pending}
          disabled={!name.trim()}
          onClick={(event) => void submit(event)}
        >
          {product ? "Enregistrer" : "Ajouter"}
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

/**
 * « 12000.00 » se relit « 12000 ».
 *
 * L'API renvoie un décimal à deux chiffres ; le remettre tel quel dans la
 * case obligerait à effacer des centimes qu'on n'a jamais saisis avant de
 * pouvoir corriger le prix.
 */
function priceInput(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

/* -------------------------------------------------------------------------
 * À prévoir
 * ---------------------------------------------------------------------- */

function ToBring({
  tenantId,
  canEdit,
  requirements,
  services,
  products,
  currency,
  loading,
  onChanged,
}: {
  tenantId: string;
  canEdit: boolean;
  requirements: Requirement[];
  services: ServiceRow[];
  products: Product[];
  currency: string;
  loading: boolean;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  // Même règle que pour les articles : une seule fourniture ouverte à la
  // fois, sinon on enregistre celle du voisin.
  const [editing, setEditing] = useState<string | null>(null);

  const byService = useMemo(() => {
    const map = new Map<string, Requirement[]>();
    for (const requirement of requirements) {
      const bucket = map.get(requirement.service);
      if (bucket) bucket.push(requirement);
      else map.set(requirement.service, [requirement]);
    }
    return map;
  }, [requirements]);

  /**
   * Une seule fonction pour créer et pour corriger.
   *
   * Le formulaire ne sait pas laquelle des deux il sert : il rend un
   * contenu, cette fonction décide de la route et du verbe. C'est ce qui
   * garantit qu'un champ ajouté au formulaire est réellement enregistrable
   * dans les deux sens — le défaut qu'on vient de corriger, où `detail`
   * existait côté serveur et n'était modifiable nulle part.
   */
  async function save(
    payload: RequirementDraft,
    requirement?: Requirement,
  ): Promise<boolean> {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          requirement
            ? `/api/v1/requirements/${requirement.id}/`
            : "/api/v1/requirements/",
          {
            method: requirement ? "PATCH" : "POST",
            body: JSON.stringify(payload),
          },
          tenantId,
        ),
      {
        success: requirement
          ? `« ${payload.label} » mise à jour.`
          : "Fourniture ajoutée.",
      },
    );
    if (ok) onChanged();
    return ok;
  }

  async function remove(requirement: Requirement) {
    const ok = await toast.run(
      () =>
        dashboardFetch(
          `/api/v1/requirements/${requirement.id}/`,
          { method: "DELETE" },
          tenantId,
        ),
      { success: `« ${requirement.label} » retirée.` },
    );
    if (ok) onChanged();
  }

  async function toggleOffer(requirement: Requirement, product: Product) {
    const attached = requirement.product_ids.includes(product.id);

    const ok = await toast.run(
      async () => {
        if (attached) {
          const page = await dashboardFetch<Page<{ id: string; product: string }>>(
            `/api/v1/requirement-products/?requirement=${requirement.id}`,
            {},
            tenantId,
          );
          const link = rows(page).find((row) => row.product === product.id);
          if (link)
            await dashboardFetch(
              `/api/v1/requirement-products/${link.id}/`,
              { method: "DELETE" },
              tenantId,
            );
          return;
        }
        await dashboardFetch(
          "/api/v1/requirement-products/",
          {
            method: "POST",
            body: JSON.stringify({
              requirement: requirement.id,
              product: product.id,
            }),
          },
          tenantId,
        );
      },
      {
        success: attached
          ? `« ${product.name} » n'est plus proposé pour cette fourniture.`
          : `« ${product.name} » est proposé pour cette fourniture.`,
      },
    );
    if (ok) onChanged();
  }

  return (
    <div>
      <p className="mb-4 text-sm text-muted">
        Ce que la cliente doit apporter. Affiché avant la réservation — même
        sans rien vendre, l&apos;écrire évite le rendez-vous annulé sur place.
      </p>

      {loading && <Skeleton rows={2} />}

      {!loading && requirements.length === 0 && !creating && (
        <EmptyState
          title="Rien à prévoir pour l'instant"
          action={
            canEdit &&
            services.length > 0 && (
              <Button type="button" onClick={() => setCreating(true)}>
                Ajouter une fourniture
              </Button>
            )
          }
        >
          « 3 paquets de mèches », « une perruque », « votre kit »… Vos clientes
          le verront au moment de réserver.
        </EmptyState>
      )}

      {services.map((service) => {
        const list = byService.get(service.id) ?? [];
        if (list.length === 0) return null;

        return (
          <div key={service.id} className="mb-6">
            <SectionTitle>{service.name}</SectionTitle>
            <ul className="space-y-2">
              {list.map((requirement) => (
                <li
                  key={requirement.id}
                  className="rounded-xl border border-line bg-surface p-3"
                >
                  {editing === requirement.id ? (
                    <RequirementForm
                      services={services}
                      requirement={requirement}
                      onCancel={() => setEditing(null)}
                      onSave={async (payload) => {
                        const ok = await save(payload, requirement);
                        if (ok) setEditing(null);
                        return ok;
                      }}
                    />
                  ) : (
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-medium text-ink">
                          {requirement.label}
                          {requirement.mandatory ? (
                            <Badge tone="warning">Indispensable</Badge>
                          ) : (
                            <Badge>Facultatif</Badge>
                          )}
                        </p>
                        {/* La précision était enregistrable côté serveur,
                            affichée à la cliente au moment de réserver, et
                            invisible ici : le salon ne pouvait ni la lire ni
                            la corriger. */}
                        {requirement.detail && (
                          <p className="mt-0.5 text-xs text-muted">
                            {requirement.detail}
                          </p>
                        )}
                      </div>
                      {canEdit && (
                        <div className="flex shrink-0 items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setCreating(false);
                              setEditing(requirement.id);
                            }}
                            className="text-xs font-medium text-salon underline-offset-2 hover:underline"
                          >
                            Modifier
                          </button>
                          <span aria-hidden className="text-subtle">
                            ·
                          </span>
                          <button
                            type="button"
                            onClick={() => remove(requirement)}
                            className="text-xs text-danger underline-offset-2 hover:underline"
                          >
                            Supprimer
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {products.length > 0 && (
                    <div className="mt-2.5 border-t border-line pt-2.5">
                      <p className="mb-1.5 text-xs text-subtle">
                        Ce que vous proposez à celles qui ne l&apos;ont pas :
                      </p>
                      <ul className="grid grid-cols-2 gap-1.5 md:grid-cols-3 lg:grid-cols-4">
                        {products.map((product) => {
                          const on = requirement.product_ids.includes(product.id);
                          return (
                            <li key={product.id}>
                              <button
                                type="button"
                                disabled={!canEdit}
                                onClick={() => toggleOffer(requirement, product)}
                                aria-pressed={on}
                                className={`w-full rounded-lg border px-2.5 py-2 text-left transition ${
                                  on
                                    ? "border-salon bg-salon-soft text-ink"
                                    : "border-line bg-surface text-muted hover:border-line-strong"
                                } disabled:opacity-60`}
                              >
                                <span className="block truncate text-xs font-medium">
                                  {product.name}
                                </span>
                                <span className="tabular text-xs text-subtle">
                                  {formatPrice(product.price, currency)}
                                </span>
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}

      {canEdit && services.length > 0 && (
        <div>
          {creating ? (
            <div className="rounded-xl border border-dashed border-line bg-surface p-3">
              <RequirementForm
                services={services}
                onCancel={() => setCreating(false)}
                onSave={async (payload) => {
                  const ok = await save(payload);
                  if (ok) setCreating(false);
                  return ok;
                }}
              />
            </div>
          ) : (
            requirements.length > 0 && (
              <GhostButton
                type="button"
                onClick={() => {
                  setEditing(null);
                  setCreating(true);
                }}
                icon={<Icon name="plus" className="size-4" />}
              >
                Ajouter une fourniture
              </GhostButton>
            )
          )}
        </div>
      )}
    </div>
  );
}

/** Ce que le formulaire renvoie, et ce que l'API attend — la même forme. */
interface RequirementDraft {
  service: string;
  label: string;
  detail: string;
  mandatory: boolean;
}

/**
 * Le formulaire d'une fourniture, partagé lui aussi entre l'ajout et la
 * correction. `requirement` absent : on crée.
 */
function RequirementForm({
  services,
  requirement,
  onSave,
  onCancel,
}: {
  services: ServiceRow[];
  requirement?: Requirement;
  onSave: (payload: RequirementDraft) => Promise<boolean>;
  onCancel: () => void;
}) {
  const [label, setLabel] = useState(requirement?.label ?? "");
  const [detail, setDetail] = useState(requirement?.detail ?? "");
  const [serviceId, setServiceId] = useState(
    requirement?.service ?? services[0]?.id ?? "",
  );
  const [mandatory, setMandatory] = useState(requirement?.mandatory ?? true);
  const [pending, setPending] = useState(false);

  async function submit(event: { preventDefault: () => void }) {
    event.preventDefault();
    const trimmed = label.trim();
    if (!trimmed || !serviceId) return;

    setPending(true);
    await onSave({
      service: serviceId,
      label: trimmed,
      detail: detail.trim(),
      mandatory,
    });
    setPending(false);
  }

  return (
    <div
      onKeyDown={(event) => {
        if (event.key !== "Enter") return;
        if ((event.target as HTMLElement).tagName !== "INPUT") return;
        event.preventDefault();
        void submit(event);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Ce qu'il faut prévoir">
          <input
            autoFocus
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            maxLength={150}
            placeholder="3 paquets de mèches"
            className={inputClass}
          />
        </Field>

        <Field label="Pour quelle prestation">
          <select
            value={serviceId}
            onChange={(event) => setServiceId(event.target.value)}
            className={inputClass}
          >
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {service.name}
              </option>
            ))}
          </select>
        </Field>

        <Field
          label="Précision (facultative)"
          hint="Longueur, couleur, quantité conseillée… La cliente la lit avant de réserver."
          className="sm:col-span-2"
        >
          <input
            value={detail}
            onChange={(event) => setDetail(event.target.value)}
            maxLength={255}
            placeholder="Longueur 26 pouces, couleur 1B"
            className={inputClass}
          />
        </Field>
      </div>

      <label className="mt-3 flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          checked={mandatory}
          onChange={(event) => setMandatory(event.target.checked)}
          className="size-4 accent-[var(--color-salon)]"
        />
        Indispensable — la cliente devra dire si elle l&apos;apporte
      </label>

      <div className="mt-3 flex items-center gap-2">
        <Button
          type="button"
          pending={pending}
          disabled={!label.trim()}
          onClick={(event) => void submit(event)}
        >
          {requirement ? "Enregistrer" : "Ajouter"}
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
