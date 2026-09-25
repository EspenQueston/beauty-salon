"use client";

import { useState } from "react";
import Link from "next/link";

import { DashboardError, login } from "@/lib/dashboard";
import { platformUrl } from "@/lib/site";
import { Button } from "@/features/ui";
import { ThemeToggle } from "@/features/ui/ThemeToggle";
import { BeautySalonBrand } from "@/features/ui/BeautySalonBrand";
import {
  AuthShell,
  authCard,
  authInput,
  authLead,
  authLink,
  authTitle,
} from "@/features/ui/AuthShell";
import { FilmAcces } from "@/features/account/FilmAcces";
import { PasswordField } from "@/features/ui/PasswordField";
import { useToast } from "@/features/ui/Toast";

/**
 * Adresse transmise par l'écran d'inscription (`/?email=…`).
 *
 * Lue depuis `window` plutôt qu'avec `useSearchParams` : ce dernier impose
 * une frontière Suspense et retire la route du pré-rendu statique, pour un
 * champ pré-rempli. Le formulaire n'existe que côté client — il n'est rendu
 * qu'après la vérification de session — donc `window` est toujours là.
 */
function emailFromUrl(): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get("email") ?? "";
}

const LAST_EMAIL = "beauty-salon.dernier-email";

/**
 * Adresse de la derniere connexion reussie.
 *
 * Une gerante se connecte depuis le meme poste tous les matins : lui
 * redemander son adresse chaque fois est un peage quotidien sur une
 * information qu'on connait deja.
 *
 * Seule l'adresse est memorisee, jamais le mot de passe — c'est au
 * gestionnaire du navigateur de s'en charger, pas a nous. Et elle n'est
 * ecrite qu'apres une connexion **reussie** : une faute de frappe ne doit
 * pas s'installer pour les visites suivantes.
 */
function rememberedEmail(): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem(LAST_EMAIL) ?? "";
  } catch {
    return "";
  }
}

function remember(email: string) {
  try {
    localStorage.setItem(LAST_EMAIL, email);
  } catch {
    /* stockage refuse : on se passe du confort, rien n'est casse */
  }
}

export function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const toast = useToast();
  const [prefilled] = useState(emailFromUrl);
  // L'adresse de l'URL prime : elle vient de l'inscription qu'on vient de
  // terminer, donc d'une intention plus recente que le souvenir.
  const [email, setEmail] = useState(() => prefilled || rememberedEmail());
  const [password, setPassword] = useState("");
  /*
   * Le curseur va la ou il reste quelque chose a saisir.
   *
   * On regarde l'etat *initial* du champ, pas sa valeur courante : sinon le
   * focus sauterait pendant la frappe, des le premier caractere tape dans
   * une adresse vide.
   */
  const [emailWasFilled] = useState(() =>
    Boolean(prefilled || rememberedEmail()),
  );
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const user = await login(email, password);
      remember(email);
      toast.success(`Bienvenue, ${user.display_name || user.email}.`);
      onSuccess();
    } catch (caught) {
      // L'erreur reste sous le formulaire : c'est là que le regard revient
      // après un échec, pas dans un coin de l'écran.
      setError(
        caught instanceof DashboardError
          ? caught.message
          : "Connexion impossible. Réessayez.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthShell
      homeHref={platformUrl}
      action={<ThemeToggle />}
      brand={<BeautySalonBrand />}
      /*
        La colonne de droite : le film, et rien d'autre.

        Elle portait une légende, un titre et trois arguments — ce qu'il y a
        derrière, ce que ça coûte, à qui appartiennent les données. C'était
        juste, et c'était deux discours pour un seul geste : le film montre
        déjà l'agenda qui se remplit et le mini-site qui se partage, pendant
        que les lignes sous lui demandaient de lire ce qu'on regardait.

        Il reste seul, comme sur l'écran d'inscription. C'est la seule chose
        de ces deux pages qui ne se lit pas.

        Le film remplace aussi l'aperçu d'agenda animé qui occupait cette
        place : celui-ci montrait une chose, le film en montre trois, et en
        mouvement réel plutôt qu'en maquette.
      */
      aside={<FilmAcces />}
    >
      <div className="rise w-full">
        {/*
          Le titre est passé *dans* la carte.

          Dehors, il flottait au-dessus d'un bloc blanc sans lui appartenir,
          et l'écran cliente écrivait le sien dedans : deux hiérarchies pour
          un même geste. Dedans, le titre, la phrase, les champs et le bouton
          forment un seul objet — c'est ce qu'on regarde, et il n'y a rien
          d'autre à regarder.
        */}
        <form onSubmit={submit} className={authCard}>
          <h1 className={authTitle}>Connexion à votre espace professionnel</h1>
          <p className={authLead}>
            {prefilled
              ? "Votre salon est créé. Connectez-vous pour y entrer."
              : "Gérez vos rendez-vous, votre équipe et vos clients."}
          </p>

          <div className="mt-6 space-y-4">
            {/* Une colonne, toujours. Deux champs d'identification côte à
                côte sur un téléphone donnent deux cases de six caractères,
                et l'un des deux est une adresse e-mail. */}
            <div>
              <label
                htmlFor="login-email"
                className="mb-1.5 block text-sm font-medium text-ink"
              >
                E-mail
              </label>
              <input
                id="login-email"
                type="email"
                inputMode="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="username"
                // Le curseur va là où il reste quelque chose à saisir.
                autoFocus={!emailWasFilled}
                required
                className={authInput}
              />
            </div>

            <PasswordField
              label="Mot de passe"
              value={password}
              onChange={setPassword}
              autoComplete="current-password"
              autoFocus={emailWasFilled}
              inputClassName={authInput}
              action={
                <Link
                  href="/mot-de-passe-oublie"
                  className={`${authLink} text-sm`}
                >
                  Mot de passe oublié ?
                </Link>
              }
            />
          </div>

          {/*
            L'erreur reste sous les champs et au-dessus du bouton, et la
            saisie n'est jamais effacée : réécrire son adresse parce qu'on
            s'est trompé de mot de passe est une punition, pas une sécurité.
          */}
          {error && (
            <p
              role="alert"
              className="mt-4 rounded-xl bg-danger-bg p-3 text-sm font-medium text-danger"
            >
              {error}
            </p>
          )}

          <Button type="submit" pending={pending} className="mt-5 w-full py-3">
            Se connecter
          </Button>
        </form>

        {/* Le lien vers l'inscription porte le fait qui compte au moment de
            decider : la duree reelle de l'essai, et l'absence de carte
            bancaire. Sans cela, « Creer le mien » demande un engagement dont
            on ignore le prix. */}
        <p className="mt-5 text-center text-sm text-ink/75">
          Pas encore de salon ?{" "}
          <Link href="/inscription" className={authLink}>
            Créer le mien
          </Link>
          <span className="mt-1 block text-xs text-muted">
            30 jours gratuits, sans carte bancaire.
          </span>
        </p>
      </div>
    </AuthShell>
  );
}
