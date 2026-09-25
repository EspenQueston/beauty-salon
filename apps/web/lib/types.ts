export type PriceKind = "fixed" | "from" | "quote";
export type LocationMode = "salon" | "home" | "hybrid";

export interface MediaAsset {
  id: string;
  url: string;
  /** Copies WebP réduites, par largeur en pixels (« 480 », « 1024 »). */
  variants?: Record<string, string>;
  /** "image/webp", "video/mp4"… Décide du rendu : <img> ou <video>. */
  content_type: string;
  alt_text: string;
  width: number | null;
  height: number | null;
  kind: string;
  position: number;
  /** Mis en avant sur l'accueil du mini-site. */
  featured: boolean;
}

/** Moyenne et volume des avis publiés. `average` est nul sans aucun avis. */
export interface RatingSummary {
  average: number | null;
  count: number;
}

export interface ReviewCriterionScore {
  field: string;
  label: string;
  rating: number;
}

export interface PublicReview {
  id: string;
  author_name: string;
  rating: number;
  /** Les critères notés, dans l'ordre demandé. Les lignes laissées vides par
   *  la cliente n'y figurent pas. */
  detail: ReviewCriterionScore[];
  comment: string;
  service_name: string;
  created_at: string;
}

export function isVideo(asset: MediaAsset): boolean {
  return asset.content_type?.startsWith("video/") ?? false;
}

export interface ServiceOption {
  id: string;
  name: string;
  description: string;
  /** Supplément. « 0 » signifie sans supplément, pas « inconnu ». */
  price_delta: string;
  /** Temps ajouté. Il entre dans la recherche de créneau, pas seulement dans l'affichage. */
  duration_delta_minutes: number;
}

export interface StoreProduct {
  id: string;
  name: string;
  description: string;
  price: string;
  unit: string;
  /** Faux = en rupture. L'article reste montré, barré : le cacher laisserait
      croire que le salon n'en vend pas. */
  available: boolean;
  image: string;
  /** Type MIME : une vidéo ne se rend pas dans une balise <img>. */
  image_type: string;
}

/** Ce qu'il faut prévoir pour une prestation — et ce que le salon peut fournir. */
export interface ServiceRequirement {
  id: string;
  label: string;
  detail: string;
  mandatory: boolean;
  products: StoreProduct[];
}

export interface PublicService {
  id: string;
  name: string;
  description: string;
  duration_minutes: number;
  price_kind: PriceKind;
  price_amount: string;
  requires_deposit: boolean;
  location_mode: LocationMode;
  image: MediaAsset | null;
  staff_member_ids: string[];
  options: ServiceOption[];
  requirements: ServiceRequirement[];
}

export interface PublicCategory {
  id: string;
  name: string;
  position: number;
  services: PublicService[];
}

export interface PublicStaffMember {
  id: string;
  name: string;
  specialty: string;
  bio: string;
  photo: MediaAsset | null;
  position: number;
}

export interface BusinessHours {
  weekday: number;
  starts_at: string;
  ends_at: string;
}

export interface ThemeConfig {
  primary?: string;
  accent?: string;
  surface?: string;
  font?: string;
  radius?: string;
}

export interface PublicSalon {
  name: string;
  slug: string;
  currency: string;
  timezone: string;
  description: string;
  address: string;
  city: string;
  service_mode: LocationMode;
  /** Quartiers desservis, en texte libre. Vide = le salon ne se déplace pas. */
  service_area: string;
  /** Point posé à la main par le salon. Chaînes décimales, ou null. */
  latitude: string | null;
  longitude: string | null;
  phone: string;
  whatsapp_number: string;
  social_links: Record<string, string>;
  /** L.identifiant WeChat du salon. Vide tant qu.il ne l.a pas renseigné. */
  wechat_id: string;
  /** Le QR qui ajoute le salon en contact WeChat. */
  wechat_qr: MediaAsset | null;
  theme_config: ThemeConfig;
  /** Page « À propos », rédigée par le salon. Vide tant qu'il n'a rien écrit. */
  about_title: string;
  about_content: string;
  about_image: MediaAsset | null;
  cancellation_policy: string;
  cancellation_deadline_hours: number;
  /** Ce qu'il advient d'un rendez-vous en retard. Vide = le salon ne dit rien. */
  late_policy: string;
  late_tolerance_minutes: number;
  /**
   * La règle d'acompte du salon, et le seul endroit où elle vive.
   *
   * Chaque prestation portait autrefois son propre montant, que le mini-site
   * affichait tel quel — pendant que la réservation en calculait un autre à
   * partir du pourcentage. Le salon publiait un chiffre et en facturait un
   * second. La prestation ne dit plus que `requires_deposit` ; le combien est
   * ici, et c'est avec lui que la page annonce ses montants.
   */
  deposit_rate: number;
  deposit_minimum: string;
  deposit_covers_items: boolean;
  min_lead_time_minutes: number;
  max_advance_days: number;
  logo: MediaAsset | null;
  banner: MediaAsset | null;
  categories: PublicCategory[];
  staff_members: PublicStaffMember[];
  business_hours: BusinessHours[];
  travel_zones: TravelZone[];
  gallery: MediaAsset[];
  rating: RatingSummary;
  /**
   * Faux quand l'abonnement du salon est échu (grâce passée) ou suspendu.
   * Le mini-site reste en ligne mais ne propose plus de réserver ; le
   * serveur refuse de toute façon la réservation. Absent d'une réponse
   * antérieure à ce champ : traité comme ouvert.
   */
  reservations_ouvertes?: boolean;
}

export interface TravelZone {
  id: string;
  name: string;
  /** Forfait du trajet. « 0 » signifie desservi gratuitement, pas « inconnu ». */
  fee_amount: string;
}

export interface Slot {
  starts_at: string;
  ends_at: string;
  staff_member_id: string;
}

export interface BookingConfirmation {
  id: string;
  starts_at: string;
  ends_at: string;
  status: string;
  service_name: string;
  staff_member_name: string;
  total_amount: string;
  deposit_amount: string;
  /**
   * Laissez-passer vers la page de paiement. Vide quand rien n'est à régler
   * en ligne — le salon encaisse alors sur place, comme avant.
   */
  payment_token: string;
  /** Options retenues, figées à la vente. */
  options_snapshot: { name: string; price: string; minutes: number }[];
  options_amount: string;
  items_snapshot: { name: string; quantity: number; total: string }[];
  items_amount: string;
  /** Vides pour un rendez-vous au salon. */
  travel_zone_name: string;
  travel_fee_amount: string;
}

export interface ApiError {
  detail: string | Record<string, string[]>;
  code: string;
  extra?: { alternatives?: string[] };
}
