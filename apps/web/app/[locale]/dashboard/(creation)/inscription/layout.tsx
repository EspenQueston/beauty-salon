import { CoquilleCompte } from "@/features/account/CoquilleCompte";
import { FilmAcces } from "@/features/account/FilmAcces";

/**
 * L'inscription, seule de son groupe de routes.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi un groupe à elle
 * ---------------------------------------------------------------------------
 *
 * Elle partage tout avec les autres écrans de compte — la même coquille, la
 * même barre, la même sortie — sauf une chose : la colonne de droite. Une
 * personne qui s'inscrit hésite encore et a besoin de voir le produit ; une
 * personne qui réinitialise son mot de passe a déjà décidé, et le même film
 * la retarderait.
 *
 * Une mise en page Next ne sait pas quelle page elle enveloppe. Plutôt que de
 * lui faire deviner l'URL, l'inscription a sa propre mise en page. Le chemin
 * servi ne change pas : les parenthèses d'un groupe de routes ne comptent pas
 * dans l'URL, et c'est toujours `/dashboard/inscription`.
 *
 * ---------------------------------------------------------------------------
 * Le film, et rien d'autre
 * ---------------------------------------------------------------------------
 *
 * La colonne portait d'abord une légende, un titre et trois arguments sous le
 * film. C'était deux discours pour un seul geste : le formulaire à gauche dit
 * déjà ce qu'on obtient — sa dernière étape le récapitule, et trois vignettes
 * de réassurance suivent la carte — pendant que la colonne de droite le
 * répétait en mots. Or le film le montre. Les mots sous lui ne faisaient que
 * demander de lire ce qu'on était en train de regarder.
 *
 * Il reste donc seul. C'est la seule chose de cette page qui ne se lit pas.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi il est à droite
 * ---------------------------------------------------------------------------
 *
 * Le regard part à gauche dans un sens de lecture latin : la colonne de gauche
 * revient donc à ce qu'on est venu faire — remplir. Le film soutient, il ne
 * précède pas. C'est aussi la place qu'occupe déjà la colonne de réassurance
 * de l'écran de connexion : deux écrans voisins n'ont aucune raison d'inverser
 * leur géographie.
 *
 * Sur téléphone, il passe **sous** le formulaire. Au-dessus, il repousserait
 * le premier champ hors de l'écran ; masqué, il reviendrait à dire que
 * l'argument ne vaut que pour qui a un grand écran.
 */
export default function InscriptionLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <CoquilleCompte aside={<FilmAcces />}>{children}</CoquilleCompte>;
}
