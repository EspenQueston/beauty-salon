/**
 * Les images qui défilent en fond des en-têtes du mini-site.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi cette fonction existe
 * ---------------------------------------------------------------------------
 *
 * Le défilé vivait dans le haut de page d'accueil, et nulle part ailleurs.
 * Les pages intérieures — Prestations, Réalisations, L'équipe, À propos,
 * Infos — recevaient un aplat de couleur figé. On passait donc d'un salon
 * vivant à un gabarit en un clic, ce qui est précisément l'impression à
 * éviter.
 *
 * La construction des diapositives est extraite ici pour que **toutes** les
 * pages partent de la même liste. Recopier la logique page par page aurait
 * garanti qu'elles divergent : un salon dont l'accueil montre ses ongles et
 * dont la page Prestations montre autre chose n'a pas l'air d'un salon, il a
 * l'air d'un bug.
 *
 * ---------------------------------------------------------------------------
 * Une par catégorie d'abord, puis on complète
 * ---------------------------------------------------------------------------
 *
 * Une par catégorie *d'abord* plutôt que les six premières du catalogue :
 * sinon un salon dont la première catégorie contient huit coiffures ne
 * montrerait jamais ses ongles, et une visiteuse venue pour ça repartirait.
 *
 * Mais s'arrêter là était une faute, et elle se voyait. Un salon à deux
 * catégories n'obtenait que deux images — et le carrousel, qui exige au
 * moins deux vues pour tourner, se figeait à la première dès qu'il n'y avait
 * qu'une seule catégorie. Un salon qui débute, celui qui a le plus besoin
 * d'une page vivante, était précisément celui qui héritait d'un fond fixe.
 *
 * Le reste du catalogue complète donc la liste jusqu'à la limite. Un salon de
 * trois prestations en montre trois ; un salon de quarante en montre six,
 * réparties sur ses catégories.
 *
 * La bannière du salon, s'il en a posé une, ouvre le défilé : c'est l'image
 * qu'il a choisie pour se présenter, elle passe avant celles qu'on a choisies
 * pour lui.
 *
 * ---------------------------------------------------------------------------
 * Un salon sans une seule photo défile quand même
 * ---------------------------------------------------------------------------
 *
 * C'est la majorité des salons le premier jour. Chaque prestation sans photo
 * reçoit une illustration d'ambiance choisie d'après sa catégorie — un salon
 * d'ongles n'affiche pas un fauteuil de barbier — et **stable** : elle est
 * tirée de l'identifiant de la prestation, donc identique d'une visite à
 * l'autre et d'une page à l'autre.
 */

import {
  illustrationUrl,
  pickIllustration,
  themeFromCategory,
} from "@/lib/illustrations";
import { formatServicePrice } from "@/lib/format";
import type { PublicSalon } from "@/lib/types";
import type { HeroSlide } from "./HeroCarousel";
import { srcSetDe, srcSetIllustration } from "./images";

/**
 * Nombre d'images retenues.
 *
 * Six sur l'accueil, quatre sur les pages intérieures. Ce n'est pas une
 * question de goût : toutes les diapositives sont dans le document, donc
 * toutes se téléchargent, même invisibles. Sur un forfait mobile facturé à la
 * donnée — le cas de la plupart des visiteuses visées — deux images de moins
 * par page intérieure se remarquent sur la facture, pas à l'écran.
 */
export const HOME_SLIDES = 6;
export const PAGE_SLIDES = 4;

export function salonSlides(salon: PublicSalon, limit = HOME_SLIDES): HeroSlide[] {
  const toSlide = (
    service: PublicSalon["categories"][number]["services"][number],
    categoryName: string,
  ): HeroSlide => ({
    key: service.id,
    ...(service.image
      ? { url: service.image.url, srcSet: srcSetDe(service.image) }
      : (() => {
          const id = pickIllustration(service.id, themeFromCategory(categoryName)).id;
          return {
            url: illustrationUrl(id, { width: 1600, ratio: 0.62 }),
            srcSet: srcSetIllustration(id, 0.62),
          };
        })()),
    label: service.name,
    price: formatServicePrice(service, salon.currency),
  });

  // La tête de chaque catégorie : c'est ce qui garantit qu'aucun métier du
  // salon n'est passé sous silence.
  const perCategory = salon.categories
    .filter((category) => category.services.length > 0)
    .map((category) => toSlide(category.services[0], category.name));

  // Puis le reste, catégorie par catégorie, pour compléter jusqu'à la limite.
  // Sans lui, un salon à une seule catégorie n'obtenait qu'une image — et un
  // carrousel d'une image ne tourne pas.
  const rest = salon.categories.flatMap((category) =>
    category.services.slice(1).map((service) => toSlide(service, category.name)),
  );

  const slides: HeroSlide[] = [
    ...(salon.banner
      ? [
          {
            key: "banner",
            url: salon.banner.url,
            srcSet: srcSetDe(salon.banner),
            label: salon.name,
            price: "",
          },
        ]
      : []),
    ...perCategory,
    ...rest,
  ].slice(0, limit);

  // Un salon sans catalogue ni bannière garde une image d'ambiance : un
  // en-tête vide se lit comme une page cassée.
  if (slides.length === 0) {
    const theme = salon.categories[0]
      ? themeFromCategory(salon.categories[0].name)
      : "salon";
    slides.push({
      key: "fallback",
      url: illustrationUrl(pickIllustration(salon.slug, theme).id, {
        width: 1600,
        ratio: 0.62,
      }),
      label: salon.name,
      price: "",
    });
  }

  return slides;
}
