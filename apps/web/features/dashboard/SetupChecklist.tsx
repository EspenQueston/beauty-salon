"use client";

/**
 * Mise en route du salon.
 *
 * Elle disparaît d'elle-même une fois tout fait : un tableau de bord qui
 * garde un bandeau d'accueil pour toujours finit par être ignoré, y compris
 * quand il a quelque chose d'important à dire.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi elle ne démarre jamais à zéro
 * ---------------------------------------------------------------------------
 *
 * S'inscrire est une étape réelle, et poser ses horaires aussi — la grille de
 * départ est créée à l'inscription. Afficher « 0 % » après ce travail est
 * faux, et décourage précisément au moment où il faudrait encourager.
 *
 * Le compteur crédite donc ce qui est réellement acquis. Il ne triche pas
 * dans l'autre sens non plus : une case ne se coche que sur une donnée
 * vérifiable, jamais sur une visite d'écran.
 */

// Les liens portent la langue (/en/…) : sans elle, chaque clic en anglais
// passerait par une redirection.
import { Lien as Link } from "@/features/ui/Lien";
import { useMemo } from "react";

import { Card, SectionTitle } from "@/features/ui";
import { useTranslations } from "next-intl";
import { Icon, type IconName } from "./icons";
import { useDashboard } from "./DashboardShell";
import { rows, useResource, type Page } from "./useResource";

interface Counted {
  id: string;
}

interface Step {
  key: string;
  label: string;
  done: boolean;
  href: string;
  hint: string;
  icon: IconName;
  /** Une étape qui ne dépend pas du salon : il ne peut rien y faire. */
  waiting?: boolean;
}

export function SetupChecklist() {
  const t = useTranslations("pro.miseEnRoute");
  const { membership } = useDashboard();
  const tenantId = membership.tenant.id;
  const canEdit = ["owner", "manager"].includes(membership.role);

  const services = useResource<Page<Counted>>(
    "/api/v1/services/?page_size=1",
    tenantId,
  );
  const staff = useResource<Page<Counted>>(
    "/api/v1/staff-members/?page_size=1",
    tenantId,
  );
  const media = useResource<Page<Counted>>(
    "/api/v1/media/?page_size=1",
    tenantId,
  );
  const hours = useResource<Page<Counted>>("/api/v1/business-hours/", tenantId);

  const loaded =
    services.data !== null &&
    staff.data !== null &&
    media.data !== null &&
    hours.data !== null;

  const steps = useMemo<Step[]>(() => {
    const count = (page: Page<Counted> | null) =>
      page && !Array.isArray(page) ? page.count : rows(page).length;

    return [
      {
        key: "compte",
        label: t("compte.titre"),
        done: true,
        href: "/profil",
        hint: t("compte.aide"),
        icon: "store",
      },
      {
        key: "horaires",
        label: t("horaires.titre"),
        done: count(hours.data) > 0,
        href: "/horaires",
        hint: t("horaires.aide"),
        icon: "clock",
      },
      {
        key: "prestations",
        label: t("prestations.titre"),
        done: count(services.data) > 0,
        href: "/prestations",
        hint: t("prestations.aide"),
        icon: "sparkles",
      },
      {
        key: "prestataires",
        label: t("prestataires.titre"),
        done: count(staff.data) > 0,
        href: "/prestataires",
        hint: t("prestataires.aide"),
        icon: "scissors",
      },
      {
        key: "photos",
        label: t("photos.titre"),
        done: count(media.data) > 0,
        href: "/galerie",
        hint: t("photos.aide"),
        icon: "image",
      },
      {
        key: "validation",
        label: t("validation.titre"),
        done: membership.tenant.status === "active",
        href: "/profil",
        hint: t("validation.aide"),
        icon: "external",
        waiting: true,
      },
    ];
  }, [
    services.data,
    staff.data,
    media.data,
    hours.data,
    membership.tenant.status,
    t,
  ]);

  const done = steps.filter((step) => step.done).length;
  const percent = Math.round((done / steps.length) * 100);

  // Rien à afficher tant qu'on ne sait pas, et plus rien une fois terminé.
  if (!loaded || done === steps.length || !canEdit) return null;

  const next = steps.find((step) => !step.done && !step.waiting);

  return (
    <Card className="mb-6">
      <SectionTitle>{t("titre")}</SectionTitle>

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-baseline gap-2">
          <span className="tabular text-3xl font-semibold text-ink">
            {percent}
          </span>
          <span className="text-lg text-muted">%</span>
        </div>

        <div className="min-w-[10rem] flex-1">
          <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
            <div
              className="h-full rounded-full bg-salon transition-[width] duration-700 ease-out"
              style={{ width: `${percent}%` }}
            />
          </div>
          <p className="mt-1.5 text-sm text-muted">
            {t("progression", { fait: done, total: steps.length })}
            {next && ` · ${t("aSuivre", { etape: next.label.toLowerCase() })}`}
          </p>
        </div>

        {next && (
          <Link
            href={next.href}
            className="inline-flex items-center gap-2 rounded-lg bg-salon px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:brightness-110"
          >
            {t("continuer")}
            <Icon name="check" className="size-4" />
          </Link>
        )}
      </div>

      <ul className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {steps.map((step) => (
          <li key={step.key}>
            <Link
              href={step.href}
              className={`lift flex h-full items-start gap-2.5 rounded-xl border p-3 transition ${
                step.done
                  ? "border-line bg-surface-muted"
                  : "border-line bg-surface hover:border-salon"
              }`}
            >
              <span
                className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full ${
                  step.done
                    ? "bg-success text-white"
                    : "border border-line-strong text-subtle"
                }`}
              >
                {step.done ? (
                  <Icon name="check" className="size-3" />
                ) : (
                  <Icon name={step.icon} className="size-3" />
                )}
              </span>

              <span className="min-w-0">
                <span
                  className={`block text-sm font-medium ${
                    step.done ? "text-muted line-through" : "text-ink"
                  }`}
                >
                  {step.label}
                </span>
                {!step.done && (
                  <span className="mt-0.5 block text-xs leading-relaxed text-subtle">
                    {step.hint}
                  </span>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
