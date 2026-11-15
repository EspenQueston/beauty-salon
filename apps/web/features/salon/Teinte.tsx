/**
 * La teinte de marque, posée sur les photos de prestations et de
 * réalisations.
 *
 * Par défaut, sur toutes : les photos d'un salon viennent de téléphones, de
 * lumières et de jours différents, et côte à côte elles se contredisent. Un
 * voile de la couleur du thème, en mode « multiplier », les accorde entre
 * elles et au reste du mini-site — la page se lit comme une identité, pas
 * comme un album. C'était déjà le traitement des illustrations d'ambiance ;
 * les photos du salon avaient l'air de venir d'ailleurs.
 *
 * Au survol, le voile s'allège : on regarde une réalisation, on veut en voir
 * les vraies couleurs. L'agrandissement (la visionneuse de la galerie) montre
 * la photo telle quelle.
 *
 * Le parent doit être positionné (`relative`) ; le survol suit le `group`
 * le plus proche.
 */
export function TeinteDeMarque({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`pointer-events-none absolute inset-0 bg-[var(--salon-primary)] opacity-30 mix-blend-multiply transition-opacity duration-500 group-hover:opacity-10 ${className}`}
    />
  );
}
