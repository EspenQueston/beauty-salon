"use client";

/**
 * Inscription d'un salon.
 *
 * ---------------------------------------------------------------------------
 * Une seule liste de champs, deux façons de la parcourir
 * ---------------------------------------------------------------------------
 *
 * Sur grand écran, les sept champs tiennent à l'écran d'un coup et on les
 * remplit dans l'ordre qu'on veut : la page les montre tous.
 *
 * Sur téléphone, cette même liste demandait de faire défiler deux écrans, le
 * compteur d'avancement disparaissait à la première frappe, et le bouton
 * d'envoi n'était jamais visible en même temps que le champ en cours. Les
 * champs y sont donc groupés en trois étapes, une par écran.
 *
 * **Le formulaire reste le même dans les deux cas.** Les groupes non affichés
 * sont masqués en CSS (`hidden sm:block`), pas démontés : leurs valeurs
 * restent, la validation porte sur l'ensemble au moment de l'envoi, et il n'y
 * a qu'un seul état à raisonner. `display: none` retire aussi les champs du
 * parcours du clavier et des lecteurs d'écran — il n'y a donc rien à ajouter
 * pour cela.
 *
 * ---------------------------------------------------------------------------
 * Ce qui encourage, et ce qui serait faux
 * ---------------------------------------------------------------------------
 *
 * Chaque champ rempli affiche ce qu'il **produit** — le nom qui s'affichera,
 * l'adresse qui est libre, la monnaie appliquée — plutôt qu'une félicitation.
 * Une coche confirme une syntaxe ; une conséquence confirme un choix.
 *
 * Rien n'est inventé pour presser : l'adresse n'est réellement pas réservée
 * tant que le formulaire n'est pas envoyé, et c'est dit. « 14 jours » est la
 * durée que la facturation applique (TRIAL_DAYS), et rien n'est prélevé à son
 * terme : le salon choisit une offre et paie lui-même.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { DashboardError, checkSlug, signup } from "@/lib/dashboard";
import { Button, Card, Field, GhostButton, inputClass } from "@/features/ui";
import { Acquis, ForceMotDePasse, Parcours } from "./Parcours";
import { PasswordField } from "@/features/ui/PasswordField";
import { guessCountry } from "@/lib/locale";
import { useToast } from "@/features/ui/Toast";
import { PALETTES, paletteDepuisCouleurs } from "@/features/site/palettes";
import { useTranslations } from "next-intl";

const PLATFORM_DOMAIN = process.env.NEXT_PUBLIC_PLATFORM_DOMAIN ?? "localhost";

const COUNTRIES = [
  {
    code: "CG",
    label: "Congo-Brazzaville",
    tz: "Africa/Brazzaville",
    currency: "XAF",
  },
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
  palette: z.string().refine(
    (value) => PALETTES.some((entry) => entry.cle === value),
    "Choisissez les couleurs de votre salon.",
  ),
  accepts_terms: z.literal(true, {
    message: "Vous devez accepter les conditions.",
  }),
});

type Values = z.infer<typeof schema>;

/**
 * Les trois groupes, dans l'ordre où on les traverse sur téléphone.
 *
 * L'ordre n'est pas neutre : le salon d'abord, parce que c'est ce qu'on est
 * venu créer et que voir son adresse libre donne envie de continuer ; le mot
 * de passe en dernier, parce que c'est le champ le plus pénible à saisir sur
 * un clavier de téléphone et qu'on l'aborde mieux après avoir déjà investi.
 */
const GROUPES = [
  {
    cle: "salon",
    titre: "Votre salon",
    champs: ["salon_name", "slug", "country", "palette"],
    requis: ["salon_name", "slug", "palette"],
  },
  {
    cle: "vous",
    titre: "Vous",
    champs: ["display_name", "email"],
    requis: ["email"],
  },
  {
    cle: "acces",
    titre: "Votre accès",
    champs: ["password", "accepts_terms"],
    requis: ["password", "accepts_terms"],
  },
] as const satisfies readonly {
  cle: string;
  titre: string;
  champs: readonly (keyof Values)[];
  requis: readonly (keyof Values)[];
}[];

/**
 * Comment ces groupes se répartissent en étapes, selon la largeur.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi deux étapes sur grand écran et trois sur téléphone
 * ---------------------------------------------------------------------------
 *
 * Le découpage ne suit pas une mode : il suit ce qui tient à l'écran sans
 * faire défiler. Un écran d'ordinateur affiche confortablement quatre champs
 * et leur bouton ; un téléphone en affiche deux ou trois. Trois étapes sur un
 * grand écran donneraient trois écrans presque vides, et chaque passage à la
 * suivante est une occasion de s'arrêter.
 *
 * Ce sont les mêmes groupes dans les deux cas — seule leur réunion change.
 * Rien n'est dupliqué, et une correction de libellé n'a qu'un endroit où
 * être faite.
 */
interface Etape {
  titre: string;
  /** Index des groupes réunis dans cette étape. */
  groupes: number[];
}

const PLAN_BUREAU: Etape[] = [
  {
    titre: "Votre salon",
    groupes: [0],
  },
  {
    titre: "Votre compte",
    groupes: [1, 2],
  },
];

const PLAN_TELEPHONE: Etape[] = GROUPES.map((groupe, index) => ({
  titre: groupe.titre,
  groupes: [index],
}));

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
    theme: primary && accent && surface && paletteDepuisCouleurs({ primary, accent, surface })
      ? { primary, accent, surface }
      : null,
  };
}

export function SignupForm() {
  const toast = useToast();
  const site = useTranslations("site");
  const [prefill] = useState(readPrefill);
  const [done, setDone] = useState<{
    hostname: string;
    name: string;
    email: string;
  } | null>(null);
  const [slugTouched, setSlugTouched] = useState(false);
  const [slugState, setSlugState] = useState<SlugState>("idle");
  const [etape, setEtape] = useState(0);
  const [plan, setPlan] = useState<Etape[]>(PLAN_BUREAU);
  const formulaire = useRef<HTMLFormElement>(null);

  /*
   * Le découpage se choisit après hydratation, et l'ordre importe.
   *
   * Le rendu du serveur ne connaît pas la largeur de l'écran : il part donc
   * du plan de bureau. Sur téléphone, le premier rendu client est identique
   * — donc aucune alerte d'hydratation — puis l'effet bascule sur trois
   * étapes. Comme les deux plans commencent par le même groupe, rien ne
   * clignote : c'est la suite du parcours qui change, pas ce qu'on voit.
   *
   * L'étape courante est ramenée dans les bornes du nouveau plan : quelqu'un
   * qui fait pivoter son téléphone depuis l'étape 2 d'un plan à deux ne doit
   * pas se retrouver devant un index qui n'existe plus.
   */
  useEffect(() => {
    const requete = window.matchMedia("(max-width: 639.98px)");
    const suivre = () => {
      const prochain = requete.matches ? PLAN_TELEPHONE : PLAN_BUREAU;
      setPlan(prochain);
      setEtape((courante) => Math.min(courante, prochain.length - 1));
    };
    suivre();
    requete.addEventListener("change", suivre);
    return () => requete.removeEventListener("change", suivre);
  }, []);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    trigger,
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
      palette: paletteDepuisCouleurs(prefill.theme),
    },
  });

  const salonName = watch("salon_name");
  const slug = watch("slug");
  const country = watch("country");
  const palette = watch("palette");
  const email = watch("email");
  const password = watch("password") ?? "";
  const accepted = watch("accepts_terms");

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
  const couleursChoisies = PALETTES.find((entry) => entry.cle === palette);

  /*
   * Avancement, dérivé des valeurs réelles du formulaire.
   *
   * Les champs pré-remplis comptent : ils contiennent bien une valeur, issue
   * d'un choix fait sur la page d'accueil.
   */
  const rempli: Record<string, boolean> = {
    salon_name: (salonName ?? "").trim().length >= 2,
    slug: (slug ?? "").length >= 3 && slugState !== "taken",
    palette: PALETTES.some((entry) => entry.cle === palette),
    email: /.+@.+\..+/.test(email ?? ""),
    password: password.length >= 10,
    accepts_terms: Boolean(accepted),
  };

  /* Un segment par étape du plan courant, rempli à la proportion des champs
     obligatoires que ses groupes ont reçus. */
  const avancement = plan.map((pas, index) => {
    const requis = pas.groupes.flatMap((i) => GROUPES[i].requis);
    return {
      cle: `pas-${index}`,
      titre: pas.titre,
      requis: requis.length,
      faits: requis.filter((champ) => rempli[champ]).length,
    };
  });

  const dernier = plan.length - 1;

  /** Passe à l'étape suivante, si celle-ci est valide. */
  const suivant = useCallback(async () => {
    const pas = plan[etape];
    const champs = pas.groupes.flatMap((i) => [...GROUPES[i].champs]);
    const valide = await trigger(champs);
    if (!valide) return;
    if (champs.includes("slug") && slugState === "taken") return;

    setEtape(Math.min(etape + 1, dernier));
  }, [etape, dernier, trigger, slugState, plan]);

  const precedent = useCallback(() => {
    setEtape((courante) => Math.max(0, courante - 1));
  }, []);

  /*
   * Le focus et le défilement, après chaque changement d'étape.
   *
   * Dans un effet et non dans le gestionnaire de clic : après `setEtape`,
   * une image d'animation ne garantit pas que React ait posé le DOM. Le
   * groupe visé est alors encore masqué, et `focus()` sur un élément en
   * `display: none` ne fait rien — silencieusement, ce qui est le pire cas.
   * Un effet s'exécute après la pose.
   *
   * Sans ce déplacement, le focus resterait sur le bouton « Continuer » qui
   * vient de disparaître : au clavier on repart du début du document, et au
   * lecteur d'écran on n'entend rien de la nouvelle étape.
   *
   * Le déclencheur est le **changement** d'étape, et non « ce n'est pas le
   * premier rendu ».
   *
   * Un drapeau « premier rendu » ne survit pas au double montage que React
   * pratique en développement : au second passage il vaut déjà faux, l'effet
   * s'exécute, et la page arrive défilée avec son titre hors cadre — ce qui
   * s'est produit. Comparer l'étape précédente à l'étape courante ne se
   * laisse pas prendre : elles sont égales tant que personne n'a rien fait.
   */
  const etapePrecedente = useRef(etape);
  useEffect(() => {
    // Rien à l'arrivée sur la page : ouvrir le clavier d'un téléphone avant
    // que quiconque ait touché l'écran est une intrusion.
    if (etapePrecedente.current === etape) return;
    etapePrecedente.current = etape;
    /*
     * On remonte en **haut de page**, pas en haut du groupe.
     *
     * `scrollIntoView` sur le groupe posait son premier champ contre le bord
     * supérieur de la fenêtre — et poussait donc hors cadre tout ce qui est
     * au-dessus de lui : le titre, le numéro d'étape, les segments. On
     * arrivait à l'étape 2 par son milieu, sans savoir où l'on en était.
     *
     * Le cas s'aggrave à fort zoom, où la carte dépasse la hauteur visible :
     * c'est précisément là qu'on a le plus besoin de voir l'en-tête.
     */
    window.scrollTo({ top: 0 });

    /* `preventScroll` : sans lui, le focus ramènerait le champ à l'écran et
       défilerait par-dessus ce qu'on vient de remonter. */
    formulaire.current
      ?.querySelector<HTMLFieldSetElement>(
        `[data-groupe="${plan[etape]?.groupes[0] ?? 0}"]`,
      )
      ?.querySelector<HTMLElement>("input:not([type=hidden]), select, textarea")
      ?.focus({ preventScroll: true });
  }, [etape, plan]);

  const submit = useCallback(
    async (values: Values) => {
      try {
        const { palette: paletteKey, ...fields } = values;
        const couleurs = PALETTES.find((entry) => entry.cle === paletteKey);
        if (!couleurs) return;
        const result = await signup({
          ...fields,
          display_name: values.display_name || undefined,
          phone: values.phone || undefined,
          timezone_name: place.tz,
          currency: place.currency,
          accepts_terms: true,
          theme_config: {
            primary: couleurs.primary,
            accent: couleurs.accent,
            surface: couleurs.surface,
          },
        });
        toast.success(
          `${result.tenant.name} est créé. Connectez-vous pour entrer.`,
        );
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

  /*
   * L'envoi n'a lieu qu'à la dernière étape.
   *
   * Sur un téléphone, la touche « entrée » du clavier envoie le formulaire
   * depuis n'importe quel champ. Sans ce garde-fou, une personne au premier
   * groupe déclencherait l'inscription avec un mot de passe vide et
   * récolterait cinq erreurs d'un coup — dont trois sur des champs qu'elle
   * n'a pas encore vus.
   */
  const surEnvoi = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      if (etape < dernier) {
        event.preventDefault();
        void suivant();
        return;
      }
      void handleSubmit(submit)(event);
    },
    [etape, dernier, suivant, handleSubmit, submit],
  );

  if (done) {
    return <Bienvenue {...done} />;
  }

  return (
    <>
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
              {[
                prefill.theme.primary,
                prefill.theme.accent,
                prefill.theme.surface,
              ].map((colour) => (
                <span
                  key={colour}
                  className="-ml-1.5 size-6 rounded-full ring-2 ring-surface first:ml-0"
                  style={{ background: colour }}
                />
              ))}
            </span>
          )}

          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-ink">
              Vos choix sont repris
            </p>
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
        {/*
          Le titre est dans la carte, pas au-dessus.

          Dehors, il flottait sur le fond de la page sans lui appartenir — et
          ce fond porte maintenant un dégradé : le contraste de la mention
          « 14 jours gratuits » y dépendait de la densité du rose, mesurée à
          4,37:1, sous le seuil. Dedans, le titre, l'avancement, les champs et
          le bouton forment un seul objet posé sur une surface opaque, dont le
          contraste ne dépend d'aucun décor.

          C'est aussi ce que fait l'écran de connexion, pour la même raison.
        */}
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Créer mon salon
        </h1>
        {/*
          Ancrage sur des faits vérifiables, pas sur une promesse vague.
          « 14 jours » est la durée réellement appliquée par la facturation
          (TRIAL_DAYS), et rien n'est prélevé à son terme : aucun moyen de
          paiement n'est enregistré, le salon choisit ensuite son offre.
        */}
        <p className="mb-6 mt-1.5 text-sm text-muted">
          <strong className="font-medium text-ink">14 jours gratuits</strong>,
          sans carte bancaire.
        </p>

        <form ref={formulaire} onSubmit={surEnvoi} noValidate>
          <Parcours etapes={avancement} etape={etape} />

          {/* ------------------------------------------------- 1. Le salon */}
          <Cadre index={0} plan={plan} etape={etape}>
            <Field
              label="Nom du salon"
              error={errors.salon_name?.message}
              className="mb-1"
            >
              <input
                {...register("salon_name")}
                autoComplete="organization"
                autoCapitalize="words"
                enterKeyHint="next"
                placeholder="Chez Fatou"
                className={inputClass}
              />
            </Field>
            <Acquis actif={rempli.salon_name}>
              Votre page s&apos;affichera au nom de{" "}
              <strong className="font-medium">{salonName}</strong>.
            </Acquis>

            <Field
              label="Adresse de votre mini-site"
              error={
                errors.slug?.message ??
                (slugState === "taken"
                  ? "Cette adresse est déjà prise."
                  : undefined)
              }
              hint={slugState === "checking" ? "Vérification…" : undefined}
              className="mb-1 mt-4"
            >
              <div className="flex items-center gap-1.5">
                <input
                  {...register("slug")}
                  onInput={() => setSlugTouched(true)}
                  spellCheck={false}
                  autoCapitalize="none"
                  autoCorrect="off"
                  inputMode="url"
                  enterKeyHint="next"
                  className={`${inputClass} flex-1`}
                />
                <span className="shrink-0 text-sm text-muted">
                  .{PLATFORM_DOMAIN}
                </span>
              </div>
            </Field>
            <Acquis actif={slugState === "free"}>
              <strong className="break-all font-medium">
                {slug}.{PLATFORM_DOMAIN}
              </strong>{" "}
              est libre.
              {/*
                Conséquence réelle de l'abandon, pas une menace fabriquée :
                tant que le formulaire n'est pas envoyé, rien n'est réservé et
                quelqu'un d'autre peut prendre l'adresse. C'est vrai,
                vérifiable, et c'est précisément ce qu'on ignore en fermant
                l'onglet.
              */}
              <span className="text-muted">
                {" "}
                Elle sera à vous à la création du salon.
              </span>
            </Acquis>

            <Field label="Pays" className="mb-1 mt-4">
              <select {...register("country")} className={inputClass}>
                {COUNTRIES.map((entry) => (
                  <option key={entry.code} value={entry.code}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </Field>
            <Acquis actif ton="neutre">
              Tarifs en {place.currency} · fuseau {place.tz}
            </Acquis>

            <fieldset className="mt-5" aria-describedby={errors.palette ? "palette-erreur" : undefined}>
              <legend className="mb-2 text-sm font-medium text-ink">
                Vos couleurs <span className="text-danger" aria-hidden="true">*</span>
                <span className="sr-only">(obligatoire)</span>
              </legend>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {PALETTES.map((entry) => {
                  const active = palette === entry.cle;
                  return (
                    <label key={entry.cle} className="relative min-w-0 cursor-pointer">
                      <input
                        {...register("palette")}
                        type="radio"
                        value={entry.cle}
                        className="peer sr-only"
                      />
                      <span className={`flex min-h-11 min-w-0 items-center gap-2 rounded-xl border px-2.5 py-2 text-xs font-medium transition duration-200 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-salon active:scale-[0.97] sm:text-sm ${
                        active
                          ? "border-salon bg-salon-soft text-ink shadow-sm"
                          : "border-line bg-surface text-muted hover:border-salon hover:bg-surface-hover"
                      }`}>
                        <span className="flex shrink-0" aria-hidden="true">
                          <span className="size-4 rounded-full ring-1 ring-black/10" style={{ background: entry.primary }} />
                          <span className="-ml-1.5 size-4 rounded-full ring-1 ring-black/10" style={{ background: entry.accent }} />
                        </span>
                        <span className="min-w-0 leading-tight">{site(`palettes.${entry.cle}`)}</span>
                        {active && <span className="ml-auto shrink-0 text-salon-ink" aria-hidden="true">✓</span>}
                      </span>
                    </label>
                  );
                })}
              </div>
              {errors.palette && (
                <p id="palette-erreur" role="alert" className="mt-2 text-xs font-medium text-danger">
                  {errors.palette.message}
                </p>
              )}
              {couleursChoisies && (
                <div
                  className="mt-3 flex items-center gap-2.5 rounded-xl border px-3 py-2.5 shadow-sm transition-colors duration-300"
                  style={{ background: couleursChoisies.surface, borderColor: couleursChoisies.accent }}
                >
                  <span
                    className="grid size-8 shrink-0 place-items-center rounded-lg text-xs font-bold text-white"
                    style={{ background: couleursChoisies.primary }}
                    aria-hidden="true"
                  >
                    BS
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold" style={{ color: couleursChoisies.primary }}>
                      {salonName?.trim() || "Votre salon"}
                    </span>
                    <span className="block text-[0.68rem] text-muted">Aperçu de votre mini-site</span>
                  </span>
                  <span className="size-2 shrink-0 rounded-full" style={{ background: couleursChoisies.accent }} aria-hidden="true" />
                </div>
              )}
            </fieldset>
          </Cadre>

          {/* ---------------------------------------------------- 2. Vous */}
          <Cadre index={1} plan={plan} etape={etape}>
            {/*
              Deux colonnes dès 640 px, une seule en dessous.

              Ce sont les deux champs les plus courts du formulaire, et
              l'étape qui les contient mesurait 884 px — plus de cinq cents à
              faire défiler sur un écran d'ordinateur portable. Côte à côte
              ils en rendent quatre-vingts.

              Pas sur téléphone : à 375 px, deux colonnes donnent deux cases
              de six caractères, où une adresse e-mail ne se relit plus.
            */}
            <div className="grid gap-4 sm:grid-cols-2 sm:gap-x-3">
              <div>
                <Field label="Votre e-mail" error={errors.email?.message}>
                  <input
                    {...register("email")}
                    type="email"
                    autoComplete="email"
                    autoCapitalize="none"
                    autoCorrect="off"
                    inputMode="email"
                    enterKeyHint="next"
                    className={inputClass}
                  />
                </Field>
                <Acquis actif={rempli.email}>Ce sera votre identifiant.</Acquis>
              </div>

              <Field label="Votre nom" hint="Facultatif">
                <input
                  {...register("display_name")}
                  autoComplete="name"
                  autoCapitalize="words"
                  enterKeyHint="next"
                  placeholder="Grâce Mabiala"
                  className={inputClass}
                />
              </Field>
            </div>
          </Cadre>

          {/* -------------------------------------------- 3. Votre accès */}
          <Cadre index={2} plan={plan} etape={etape}>
            {/* `PasswordField` porte l'œil qui permet de relire ce qu'on
                tape : sur un clavier de téléphone, un mot de passe saisi à
                l'aveugle se recommence entier au lieu de se corriger. */}
            <PasswordField
              label="Mot de passe"
              value={password}
              onChange={(valeur) =>
                setValue("password", valeur, {
                  shouldValidate: Boolean(errors.password),
                })
              }
              autoComplete="new-password"
              inputClassName={inputClass}
            />
            {errors.password && (
              <p className="mt-1.5 text-xs font-medium text-danger">
                {errors.password.message}
              </p>
            )}
            <ForceMotDePasse valeur={password} />

            <label className="mt-5 flex items-start gap-2.5 text-sm text-ink">
              <input
                type="checkbox"
                {...register("accepts_terms")}
                className="mt-0.5 size-4 accent-[var(--salon-primary)]"
              />
              <span>
                J&apos;accepte les conditions d&apos;utilisation de Beauty
                Salon.
              </span>
            </label>
            {errors.accepts_terms && (
              <p className="mt-1.5 text-xs font-medium text-danger">
                {errors.accepts_terms.message}
              </p>
            )}

            {/* Le récapitulatif juste avant le bouton : on signe ce qu'on a
                sous les yeux, pas ce dont on se souvient. */}
            {rempli.salon_name && rempli.slug && (
              <p className="mt-4 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-xl border border-line bg-surface-muted px-3.5 py-2.5 text-xs text-muted">
                <span className="font-medium uppercase tracking-[0.1em]">
                  Vous créez
                </span>
                <span className="font-medium text-ink">{salonName}</span>
                <span className="tabular break-all">
                  {slug}.{PLATFORM_DOMAIN} · {place.currency}
                </span>
              </p>
            )}
          </Cadre>

          {/* ------------------------------------------------ la navigation */}
          <div className="mt-6 grid gap-2.5">
            {/* Envoi : à la dernière étape seulement, quel que soit le plan. */}
            <div className={etape === dernier ? "" : "hidden"}>
              <Button
                type="submit"
                pending={isSubmitting}
                disabled={slugState === "taken"}
                className="w-full py-3"
              >
                Créer mon salon
              </Button>
            </div>

            <div className={etape < dernier ? "" : "hidden"}>
              <Button
                type="button"
                onClick={() => void suivant()}
                disabled={slugState === "taken"}
                className="w-full py-3"
              >
                Continuer
              </Button>
            </div>

            {etape > 0 && (
              <GhostButton
                type="button"
                onClick={precedent}
                className="w-full justify-center py-3"
              >
                Retour
              </GhostButton>
            )}
          </div>
        </form>
      </Card>

      {/*
        Les trois objections, au moment où elles se posent.

        Sur grand écran seulement : le téléphone traverse le formulaire en
        trois écrans courts, et chaque étape y porte déjà sa phrase. Y ajouter
        ce bloc rallongerait le seul endroit qu'on a passé du temps à
        raccourcir.

        Chaque ligne est vérifiable. « Rien n'est prélevé » décrit ce que fait
        la facturation à la fin de l'essai : une facture est émise, le
        mini-site continue de fonctionner.
      */}
      {/* Une colonne, sans cadres.

          Mises sur trois colonnes pour gagner en hauteur, ces trois lignes
          tombaient à quatre mots par ligne dans une carte de 448 px : le bloc
          gagnait vingt pixels et perdait sa lisibilité. Sans cadre ni fond,
          une colonne unique fait la même économie sans rien casser. */}
      <ul className="mt-5 hidden gap-2 sm:grid">
        {[
          // « 14 jours gratuits, sans carte bancaire » est déjà écrit en haut
          // de la carte, et « trois minutes suffisent » accompagne désormais
          // l'avancement. Restent les deux choses que rien d'autre ne dit.
          ["Rien n'est prélevé", "à la fin de l'essai."],
          ["Vos données restent les vôtres", "exportables à tout moment."],
        ].map(([titre, corps]) => (
          <li key={titre} className="flex gap-2">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
              className="mt-0.5 size-3.5 shrink-0 text-success"
            >
              <path d="M20 6 9 17l-5-5" />
            </svg>
            <span className="min-w-0 text-xs leading-relaxed">
              <span className="font-medium text-ink">{titre}</span>{" "}
              <span className="text-muted">{corps}</span>
            </span>
          </li>
        ))}
      </ul>

      <p className="mt-5 text-center text-sm text-muted">
        Vous avez déjà un compte ?{" "}
        <Link
          href="/"
          className="font-medium text-salon-ink underline-offset-2 hover:underline"
        >
          Se connecter
        </Link>
      </p>
    </>
  );
}

/**
 * Un groupe de champs.
 *
 * `<fieldset>` et non `<div>` : son `<legend>` donne au groupe un nom que les
 * lecteurs d'écran annoncent en entrant dedans, ce qui est exactement
 * l'information dont on manque quand un écran ne montre qu'une étape.
 */
function Cadre({
  index,
  plan,
  etape,
  children,
}: {
  index: number;
  plan: Etape[];
  etape: number;
  children: React.ReactNode;
}) {
  const reunis = plan[etape].groupes;
  const affiche = reunis.includes(index);
  /* Quand une étape réunit plusieurs groupes, chacun reprend son nom : sans
     lui, l'étape redevient une liste de champs. Quand elle n'en contient
     qu'un, le nom est déjà dans l'en-tête du parcours et le répéter ne dit
     rien de plus. */
  const nomme = reunis.length > 1;

  return (
    <fieldset
      data-groupe={index}
      // `hidden` suffit : `display: none` retire aussi le groupe du parcours
      // du clavier et des lecteurs d'écran.
      className={`groupe ${affiche ? "" : "hidden"}`}
    >
      <legend className="sr-only">{GROUPES[index].titre}</legend>
      {nomme && (
        <p
          className={`mb-3 text-xs font-semibold uppercase tracking-[0.1em] text-muted ${
            index > reunis[0] ? "mt-5 border-t border-line pt-5" : ""
          }`}
          aria-hidden
        >
          {GROUPES[index].titre}
        </p>
      )}
      {children}
    </fieldset>
  );
}

/**
 * L'écran d'arrivée.
 *
 * Aucune session n'est ouverte automatiquement : on demande le mot de passe
 * qui vient d'être choisi. C'est le moment où une faute de frappe se
 * découvre — pas à la visite suivante.
 */
function Bienvenue({
  hostname,
  name,
  email,
}: {
  hostname: string;
  name: string;
  email: string;
}) {
  return (
    <Card>
      <span className="inline-flex size-12 items-center justify-center rounded-2xl bg-success-bg text-success">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          className="size-7"
        >
          <path
            d="M20 6 9 17l-5-5"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>

      <h1 className="mt-4 text-xl font-semibold tracking-tight text-ink">
        {name} est créé
      </h1>

      <p className="mt-3 text-sm leading-relaxed text-ink">
        Votre adresse est réservée :{" "}
        <strong className="break-all">{hostname}</strong>
      </p>

      <p className="mt-3 text-sm leading-relaxed text-muted">
        Notre équipe vérifie votre salon avant de mettre votre mini-site en
        ligne. En attendant, vous pouvez déjà préparer votre catalogue, vos
        horaires et votre équipe.
      </p>

      <div className="mt-5 rounded-xl border border-line bg-surface-muted p-4">
        <p className="text-sm font-medium text-ink">Dernière étape</p>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          Connectez-vous avec l&apos;adresse{" "}
          <strong className="break-all text-ink">{email}</strong> et le mot de
          passe que vous venez de choisir.
        </p>
      </div>

      <Link
        href={`/?email=${encodeURIComponent(email)}`}
        className="mt-5 inline-flex w-full items-center justify-center rounded-lg bg-salon px-4 py-3 text-sm font-medium text-white shadow-sm transition hover:brightness-110 sm:w-auto sm:py-2.5"
      >
        Me connecter
      </Link>
    </Card>
  );
}
