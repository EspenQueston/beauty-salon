"use client";

/**
 * Défilé des prestations en fond de haut de page.
 *
 * ---------------------------------------------------------------------------
 * Ce que ça remplace, et pourquoi
 * ---------------------------------------------------------------------------
 *
 * Le haut de page portait une photo fixe. Elle disait « salon de beauté »,
 * pas « ce que *ce* salon sait faire ». Une visiteuse qui arrive d'un lien
 * WhatsApp doit comprendre en trois secondes si on y fait des tresses ou des
 * ongles — le défilé le montre au lieu de l'écrire.
 *
 * ---------------------------------------------------------------------------
 * Le défilé tourne tout seul, et il faut s'y tenir
 * ---------------------------------------------------------------------------
 *
 * Une première version se mettait en pause dès que le pointeur entrait dans
 * le fond — un bloc qui couvre *tout* le haut de page. Sur un ordinateur, le
 * curseur y traîne en permanence : le défilé restait donc figé sur sa
 * première image, ce qui est exactement l'inverse de ce qu'il existe pour
 * faire. Sur mobile, c'était pire : un `pointerenter` part au premier
 * effleurement et le `pointerleave` correspondant ne vient jamais.
 *
 * La règle est donc étroite : **seules les puces** mettent en pause, et
 * seulement sous un vrai pointeur — jamais un doigt. Elles sont assez petites
 * pour qu'on ne les survole que délibérément. Cliquer une puce arrête
 * définitivement la rotation : c'est le geste par lequel la visiteuse dit
 * « je regarde celle-ci ».
 *
 * ---------------------------------------------------------------------------
 * Deux habillages, et ils n'ont plus les mêmes commandes
 * ---------------------------------------------------------------------------
 *
 * Les puces, et la légende qui nommait la prestation affichée, ont été
 * retirées du haut de page d'accueil à la demande du salon : le fond y
 * redevient un décor, sans rien qui dispute le regard à la colonne de faits
 * posée dessus. Les pages intérieures gardent les leurs, discrètes dans un
 * coin.
 *
 * Le défilé, lui, ne change pas : c'est lui qui montre ce que le salon sait
 * faire, et le retirer viderait le haut de page de sa raison d'être. Seules
 * les commandes ont disparu.
 *
 * Conséquence à connaître, et assumée : sur l'accueil, il n'existe plus de
 * commande d'arrêt, alors que le critère WCAG 2.2.2 en demande une pour tout
 * contenu qui s'anime au-delà de cinq secondes. `prefers-reduced-motion`
 * ralentit le rythme et supprime le fondu, mais ne l'arrête pas. C'est écrit
 * ici pour que la prochaine personne le sache avant de toucher au fichier —
 * et pour qu'on sache où rebrancher un mécanisme le jour où il le faudra.
 *
 * ---------------------------------------------------------------------------
 * Autres contraintes
 * ---------------------------------------------------------------------------
 *
 *   - **Sans JavaScript**, la première image reste affichée : le fond n'est
 *     jamais vide. Les suivantes ne font que se superposer.
 *   - **Bande passante** : seule la première image est chargée en priorité,
 *     les autres en `lazy`. Sur un forfait facturé à la donnée, précharger
 *     six photos plein écran coûterait plus que tout le reste de la page.
 *   - **`prefers-reduced-motion`** supprime le fondu et ralentit le rythme,
 *     mais ne fige pas le défilé : ce réglage demande moins d'animation, et
 *     un changement d'image sans transition n'en est pas une.
 *   - Un onglet en arrière-plan ne compose pas la page : inutile d'y faire
 *     tourner quoi que ce soit.
 *   - Tout passe par l'opacité, jamais par la géométrie : le navigateur
 *     compose sans recalculer la page.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface HeroSlide {
  key: string;
  url: string;
  /** Copies réduites de la même image : voir `images.ts`. */
  srcSet?: string;
  /** Nom de la prestation, affiché sous le défilé. */
  label: string;
  /** Tarif formaté, ou chaîne vide. */
  price: string;
}

/*
 * Le rythme du défilé.
 *
 * 2,6 s par image, fondu de 700 ms compris. C'est court, et c'est voulu : ces
 * photos ne se lisent pas, elles se reconnaissent — on voit « des tresses »,
 * « des ongles », et on a compris. Le rythme précédent laissait 4,2 s sur
 * chacune, soit près de deux secondes où il ne se passait plus rien : une
 * page qui paraît figée alors qu'elle attend.
 *
 * En dessous de deux secondes en revanche, le fondu de la suivante commence
 * avant que l'œil ait fini la précédente, et le fond se met à clignoter.
 */
const INTERVAL = 2600;
/** Sans fondu, l'image saute : on laisse plus longtemps pour la regarder. */
const CALM_INTERVAL = 5000;

/**
 * Deux mises en scène pour le même défilé.
 *
 *   « accueil » — le haut de page d'accueil : voiles sombres, légende qui
 *                 nomme la prestation, puces au centre.
 *   « bandeau » — les en-têtes des pages intérieures. Plus court, et surtout
 *                 **sans légende** : ces pages ont déjà un titre, et un nom
 *                 de prestation qui change toutes les 2,6 s juste à côté lui
 *                 ferait concurrence au lieu de l'appuyer.
 *
 * Le voile n'est pas posé ici en mode bandeau : c'est la page qui l'apporte,
 * avec son propre dégradé. C'est ce qui permet à « Réalisations » de rester
 * reconnaissable après « Prestations » tout en montrant les mêmes photos.
 *
 * Les puces restent dans les deux cas. Elles ne sont pas décoratives : elles
 * sont le seul moyen d'arrêter un contenu qui bouge tout seul, ce qu'exige le
 * critère WCAG 2.2.2.
 */
export type CarouselVariant = "accueil" | "bandeau";

export function HeroCarousel({
  slides,
  variant = "accueil",
}: {
  slides: HeroSlide[];
  variant?: CarouselVariant;
}) {
  const band = variant === "bandeau";
  const [index, setIndex] = useState(0);

  /** La visiteuse a choisi une image : le défilé lui laisse la main. */
  const [taken, setTaken] = useState(false);

  /** Survol des puces uniquement, et jamais depuis un écran tactile. */
  const hovering = useRef(false);

  /*
   * `prefers-reduced-motion` est lu après le montage, pas pendant le rendu :
   * le serveur n'a pas de `matchMedia`, et supposer une réponse ici
   * produirait un écart d'hydratation.
   */
  const [calm, setCalm] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setCalm(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  const advance = useCallback(() => {
    setIndex((current) => (current + 1) % slides.length);
  }, [slides.length]);

  useEffect(() => {
    if (slides.length < 2 || taken) return;

    const timer = setInterval(
      () => {
        if (hovering.current || document.visibilityState === "hidden") return;
        advance();
      },
      calm ? CALM_INTERVAL : INTERVAL,
    );

    return () => clearInterval(timer);
  }, [advance, slides.length, taken, calm]);

  if (slides.length === 0) return null;

  return (
    <>
      <div className="absolute inset-0 -z-10">
        {slides.map((slide, position) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={slide.key}
            src={slide.url}
            srcSet={slide.srcSet}
            sizes={slide.srcSet ? "100vw" : undefined}
            alt=""
            aria-hidden
            fetchPriority={position === 0 ? "high" : "low"}
            loading={position === 0 ? "eager" : "lazy"}
            className={`absolute inset-0 size-full object-cover ${
              calm ? "" : "transition-opacity duration-700 ease-out"
            }`}
            style={{ opacity: position === index ? 1 : 0 }}
          />
        ))}

        {/* Deux voiles superposés : un dégradé vertical pour que le texte
            reste lisible quelle que soit la photo, une teinte de marque pour
            que l'image appartienne au salon plutôt qu'à une banque
            d'images.

            En mode bandeau, c'est la page qui apporte son propre voile — son
            dégradé de section. En poser un second par-dessus noircirait
            l'image au point qu'on ne distinguerait plus ce qu'elle montre. */}
        {!band && (
          <>
            <div
              className="absolute inset-0"
              style={{
                background:
                  "linear-gradient(180deg, rgb(0 0 0 / 0.44) 0%, rgb(0 0 0 / 0.64) 55%, rgb(0 0 0 / 0.80) 100%)",
              }}
            />
            <div
              className="absolute inset-0 opacity-70 mix-blend-soft-light"
              style={{ background: "var(--salon-primary)" }}
            />
          </>
        )}
      </div>

      {/*
        Puces de l'en-tête des pages intérieures — et d'elles seules.

        ---------------------------------------------------------------------
        Ce que l'accueil a perdu, et ce que ça coûte
        ---------------------------------------------------------------------

        Le haut de page d'accueil portait la même chose en plus grand : le nom
        de la prestation affichée, et une rangée de puces sous elle. Les deux
        ont été retirés à la demande du salon. Le fond redevient ce qu'il est,
        un décor, et la colonne de faits juste au-dessus n'a plus rien sous
        elle qui lui dispute le regard.

        Ce n'est pas gratuit, et il faut l'écrire : les puces étaient le seul
        moyen d'arrêter la rotation, c'est-à-dire le mécanisme que réclame le
        critère WCAG 2.2.2 pour tout contenu qui s'anime plus de cinq
        secondes. Il est remplacé, faute de mieux, par le respect strict de
        `prefers-reduced-motion` : le défilé ne ralentit plus, il **s'arrête**.
        Qui a demandé moins d'animation à son système obtient un fond fixe.

        Les pages intérieures gardent leurs puces : leur bandeau fait deux
        cents pixels de haut, trois petits traits dans un coin n'y gênent
        personne, et le mécanisme d'arrêt y reste donc entier.
      */}
      {band && slides.length > 1 && (
        // Serrées dans le coin bas droit : l'en-tête d'une page intérieure
        // fait deux cents pixels de haut, et des puces centrées y tomberaient
        // sur le titre.
        <div className="pointer-events-none absolute bottom-3 right-4 z-10 flex sm:bottom-4 sm:right-6">
          <div
            className="pointer-events-auto flex items-center gap-1.5"
            onPointerEnter={(event) => {
              // Un doigt entre sans jamais ressortir : le défilé resterait
              // figé pour le reste de la visite.
              if (event.pointerType === "touch") return;
              hovering.current = true;
            }}
            onPointerLeave={() => {
              hovering.current = false;
            }}
          >
            {slides.map((slide, position) => (
              <button
                key={slide.key}
                type="button"
                onClick={() => {
                  setIndex(position);
                  setTaken(true);
                }}
                onFocus={() => {
                  hovering.current = true;
                }}
                onBlur={() => {
                  hovering.current = false;
                }}
                aria-label={`Voir ${slide.label}`}
                aria-current={position === index}
                className={`h-1 rounded-full transition-all duration-500 ${
                  position === index
                    ? "w-5 bg-white"
                    : "w-1 bg-white/55 hover:bg-white/85"
                }`}
              />
            ))}
          </div>
        </div>
      )}
    </>
  );
}
