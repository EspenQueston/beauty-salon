"use client";

/**
 * « Ce qu'il faut prévoir » : l'étape qui évite le rendez-vous annulé sur place.
 *
 * ---------------------------------------------------------------------------
 * Le problème
 * ---------------------------------------------------------------------------
 *
 * Beaucoup de prestations demandent une fourniture que la cliente apporte
 * elle-même : des mèches, une perruque, un kit. Le salon le sait, la cliente
 * pas toujours — et elle arrive les mains vides pour un rendez-vous de quatre
 * heures qu'il faut renvoyer.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi deux réponses et pas une case à cocher
 * ---------------------------------------------------------------------------
 *
 * « J'apporte » et « J'achète ici » sont deux intentions, pas un oui/non. Une
 * simple case à cocher aurait forcé le salon à choisir entre informer et
 * vendre, alors que les deux cohabitent : certaines clientes ont déjà leurs
 * mèches, d'autres découvrent qu'il en faut.
 *
 * Ce qu'on refuse, ce n'est pas la cliente qui apporte son matériel — on la
 * croit sur parole, lui refuser sa propre perruque serait absurde. C'est le
 * **silence** : réserver quatre heures sans avoir dit ce qu'on fait des
 * mèches finit toujours de la même façon.
 *
 * ---------------------------------------------------------------------------
 * Les articles en rupture restent affichés
 * ---------------------------------------------------------------------------
 *
 * Barrés, pas cachés. Les faire disparaître laisserait croire que le salon
 * n'en vend pas, et la cliente irait chercher ailleurs ce qu'elle aurait pu
 * avoir la semaine suivante.
 */

import { useTranslations } from "next-intl";
import { formatPrice } from "@/lib/format";
import type { ServiceRequirement } from "@/lib/types";
import { SalonIcon } from "@/features/salon/icons";
import { ProductMedia } from "./ProductMedia";
import { productIllustrations } from "@/lib/illustrations";

export interface Basket {
  /** Exigences pour lesquelles la cliente dit apporter le nécessaire. */
  owned: string[];
  /** Articles achetés : identifiant → quantité. */
  items: Record<string, number>;
}

export const EMPTY_BASKET: Basket = { owned: [], items: {} };

const CARD =
  "rounded-2xl border border-[var(--site-line)] bg-[var(--site-surface)] shadow-[0_1px_3px_rgb(23_23_28_/_0.06)]";

/** Total des articles retenus, au prix affiché. */
export function basketTotal(
  requirements: ServiceRequirement[],
  basket: Basket,
): number {
  return requirements.reduce((sum, requirement) => {
    return (
      sum +
      requirement.products.reduce((inner, product) => {
        const quantity = basket.items[product.id] ?? 0;
        return inner + quantity * Number(product.price);
      }, 0)
    );
  }, 0);
}

/** Exigences indispensables auxquelles rien ne répond encore. */
export function unanswered(
  requirements: ServiceRequirement[],
  basket: Basket,
): ServiceRequirement[] {
  return requirements.filter((requirement) => {
    if (!requirement.mandatory) return false;
    if (basket.owned.includes(requirement.id)) return false;
    return !requirement.products.some((product) => basket.items[product.id]);
  });
}

export function RequirementsStep({
  requirements,
  basket,
  currency,
  onChange,
}: {
  requirements: ServiceRequirement[];
  basket: Basket;
  currency: string;
  onChange: (basket: Basket) => void;
}) {
  const t = useTranslations("reservation");
  // Tous les articles de l'étape, toutes exigences confondues : deux
  // fournitures voisines ne doivent pas porter la même photo.
  const fallbacks = productIllustrations(
    requirements.flatMap((requirement) => requirement.products),
  );

  function declareOwned(requirement: ServiceRequirement) {
    const owned = basket.owned.includes(requirement.id)
      ? basket.owned.filter((id) => id !== requirement.id)
      : [...basket.owned, requirement.id];

    // Dire « je l'apporte » retire ce qu'on avait mis au panier pour cette
    // exigence : garder les deux laisserait payer un article dont on vient
    // de dire qu'on n'en a pas besoin.
    const items = { ...basket.items };
    if (!basket.owned.includes(requirement.id)) {
      for (const product of requirement.products) delete items[product.id];
    }

    onChange({ owned, items });
  }

  function setQuantity(
    productId: string,
    quantity: number,
    requirementId: string,
  ) {
    const items = { ...basket.items };
    if (quantity <= 0) delete items[productId];
    else items[productId] = Math.min(quantity, 20);

    // Acheter répond à l'exigence : la déclaration « j'apporte » tombe.
    const owned = basket.owned.filter((id) => id !== requirementId);
    onChange({ owned, items });
  }

  return (
    <ul className="space-y-3">
      {requirements.map((requirement) => {
        const owned = basket.owned.includes(requirement.id);
        const bought = requirement.products.some(
          (product) => basket.items[product.id],
        );
        const answered = owned || bought;

        return (
          <li key={requirement.id} className={`${CARD} p-4`}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 font-medium text-[var(--site-ink)]">
                  {requirement.label}
                  {requirement.mandatory ? (
                    <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[0.7rem] font-medium text-amber-700 dark:text-amber-400">
                      Indispensable
                    </span>
                  ) : (
                    <span className="rounded-full bg-black/[0.06] px-2 py-0.5 text-[0.7rem] text-[var(--site-muted)] dark:bg-white/10">
                      Facultatif
                    </span>
                  )}
                </p>
                {requirement.detail && (
                  <p className="mt-0.5 text-sm text-[var(--site-muted)]">
                    {requirement.detail}
                  </p>
                )}
              </div>

              {answered && (
                <SalonIcon
                  name="check"
                  aria-label={t("exigences.regle")}
                  className="size-5 shrink-0 text-emerald-600"
                />
              )}
            </div>

            {/* Les deux réponses, côte à côte et de même poids : le salon ne
                pousse pas à l'achat, il propose une solution à celles qui
                n'ont rien. */}
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => declareOwned(requirement)}
                aria-pressed={owned}
                className={`rounded-xl border px-3 py-2.5 text-left text-sm transition ${
                  owned
                    ? "border-[var(--salon-primary)] bg-[var(--salon-primary)]/[0.08] text-[var(--site-ink)]"
                    : "border-[var(--site-line)] text-[var(--site-muted)] hover:border-[var(--salon-primary)]/50"
                }`}
              >
                <span className="block font-medium">Je l&apos;apporte</span>
                <span className="text-xs text-[var(--site-subtle)]">
                  {t("exigences.rienAPayer")}
                </span>
              </button>

              <div
                className={`rounded-xl border px-3 py-2.5 text-sm ${
                  bought
                    ? "border-[var(--salon-primary)] bg-[var(--salon-primary)]/[0.08]"
                    : "border-[var(--site-line)]"
                }`}
              >
                <span className="block font-medium text-[var(--site-ink)]">
                  {requirement.products.length > 0
                    ? t("exigences.jeLAchete")
                    : t("exigences.aApporter")}
                </span>
                <span className="text-xs text-[var(--site-subtle)]">
                  {requirement.products.length > 0
                    ? t("exigences.auSalonJourMeme")
                    : t("exigences.salonNenVendPas")}
                </span>
              </div>
            </div>

            {requirement.products.length > 0 && (
              <ul className="mt-2.5 space-y-2">
                {requirement.products.map((product) => {
                  const quantity = basket.items[product.id] ?? 0;

                  return (
                    <li
                      key={product.id}
                      className={`flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border p-2.5 ${
                        quantity > 0
                          ? "border-[var(--salon-primary)]/50"
                          : "border-[var(--site-line)]"
                      } ${product.available ? "" : "opacity-60"}`}
                    >
                      {/* Toujours une vignette : une ligne sans image se lit
                          comme un article indisponible. */}
                      <ProductMedia
                        id={product.id}
                        name={product.name}
                        url={product.image}
                        type={product.image_type}
                        width={120}
                        fallback={fallbacks.get(product.id)}
                        className="size-12 shrink-0 rounded-lg object-cover"
                      />

                      <div className="min-w-0 flex-1">
                        <p
                          className={`truncate text-sm font-medium text-[var(--site-ink)] ${
                            product.available ? "" : "line-through"
                          }`}
                        >
                          {product.name}
                        </p>
                        <p className="tabular text-sm text-[var(--salon-ink)]">
                          {formatPrice(product.price, currency)}
                          {!product.available && (
                            <span className="ml-2 text-xs font-medium text-[var(--site-subtle)]">
                              en rupture
                            </span>
                          )}
                        </p>
                      </div>

                      {product.available && (
                        <div className="flex shrink-0 items-center gap-1">
                          <button
                            type="button"
                            onClick={() =>
                              setQuantity(
                                product.id,
                                quantity - 1,
                                requirement.id,
                              )
                            }
                            disabled={quantity === 0}
                            aria-label={t("exigences.retirer", {
                              produit: product.name,
                            })}
                            className="flex size-8 items-center justify-center rounded-lg border border-[var(--site-line)] text-[var(--site-muted)] transition disabled:opacity-40"
                          >
                            −
                          </button>
                          {/*
                            Pas d'`aria-live` ici.

                            La quantité est le résultat direct du bouton
                            qu'on vient de presser, et ce bouton se nomme
                            déjà (« Ajouter un… »). Le total, lui, est la
                            conséquence *indirecte* : c'est lui qui mérite
                            d'être annoncé. Les deux ensemble faisaient deux
                            annonces pour un seul geste, et la plupart des
                            lecteurs d'écran coupent la première.
                          */}
                          <span className="tabular w-7 text-center text-sm font-medium text-[var(--site-ink)]">
                            {quantity}
                          </span>
                          <button
                            type="button"
                            onClick={() =>
                              setQuantity(
                                product.id,
                                quantity + 1,
                                requirement.id,
                              )
                            }
                            aria-label={t("exigences.ajouter", {
                              produit: product.name,
                            })}
                            className="flex size-8 items-center justify-center rounded-lg border border-[var(--site-line)] text-[var(--site-muted)] transition hover:border-[var(--salon-primary)]"
                          >
                            +
                          </button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}
