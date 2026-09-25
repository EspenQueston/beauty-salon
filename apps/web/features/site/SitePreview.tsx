"use client";

/**
 * Aperçu du mini-site, avant toute inscription.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi donner ça gratuitement
 * ---------------------------------------------------------------------------
 *
 * Le produit demandait de créer un compte pour voir à quoi ressemblerait sa
 * page — c'est-à-dire de payer d'un formulaire avant d'avoir la moindre
 * preuve que ça vaut le coup. Ici on rend d'abord quelque chose d'utile :
 * son nom, ses couleurs, son adresse réelle, vérifiée en direct.
 *
 * Le résultat n'est pas décoratif. L'adresse est réellement interrogée
 * auprès de l'API : « blondrose.localhost est libre » est une information
 * vraie, obtenue sans rien donner en échange.
 *
 * Et ce qu'on a composé est conservé : le bouton d'inscription emporte le
 * nom, l'adresse et la palette. On ne recommence pas de zéro de l'autre
 * côté du formulaire — ce qui est autant une politesse qu'une raison de
 * franchir l'étape.
 */

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { checkSlug } from "@/lib/dashboard";
import { appUrl } from "@/lib/site";
import { SLUG_MIN, toSlug } from "@/lib/slug";
import { PALETTES } from "./palettes";

type SlugState = "idle" | "checking" | "free" | "taken";

export function SitePreview() {
  const t = useTranslations("site");
  const c = useTranslations("commun");
  const [name, setName] = useState("");
  const [palette, setPalette] = useState<(typeof PALETTES)[number]>(PALETTES[0]);
  /** Dernière réponse du serveur, avec l'adresse à laquelle elle répond. */
  const [checked, setChecked] = useState<{
    slug: string;
    available: boolean;
    hostname: string;
  } | null>(null);

  const slug = toSlug(name);
  const displayName = name.trim() || t("apercuVitrine.salonParDefaut");

  /*
   * L'état affiché est **déduit**, pas stocké.
   *
   * Le garder dans un `useState` obligeait à le corriger depuis l'effet à
   * chaque frappe — un rendu de plus par caractère, et une seconde source de
   * vérité qui pouvait désigner une autre adresse que celle tapée. Ici, une
   * réponse ne compte que si elle porte sur l'adresse courante ; sinon on
   * est, par construction, en train de vérifier.
   */
  const slugState: SlugState =
    slug.length < SLUG_MIN
      ? "idle"
      : checked?.slug === slug
        ? checked.available
          ? "free"
          : "taken"
        : "checking";

  const hostname = checked?.slug === slug ? checked.hostname : "";

  useEffect(() => {
    if (slug.length < SLUG_MIN) return;

    let cancelled = false;

    // Court délai : évite une requête par touche frappée.
    const handle = setTimeout(() => {
      checkSlug(slug)
        .then((result) => {
          if (cancelled) return;
          setChecked({
            slug,
            available: result.available,
            hostname: result.hostname,
          });
        })
        .catch(() => {
          // Le serveur n'a pas répondu : on reste en « vérification »
          // plutôt que d'annoncer une disponibilité qu'on ignore.
        });
    }, 400);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [slug]);

  // Ce qui a été composé accompagne l'inscription : le formulaire arrive
  // pré-rempli plutôt que vide.
  const signupHref = `${appUrl}/inscription?${new URLSearchParams({
    ...(name.trim() ? { nom: name.trim() } : {}),
    ...(slug.length >= SLUG_MIN ? { slug } : {}),
    // Les trois couleurs voyagent, pas le nom de la palette : le serveur
    // enregistre des couleurs, et une liste de noms figée finirait par
    // diverger entre les deux écrans.
    primaire: palette.primary,
    secondaire: palette.accent,
    fond: palette.surface,
  })}`;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr] lg:items-center">
      {/* ------------------------------------------------------ commandes */}
      <div>
        <label
          htmlFor="apercu-nom"
          className="mb-1.5 block text-sm font-medium text-ink"
        >
          {t("apercuVitrine.nomChamp")}
        </label>
        <input
          id="apercu-nom"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("apercu.exemple")}
          maxLength={60}
          className="w-full rounded-xl border border-line bg-surface px-4 py-3 text-ink transition focus:border-salon"
        />

        <p className="mt-2 min-h-5 text-sm" aria-live="polite">
          {slug.length >= SLUG_MIN && slugState === "checking" && (
            <span className="text-subtle">{t("adresse.verification")}</span>
          )}
          {slugState === "free" && (
            <span className="text-success">
              {t("adresse.libre", { adresse: hostname })}
            </span>
          )}
          {slugState === "taken" && (
            <span className="text-danger">
              {t("adresse.prise", { adresse: hostname })}
            </span>
          )}
        </p>

        <p className="mb-2 mt-5 text-sm font-medium text-ink">
          {t("apercuVitrine.couleurs")}
        </p>
        <div className="flex flex-wrap gap-2">
          {PALETTES.map((entry) => {
            const active = entry.cle === palette.cle;
            return (
              <button
                key={entry.cle}
                type="button"
                onClick={() => setPalette(entry)}
                aria-pressed={active}
                title={t(`palettes.${entry.cle}`)}
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-xs transition ${
                  active
                    ? "border-salon bg-salon-soft text-ink"
                    : "border-line bg-surface text-muted hover:bg-surface-hover"
                }`}
              >
                <span className="flex">
                  <span
                    className="size-3.5 rounded-full ring-1 ring-black/10"
                    style={{ background: entry.primary }}
                  />
                  <span
                    className="-ml-1 size-3.5 rounded-full ring-1 ring-black/10"
                    style={{ background: entry.accent }}
                  />
                </span>
                <span className="hidden sm:inline">
                  {t(`palettes.${entry.cle}`)}
                </span>
              </button>
            );
          })}
        </div>

        <a
          href={signupHref}
          className="mt-6 inline-flex items-center justify-center rounded-xl bg-salon px-6 py-3.5 font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:brightness-110"
        >
          {slugState === "free"
            ? t("apercuVitrine.reserverAdresse", { adresse: hostname })
            : c("creerSalon")}
        </a>

        <p className="mt-2 text-xs text-subtle">{t("apercuVitrine.suivi")}</p>
      </div>

      {/* -------------------------------------------------------- aperçu */}
      <div
        className="rounded-3xl border border-line p-4 shadow-card transition-colors duration-500 sm:p-6"
        style={{ background: palette.surface }}
      >
        <p className="mb-3 text-center text-xs font-medium uppercase tracking-[0.12em] text-black/40">
          {t("apercuVitrine.direct")}
        </p>

        <div className="overflow-hidden rounded-2xl bg-white shadow-lg">
          {/* Bandeau : dégradé de la palette, comme sur un vrai mini-site. */}
          <div
            className="flex h-24 items-end p-4 transition-[background] duration-500 sm:h-28"
            style={{
              backgroundImage: `linear-gradient(135deg, ${palette.primary} 0%, ${palette.accent} 140%)`,
            }}
          >
            <span
              className="flex size-12 items-center justify-center rounded-2xl bg-white text-lg font-semibold shadow-md"
              style={{ color: palette.primary }}
            >
              {displayName.slice(0, 1).toUpperCase()}
            </span>
          </div>

          <div className="p-4 sm:p-5">
            <p
              className="text-lg font-semibold transition-colors duration-500"
              style={{ color: palette.primary }}
            >
              {displayName}
            </p>
            <p className="mt-0.5 text-sm text-black/50">
              {hostname || t("apercuVitrine.hoteExemple")}
            </p>

            <div className="mt-4 space-y-2">
              {[
                {
                  label: t("apercuVitrine.prestations.tresses"),
                  price: "12 000",
                },
                { label: t("apercuVitrine.prestations.soin"), price: "8 000" },
              ].map((row) => (
                <div
                  key={row.label}
                  className="flex items-center justify-between rounded-xl border border-black/[0.06] px-3 py-2.5"
                >
                  <span className="text-sm text-black/75">{row.label}</span>
                  <span
                    className="tabular text-sm font-semibold transition-colors duration-500"
                    style={{ color: palette.primary }}
                  >
                    {row.price}
                  </span>
                </div>
              ))}
            </div>

            <span
              className="mt-4 block rounded-xl py-2.5 text-center text-sm font-semibold text-white transition-[background] duration-500"
              style={{ background: palette.primary }}
            >
              {t("apercuVitrine.reserver")}
            </span>
          </div>
        </div>

        <p className="mt-3 text-center text-xs text-black/40">
          {t("apercuVitrine.noteExemple")}
        </p>
      </div>
    </div>
  );
}
