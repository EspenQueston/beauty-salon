/** Décide quel écran ouvrir sans confondre session et accès à un salon. */
export function modeSession(
  user: { memberships: readonly unknown[] } | null,
): "connexion" | "changer_compte" | "salon" {
  if (!user) return "connexion";
  return user.memberships.length ? "salon" : "changer_compte";
}

/** Une adresse sans accès salon ne doit pas réapparaître dans le formulaire. */
export function adresseDeConnexion(
  adresseUrl: string,
  adresseMemorisee: string,
  compteActuel?: string,
): string {
  if (adresseUrl && adresseUrl !== compteActuel) return adresseUrl;
  if (adresseMemorisee && adresseMemorisee !== compteActuel)
    return adresseMemorisee;
  return "";
}
