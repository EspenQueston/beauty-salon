"use client";

/**
 * Vérification d'adresse, avant toute inscription.
 *
 * On donne un résultat utile — « blondrose.beautysalon.app est libre » —
 * sans rien demander en échange. C'est une information que la personne
 * cherchait vraiment, et elle repart avec, qu'elle s'inscrive ou non.
 *
 * Elle a aussi un effet de possession : une fois son adresse trouvée et
 * affichée à son nom, elle n'a plus envie de la laisser à quelqu'un d'autre.
 * Le formulaire d'inscription la reçoit pré-remplie, donc la personne
 * continue son geste au lieu d'en recommencer un.
 *
 * Aucun compte n'est créé ici, et l'adresse n'est pas réservée tant que
 * l'inscription n'est pas terminée : le bouton le dit, pour qu'on ne
 * découvre pas la nuance en revenant deux jours plus tard.
 */

import { useTranslations } from "next-intl";
import { useEffect, useId, useState } from "react";

import { checkSlug } from "@/lib/dashboard";
import { appUrl } from "@/lib/site";
import { toSlug } from "@/lib/slug";

type State = "idle" | "checking" | "free" | "taken" | "invalid";

const PLATFORM_DOMAIN = process.env.NEXT_PUBLIC_PLATFORM_DOMAIN ?? "localhost";

/**
 * @param nu Rendu sans la carte qui l'entoure, pour être posé dans un cadre
 *           à soi — ce que fait la mise en page du téléphone.
 */
export function AddressCheck({ nu = false }: { nu?: boolean } = {}) {
  const t = useTranslations("site");
  /*
   * L'identifiant du champ vient de React et n'est plus écrit en dur.
   *
   * La page d'accueil rend ce composant deux fois — une version pour le
   * téléphone, une pour le grand écran, un seul des deux étant affiché.
   * Deux `id="adresse-salon"` dans le même document rendraient
   * l'association entre l'intitulé et le champ imprévisible, et un lecteur
   * d'écran annoncerait l'un pour l'autre.
   */
  const champ = useId();
  const [name, setName] = useState("");
  /** Dernière réponse du serveur, avec l'adresse à laquelle elle répond. */
  const [answer, setAnswer] = useState<{ slug: string; free: boolean } | null>(
    null,
  );

  const slug = toSlug(name);

  /*
   * L'état affiché se déduit de la saisie et de la dernière réponse — il
   * n'est pas stocké. « Vide », « trop court » et « en cours » se savent
   * sans réseau ; les poser dans un `useState` depuis l'effet ajouterait un
   * rendu par frappe, et ferait clignoter le message.
   *
   * Comparer `answer.slug` à `slug` garantit qu'une réponse en retard ne
   * s'affiche jamais sous une adresse qu'on vient de modifier.
   */
  const state: State =
    slug.length === 0
      ? "idle"
      : slug.length < 3
        ? "invalid"
        : answer?.slug === slug
          ? answer.free
            ? "free"
            : "taken"
          : "checking";

  useEffect(() => {
    if (slug.length < 3) return;
    let cancelled = false;

    // Petit délai : évite une requête par touche frappée.
    const handle = setTimeout(() => {
      checkSlug(slug)
        .then((result) => {
          if (!cancelled) setAnswer({ slug, free: result.available });
        })
        .catch(() => {
          // Réseau indisponible : on reste sur « vérification », plutôt que
          // d'annoncer une disponibilité qu'on n'a pas pu vérifier.
        });
    }, 350);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [slug]);

  return (
    <div
      className={
        nu
          ? ""
          : "rounded-2xl border border-line bg-surface p-5 shadow-card sm:p-6"
      }
    >
      <label htmlFor={champ} className="block text-sm font-medium text-ink">
        {t("adresse.question")}
      </label>
      <p className="mt-1 text-sm text-muted">{t("adresse.aide")}</p>

      <div className="mt-3 flex flex-wrap items-stretch gap-2">
        <div className="flex min-w-[14rem] flex-1 items-center rounded-xl border border-line bg-bg px-3 focus-within:border-salon">
          <input
            id={champ}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t("adresse.exemple")}
            autoComplete="organization"
            className="min-w-0 flex-1 bg-transparent py-3 text-ink outline-none placeholder:text-subtle"
          />
          <span className="tabular shrink-0 pl-1 text-sm text-subtle">
            .{PLATFORM_DOMAIN}
          </span>
        </div>

        {state === "free" && (
          <a
            href={`${appUrl}/inscription?slug=${encodeURIComponent(slug)}&nom=${encodeURIComponent(name.trim())}`}
            className="inline-flex items-center justify-center rounded-xl bg-salon px-5 py-3 font-semibold text-white shadow-sm transition hover:brightness-110"
          >
            {t("adresse.reserver")}
          </a>
        )}
      </div>

      <p className="mt-3 min-h-[1.25rem] text-sm" aria-live="polite">
        {state === "checking" && (
          <span className="text-subtle">{t("adresse.verification")}</span>
        )}
        {state === "invalid" && (
          <span className="text-subtle">{t("adresse.tropCourt")}</span>
        )}
        {state === "free" && (
          <span className="font-medium text-success">
            {t("adresse.libre", { adresse: `${slug}.${PLATFORM_DOMAIN}` })}
          </span>
        )}
        {state === "taken" && (
          <span className="text-danger">
            {t("adresse.prise", { adresse: `${slug}.${PLATFORM_DOMAIN}` })}
          </span>
        )}
      </p>
    </div>
  );
}
