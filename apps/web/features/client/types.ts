/**
 * Une ligne de l'espace cliente.
 *
 * Le type vit à part depuis que plusieurs composants le lisent — le suivi,
 * les cartes, la page elle-même. Le laisser dans `ClientSpace.tsx` obligeait
 * à importer l'écran entier pour connaître la forme d'un rendez-vous.
 */
export interface ClientBooking {
  id: string;
  salon_name: string;
  salon_slug: string;
  currency: string;
  starts_at: string;
  ends_at: string;
  status: string;
  service_name: string;
  staff_member_name: string;
  total_amount: string;
  deposit_amount: string;
  options_snapshot: { name: string; price: string; minutes: number }[];
  travel_zone_name: string;
  address: string;
  /**
   * Pourquoi ce rendez-vous n'aura pas lieu. Vide s'il n'est pas annulé.
   *
   * « Annulé » tout court fait chercher : on se demande si on a annulé
   * soi-même, si le salon a fermé, ou si l'acompte est arrivé trop tard.
   */
  cancellation_reason: string;
  /** QR d'arrivée. Non vide seulement une fois le salon d'accord. */
  checkin_token: string;
  checkin_code: string;
  /** Une visite close se retire de l'historique ; un rendez-vous à venir, non. */
  can_forget: boolean;
  /** Non vide quand l'acompte reste à régler. */
  payment_token: string;
  /** Ouvre la page de suivi détaillée. Toujours présent. */
  status_token: string;

  /* ----- l'avis ---------------------------------------------------------
   *
   * Les trois champs viennent du serveur, qui est seul juge : une visite
   * honorée, vieille de moins de trente jours, et pas encore notée. Refaire
   * ce calcul dans le navigateur produirait tôt ou tard deux verdicts
   * différents — un bouton proposé sur une visite déjà notée, ou refusé sur
   * une visite qui l'accepte encore.
   */
  reviewed: boolean;
  can_review: boolean;
  review_token: string;
  /** Date limite pour noter, en ISO. Vide quand il n'y a rien à noter. */
  review_until: string;

  /* ----- l'annulation ---------------------------------------------------
   *
   * Même raisonnement que pour l'avis : le serveur seul décide, et la route
   * d'annulation revalide la règle au moment de l'exécuter. Recalculer
   * « plus de 24 h avant » dans le navigateur donnerait un bouton proposé
   * sur un rendez-vous que le serveur refusera.
   */
  can_cancel: boolean;
  /** Droit d'annuler ce rendez-vous. Émis seulement si la fenêtre est ouverte. */
  cancel_token: string;
  /** Instant après lequel il faut téléphoner au salon. Vide si sans objet. */
  cancel_until: string;
  cancel_deadline_hours: number;
}
