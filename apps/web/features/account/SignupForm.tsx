"use client";

/**
 * Inscription d'un salon.
 *
 * L'adresse du mini-site est le seul champ qui engage durablement : elle
 * devient le sous-domaine et figurera sur les cartes de visite. Elle est
 * donc proposée automatiquement depuis le nom, vérifiée pendant la saisie,
 * et modifiable tant que le formulaire n'est pas envoyé.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { DashboardError, checkSlug, signup } from "@/lib/dashboard";
import { Button, Card, Field, inputClass } from "@/features/ui";
import { FormProgress } from "./FormProgress";
import { guessCountry } from "@/lib/locale";
import { useToast } from "@/features/ui/Toast";

const PLATFORM_DOMAIN = process.env.NEXT_PUBLIC_PLATFORM_DOMAIN ?? "localhost";

const COUNTRIES = [
  { code: "CG", label: "Congo-Brazzaville", tz: "Africa/Brazzaville", currency: "XAF" },
  {
    code: "CD",
    label: "République démocratique du Congo",
    tz: "Africa/Kinshasa",
    currency: "CDF",
  },
  { code: "CN", label: "Chine", tz: "Asia/Shanghai", currency: "CNY" },
];

const schema = z.object({
  salon_name: z.string().min(2, "Indiquez le nom de votre salon."),
  slug: z
    .string()
    .min(3, "Au moins 3 caractères.")
    .max(63)
    .regex(
      /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/,
      "Minuscules, chiffres et tirets uniquement.",
    ),
  email: z.string().email("Adresse e-mail invalide."),
  password: z.string().min(10, "Au moins 10 caractères."),
  display_name: z.string().max(120).optional(),
  phone: z.string().max(32).optional(),
  country: z.string(),
  accepts_terms: z.literal(true, { message: "Vous devez accepter les conditions." }),
});

type Values = z.infer<typeof schema>;

/** "Chez Fatou & Filles" -> "chez-fatou-filles" */
function toSlug(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

type SlugState = "idle" | "checking" | "free" | "taken";

/**
 * Nom et adresse apportés par la page d'accueil (`?nom=…&slug=…`).
 *
 * Lus depuis `window` plutôt qu'avec `useSearchParams` : ce dernier impose
 * une frontière Suspense et retire la route du pré-rendu statique, pour deux
 * champs pré-remplis.
 */
function readPrefill(): {
  name: string;
  slug: string;
  theme: Record<string, string> | null;
} {
  if (typeof window === "undefined") return { name: "", slug: "", theme: null };
  const params = new URLSearchParams(window.location.search);

  /*
   * Les couleurs composées sur la page d'accueil sont reprises telles
   * quelles — sinon la promesse « vos choix vous suivent » serait fausse,
   * ce qui vaut moins que de ne rien promettre.
   *
   * Elles viennent de l'URL, donc de l'extérieur : on n'accepte que des
   * codes hexadécimaux, et le serializer les revalide de son côté.
   */
  const hex = (value: string | null) =>
    value && /^#[0-9a-fA-F]{6}$/.test(value) ? value : null;

  const primary = hex(params.get("primaire"));
  const accent = hex(params.get("secondaire"));
  const surface = hex(params.get("fond"));

  return {
    name: params.get("nom") ?? "",
    slug: params.get("slug") ?? "",
    theme:
      primary && accent && surface
        ? { primary, accent, surface }
        : null,
  };
}

export function SignupForm() {
  const toast = useToast();
  const [prefill] = useState(readPrefill);
  const [done, setDone] = useState<{
    hostname: string;
    name: string;
    email: string;
  } | null>(null);
  const [slugTouched, setSlugTouched] = useState(false);
  const [slugState, setSlugState] = useState<SlugState>("idle");

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    /*
     * Valeurs de départ, dont celles apportées depuis la page d'accueil.
     *
     * Quelqu'un qui vient de vérifier que « blondrose » est libre a déjà
     * fait ce choix : le lui redemander revient à effacer son travail, et
     * c'est là qu'on perd les inscriptions.
     */
    defaultValues: {
      // Déduit du fuseau du navigateur plutôt que figé sur le Congo : une
      // coiffeuse à Guangzhou n'a plus trois champs à corriger avant même
      // d'avoir tapé son nom.
      country: guessCountry(),
      slug: prefill.slug,
      salon_name: prefill.name,
      display_name: "",
      phone: "",
    },
  });

  const salonName = watch("salon_name");
  const slug = watch("slug");
  const country = watch("country");

  // Proposition automatique tant que la personne n'a pas repris la main.
  useEffect(() => {
    if (!slugTouched && salonName) {
      setValue("slug", toSlug(salonName), { shouldValidate: false });
    }
  }, [salonName, slugTouched, setValue]);

  useEffect(() => {
    if (!slug || slug.length < 3) {
      setSlugState("idle");
      return;
    }
    let cancelled = false;

    const handle = setTimeout(() => {
      if (!cancelled) setSlugState("checking");
      checkSlug(slug)
        .then((result) => {
          if (!cancelled) setSlugState(result.available ? "free" : "taken");
        })
        .catch(() => {
          if (!cancelled) setSlugState("idle");
        });
    }, 350);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [slug]);

  const place = useMemo(
    () => COUNTRIES.find((entry) => entry.code === country) ?? COUNTRIES[0],
    [country],
  );

  /*
   * Avancement, dérivé des valeurs réelles du formulaire.
   *
   * Les champs pré-remplis comptent : ils contiennent bien une valeur, issue
   * d'un choix fait sur la page d'accueil. Le contraire reviendrait à
   * effacer ce travail à l'écran, ce qui est exactement ce qu'on cherche à
   * éviter ici.
   */
  const email = watch("email");
  const password = watch("password");
  const accepted = watch("accepts_terms");

  const progress = [
    { key: "nom", label: "Nom", done: (salonName ?? "").trim().length >= 2 },
    { key: "adresse", label: "Adresse", done: (slug ?? "").length >= 3 },
    { key: "email", label: "E-mail", done: /.+@.+\..+/.test(email ?? "") },
    { key: "mdp", label: "Mot de passe", done: (password ?? "").length >= 10 },
    { key: "cgu", label: "Conditions", done: Boolean(accepted) },
  ];

  const submit = useCallback(
    async (values: Values) => {
      try {
        const result = await signup({
          ...values,
          display_name: values.display_name || undefined,
          phone: values.phone || undefined,
          timezone_name: place.tz,
          currency: place.currency,
          accepts_terms: true,
          // Reprend les couleurs composées sur la page d'accueil, s'il y en a.
          ...(prefill.theme ? { theme_config: prefill.theme } : {}),
        });
        toast.success(`${result.tenant.name} est créé. Connectez-vous pour entrer.`);
        setDone({
          hostname: result.tenant.hostname,
          name: result.tenant.name,
          email: result.email,
        });
      } catch (error) {
        toast.error(
          error instanceof DashboardError
            ? error.message
            : "L'inscription a échoué. Réessayez.",
        );
      }
    },
    [place, toast],
  );

  if (done) {
    return (
      <Card>
        <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-success-bg text-success">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="size-6">
            <path
              d="M20 6 9 17l-5-5"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>

        <h1 className="mt-4 text-xl font-semibold tracking-tight text-ink">
          {done.name} est créé
        </h1>

        <p className="mt-3 text-sm leading-relaxed text-ink">
          Votre adresse est réservée :{" "}
          <strong className="break-all">{done.hostname}</strong>
        </p>

        <p className="mt-3 text-sm leading-relaxed text-muted">
          Notre équipe vérifie votre salon avant de mettre votre mini-site en
          ligne. En attendant, vous pouvez déjà préparer votre catalogue, vos
          horaires et votre équipe.
        </p>

        {/* Pas de session ouverte automatiquement : on demande le mot de passe
            qui vient d'être choisi. C'est le moment où une faute de frappe se
            découvre — pas à la visite suivante. */}
        <div className="mt-5 rounded-xl border border-line bg-surface-muted p-4">
          <p className="text-sm font-medium text-ink">Dernière étape</p>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            Connectez-vous avec l&apos;adresse{" "}
            <strong className="break-all text-ink">{done.email}</strong> et le
            mot de passe que vous venez de choisir.
          </p>
        </div>

        <Link
          href={`/?email=${encodeURIComponent(done.email)}`}
          className="mt-5 inline-flex items-center justify-center rounded-lg bg-salon px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:brightness-110"
        >
          Me connecter
        </Link>
      </Card>
    );
  }

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Créer mon salon
        </h1>
        {/*
          Ancrage sur des faits vérifiables, pas sur une promesse vague.
          « 30 jours » est la durée réellement appliquée par la facturation
          (TRIAL_DAYS), et rien n'est prélevé à son terme : une facture est
          émise, le mini-site continue de fonctionner. Annoncer une coupure
          serait une menace inventée.
        */}
        <p className="mt-1.5 text-sm text-muted">
          <strong className="font-medium text-ink">30 jours gratuits</strong>,
          sans carte bancaire. Rien ne s&apos;interrompt à la fin de
          l&apos;essai.
        </p>
      </div>

      {/*
        Ce qui a été composé sur la page d'accueil, rendu visible.

        Une adresse vérifiée et des couleurs choisies constituent déjà un
        petit bien. Le montrer ici n'est pas décoratif : c'est la différence
        entre « remplir un formulaire » et « terminer ce que j'ai commencé ».
      */}
      {(prefill.slug || prefill.theme) && (
        <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface-muted p-4">
          {prefill.theme && (
            <span className="flex shrink-0">
              {[prefill.theme.primary, prefill.theme.accent, prefill.theme.surface].map(
                (colour) => (
                  <span
                    key={colour}
                    className="-ml-1.5 size-6 rounded-full ring-2 ring-surface first:ml-0"
                    style={{ background: colour }}
                  />
                ),
              )}
            </span>
          )}

          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-ink">Vos choix sont repris</p>
            <p className="mt-0.5 text-xs text-muted">
              {prefill.slug && (
                <>
                  <span className="break-all">
                    {prefill.slug}.{PLATFORM_DOMAIN}
                  </span>
                  {prefill.theme && " · "}
                </>
              )}
              {prefill.theme && "vos couleurs"}
            </p>
          </div>
        </div>
      )}

      <Card>
        <form onSubmit={(event) => void handleSubmit(submit)(event)} noValidate>
          {/* Le compteur crédite ce qui arrive déjà rempli : personne ne
              démarre à zéro après avoir composé son aperçu. */}
          <FormProgress steps={progress} />

          <Field
            label="Nom du salon"
            error={errors.salon_name?.message}
            className="mb-4"
          >
            <input
              {...register("salon_name")}
              autoComplete="organization"
              placeholder="Chez Fatou"
              className={inputClass}
            />
          </Field>

          <Field
            label="Adresse de votre mini-site"
            error={
              errors.slug?.message ??
              (slugState === "taken" ? "Cette adresse est déjà prise." : undefined)
            }
            hint={slugHint(slugState, slug)}
            className="mb-4"
          >
            <div className="flex items-center gap-1.5">
              <input
                {...register("slug")}
                onInput={() => setSlugTouched(true)}
                spellCheck={false}
                className={`${inputClass} flex-1`}
              />
              <span className="shrink-0 text-sm text-muted">.{PLATFORM_DOMAIN}</span>
            </div>
          </Field>

          {/*
            Conséquence réelle de l'abandon, pas une menace fabriquée : tant
            que le formulaire n'est pas envoyé, rien n'est réservé et
            quelqu'un d'autre peut prendre l'adresse. C'est vrai, vérifiable,
            et c'est précisément ce qu'on ignore en fermant l'onglet.
          */}
          {slugState === "free" && (
            <p className="-mt-2 mb-4 text-xs leading-relaxed text-muted">
              Cette adresse n&apos;est pas encore à vous : elle se réserve à
              la création du salon.
            </p>
          )}

          <Field
            label="Pays"
            hint={`Fuseau ${place.tz}, tarifs en ${place.currency}. Modifiable ensuite.`}
            className="mb-4"
          >
            <select {...register("country")} className={inputClass}>
              {COUNTRIES.map((entry) => (
                <option key={entry.code} value={entry.code}>
                  {entry.label}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Votre nom"
            hint="Celui qui apparaîtra dans votre équipe. Facultatif."
            className="mb-4"
          >
            <input
              {...register("display_name")}
              autoComplete="name"
              placeholder="Grâce Mabiala"
              className={inputClass}
            />
          </Field>

          <Field label="Votre e-mail" error={errors.email?.message} className="mb-4">
            <input
              {...register("email")}
              type="email"
              autoComplete="email"
              className={inputClass}
            />
          </Field>

          <Field
            label="Mot de passe"
            hint="Au moins 10 caractères."
            error={errors.password?.message}
            className="mb-5"
          >
            <input
              {...register("password")}
              type="password"
              autoComplete="new-password"
              className={inputClass}
            />
          </Field>

          <label className="mb-5 flex items-start gap-2.5 text-sm text-ink">
            <input
              type="checkbox"
              {...register("accepts_terms")}
              className="mt-0.5 size-4 accent-[var(--salon-primary)]"
            />
            <span>
              J&apos;accepte les conditions d&apos;utilisation de Beauty Salon.
            </span>
          </label>
          {errors.accepts_terms && (
            <p className="-mt-3 mb-4 text-xs font-medium text-danger">
              {errors.accepts_terms.message}
            </p>
          )}

          <Button
            type="submit"
            pending={isSubmitting}
            disabled={slugState === "taken"}
            className="w-full"
          >
            Créer mon salon
          </Button>
        </form>
      </Card>

      <p className="mt-5 text-center text-sm text-muted">
        Vous avez déjà un compte ?{" "}
        <Link
          href="/"
          className="font-medium text-salon underline-offset-2 hover:underline"
        >
          Se connecter
        </Link>
      </p>
    </>
  );
}

function slugHint(state: SlugState, slug: string): string | undefined {
  if (!slug) return "Elle apparaîtra sur vos cartes et vos partages.";
  if (state === "checking") return "Vérification…";
  if (state === "free") return `${slug}.${PLATFORM_DOMAIN} est disponible.`;
  return undefined;
}
