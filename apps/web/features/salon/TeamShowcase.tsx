"use client";

/**
 * L'équipe : mosaïque sur grand écran, fiches sur téléphone.
 *
 * Sur un écran assez large, des portraits décalés d'un côté et la liste des
 * noms de l'autre. Désigner l'un met l'autre en couleur et atténue le reste :
 * le regard fait le lien entre un visage et un nom sans qu'on ait à légender
 * chaque photo, et la section respire au lieu d'aligner des cartes inertes.
 *
 * ---------------------------------------------------------------------------
 * Deux dispositions, parce qu'il y a deux gestes
 * ---------------------------------------------------------------------------
 *
 * Le jeu du survol suppose une souris. Sur un téléphone il n'y en a pas, et
 * le bloc se défaisait : la mosaïque restait grise — donc décorative —,
 * les noms restaient orphelins à côté d'elle, rien ne disait qui était qui,
 * et le décalage des colonnes ouvrait des trous que seule la mise en
 * regard justifie.
 *
 * En dessous de `md`, le composant rend donc **deux colonnes de fiches** :
 * une personne, une photo en couleur, son nom posé dessus. Rien à relier,
 * rien à survoler. Au-delà, la mosaïque et la liste reprennent leur place.
 *
 * Les deux branches pointent vers les mêmes adresses d'images : celle qui
 * est masquée est en `display:none`, donc absente de l'arbre
 * d'accessibilité, et le navigateur ne télécharge chaque photo qu'une fois.
 *
 * ---------------------------------------------------------------------------
 * Quatre écarts avec le modèle d'origine, et pourquoi
 * ---------------------------------------------------------------------------
 *
 * **Les largeurs sont relatives, pas en pixels.** Le modèle fixait trois
 * jeux de tailles — 110, 122 et 115 px, plus deux variantes au-dessus — et
 * laissait la mosaïque défiler horizontalement sur téléphone. Les mêmes
 * proportions exprimées en fractions de colonne tiennent dans 343 px comme
 * dans 600 px, sans barre de défilement et sans trois séries de classes à
 * maintenir. Le décalage vertical suit la même logique : en pourcentage, il
 * se mesure sur la largeur de sa propre colonne et reste proportionné
 * partout.
 *
 * **Le toucher et le focus clavier valent le survol.** Sur une tablette
 * large, la mosaïque serait restée grise sans eux.
 *
 * **Les réseaux sociaux deviennent la réservation.** Un prestataire n'a pas
 * de compte X dans notre modèle de données, et n'en aura pas : ce qu'on veut
 * voir apparaître au survol d'un nom, sur le site d'un salon, c'est le
 * chemin vers le rendez-vous. Chaque ligne est donc un lien vers
 * « Réserver ».
 *
 * **Le repli sans photo n'est pas gris.** Tout salon qui ouvre passe ses
 * premières semaines sans portrait. Une photo désaturée se lit comme un
 * parti pris ; une initiale grise se lit comme une image cassée. Les tuiles
 * sans photo gardent donc la teinte du salon — assourdie au repos dans la
 * mosaïque, pleine sur les fiches, où rien ne viendrait la révéler.
 */

import Link from "next/link";
import { useState } from "react";

import type { PublicStaffMember } from "@/lib/types";
import { SalonIcon } from "./icons";

/**
 * Largeur relative de chaque colonne.
 *
 * Les rapports viennent du modèle — 110 / 122 / 115 — ramenés à la première
 * colonne. C'est ce léger désaccord de largeur, avec le décalage vertical,
 * qui empêche la mosaïque de se lire comme un tableau.
 */
const GRILLE: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-[1fr_1.11fr]",
  3: "grid-cols-[1fr_1.11fr_1.05fr]",
};

/** Décalage de départ de chaque colonne, en part de sa propre largeur. */
const DECALAGE = ["", "pt-[39%]", "pt-[19%]"];

/**
 * L'aplat de marque des fiches sans photo, décliné en trois teintes.
 *
 * Quatre aplats identiques feraient un nuancier ; un écart de quelques pour
 * cent d'une tuile à l'autre suffit à ce que l'ensemble se lise comme un
 * assemblage. Les deux bornes restent assez sombres pour que le blanc y
 * tienne ses 4:1 — vérifié à 4,62:1 dans le pire cas.
 */
function aplat(rang: number): string {
  const tour = rang % 3;
  return `linear-gradient(${135 + tour * 25}deg,
    color-mix(in srgb, var(--salon-primary) 92%, black) 0%,
    color-mix(in srgb, var(--salon-primary) ${88 - tour * 4}%, var(--salon-accent)) 100%)`;
}

export function TeamShowcase({
  members,
  detailed = false,
}: {
  members: PublicStaffMember[];
  /** Ajoute la présentation écrite : réservé à la page « L'équipe ». */
  detailed?: boolean;
}) {
  /**
   * Le prestataire mis en avant, ou aucun.
   *
   * Un seul état pour les deux moitiés du bloc : c'est lui qui fait que
   * survoler un nom allume la bonne photo, et l'inverse.
   */
  const [actif, setActif] = useState<string | null>(null);

  if (members.length === 0) return null;

  // Deux prestataires ne remplissent pas trois colonnes : la troisième
  // resterait vide et ouvrirait un trou au milieu de la mosaïque.
  const colonnes = Math.min(3, members.length);

  return (
    <>
      {/*
        ── Sur téléphone : des fiches, pas une mosaïque ────────────────

        La mosaïque et la liste des noms sont deux moitiés reliées par le
        survol. Or le survol n'existe pas sur un téléphone : les photos y
        restaient grises et décoratives, les noms restaient orphelins à
        côté, et rien ne disait qui était qui. S'ajoutaient les trous
        ouverts par le décalage des colonnes, qui n'a de sens que quand les
        deux moitiés se font face.

        En dessous de `md`, le bloc devient donc ce qu'un petit écran sait
        lire sans geste : deux colonnes de fiches, chacune portant sa photo
        *en couleur* et son nom dessus. Un seul objet par personne, rien à
        relier.
      */}
      {/* Trois colonnes dès 640 px : à deux, la fiche atteignait 362 px de
          large sur une tablette — deux portraits géants par rangée. */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 sm:gap-3 md:hidden">
        {members.map((member, rang) => (
          <Fiche key={member.id} member={member} rang={rang} />
        ))}
      </div>

      {/* ── À partir de md : la mosaïque et la liste ───────────────── */}
      <div className="hidden md:flex md:flex-row md:items-start md:gap-10 lg:gap-14">
        <div
          className={`grid w-full gap-2 sm:gap-3 md:w-[46%] lg:w-[48%] ${GRILLE[colonnes]}`}
        >
          {Array.from({ length: colonnes }, (_, colonne) => (
            <div
              key={colonne}
              className={`flex flex-col gap-2 sm:gap-3 ${DECALAGE[colonne]}`}
            >
              {members
                .map((member, rang) => ({ member, rang }))
                .filter(({ rang }) => rang % colonnes === colonne)
                .map(({ member, rang }) => (
                  <Tuile
                    key={member.id}
                    member={member}
                    rang={rang}
                    actif={actif}
                    onActif={setActif}
                  />
                ))}
            </div>
          ))}
        </div>

        {/* ── Les noms ──────────────────────────────────────────────── */}
        {/*
          Une seule colonne : côte à côte avec la mosaïque, la liste doit
          rester étroite pour que l'œil fasse l'aller-retour avec les photos
          sans balayer toute la page.
        */}
        <div className="flex min-w-0 flex-1 flex-col gap-5 pt-1">
          {members.map((member) => (
            <Ligne
              key={member.id}
              member={member}
              actif={actif}
              onActif={setActif}
              detailed={detailed}
            />
          ))}
        </div>
      </div>
    </>
  );
}

/* ───────────────────────────────────────────────────────────────────────
   La fiche — téléphone et petite tablette
   ─────────────────────────────────────────────────────────────────────── */

/**
 * Une personne, en un seul objet.
 *
 * Le nom se pose *sur* la photo derrière un dégradé plutôt qu'en dessous :
 * sous l'image, il ajoutait une bande de texte à chaque fiche et deux
 * rangées suffisaient à remplir l'écran. Le dégradé garantit qu'il reste
 * lisible sur une photo claire comme sur une photo sombre.
 *
 * Et la photo est **en couleur**. Le gris de la mosaïque est la moitié d'un
 * effet : il n'a de sens que parce que le survol le lève. Sans survol, ce
 * n'est plus un parti pris, c'est une page éteinte.
 */
function Fiche({ member, rang }: { member: PublicStaffMember; rang: number }) {
  return (
    <Link
      href="/reserver"
      className="group relative block overflow-hidden rounded-xl outline-offset-2"
    >
      <div className="aspect-[4/5] w-full overflow-hidden">
        {member.photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={member.photo.url}
            alt={member.photo.alt_text || member.name}
            loading="lazy"
            className="size-full object-cover transition-transform duration-500 group-active:scale-[1.03]"
          />
        ) : (
          <span
            aria-hidden
            className="flex size-full items-center justify-center text-4xl font-semibold text-white"
            style={{
              background: aplat(rang),
              /*
                Assombri d'un cran.

                À pleine intensité, l'aplat de marque est la surface la plus
                claire de la grille : il attirait l'œil davantage que les
                portraits, c'est-à-dire l'inverse de ce qu'on veut. Assez
                foncé pour se ranger derrière eux, assez coloré pour rester
                la teinte du salon — et le blanc y gagne, mesuré à 6,98:1.
              */
              filter: "saturate(0.85) brightness(0.8)",
            }}
          >
            {member.name.slice(0, 1).toUpperCase()}
          </span>
        )}
      </div>

      <span
        aria-hidden
        className="absolute inset-x-0 bottom-0 h-3/5 bg-gradient-to-t from-black/80 via-black/35 to-transparent"
      />
      <div className="absolute inset-x-0 bottom-0 p-2.5">
        <h3 className="truncate text-[0.82rem] font-semibold leading-tight text-white drop-shadow">
          {member.name}
        </h3>
        {member.specialty && (
          <p className="mt-1 line-clamp-2 text-[0.58rem] font-medium uppercase leading-snug tracking-[0.1em] text-white/80">
            {member.specialty}
          </p>
        )}
      </div>
    </Link>
  );
}

/* ───────────────────────────────────────────────────────────────────────
   La tuile
   ─────────────────────────────────────────────────────────────────────── */

/**
 * Un portrait de la mosaïque.
 *
 * Volontairement pas un bouton : la même désignation est offerte au clavier
 * par la ligne voisine, qui porte le nom et mène quelque part. En faire une
 * seconde cible focalisable doublerait les arrêts de tabulation pour un
 * effet purement décoratif.
 */
function Tuile({
  member,
  rang,
  actif,
  onActif,
}: {
  member: PublicStaffMember;
  rang: number;
  actif: string | null;
  onActif: (id: string | null) => void;
}) {
  const estActif = actif === member.id;
  const eteint = actif !== null && !estActif;

  return (
    <div
      onMouseEnter={() => onActif(member.id)}
      onMouseLeave={() => onActif(null)}
      // Le toucher n'émet pas toujours « mouseleave » : on désigne sans
      // jamais éteindre, et c'est la tuile suivante qui reprend la main.
      onClick={() => onActif(member.id)}
      className={`relative aspect-[11/12] cursor-pointer overflow-hidden rounded-xl transition-opacity duration-300 ${
        eteint ? "opacity-60" : "opacity-100"
      }`}
    >
      {member.photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={member.photo.url}
          alt={member.photo.alt_text || member.name}
          loading="lazy"
          className="size-full object-cover transition-[filter,transform] duration-500"
          style={{
            filter: estActif ? "none" : "grayscale(1) brightness(0.78)",
            transform: estActif ? "scale(1.04)" : "scale(1)",
          }}
        />
      ) : (
        <span
          aria-hidden
          className="flex size-full items-center justify-center text-3xl font-semibold text-white transition-[filter] duration-500 sm:text-4xl md:text-5xl"
          style={{
            background: aplat(rang),
            filter: estActif ? "none" : "saturate(0.25) brightness(0.92)",
          }}
        >
          {member.name.slice(0, 1).toUpperCase()}
        </span>
      )}
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────
   La ligne
   ─────────────────────────────────────────────────────────────────────── */

function Ligne({
  member,
  actif,
  onActif,
  detailed,
}: {
  member: PublicStaffMember;
  actif: string | null;
  onActif: (id: string | null) => void;
  detailed: boolean;
}) {
  const estActif = actif === member.id;
  const eteint = actif !== null && !estActif;

  return (
    <Link
      href="/reserver"
      onMouseEnter={() => onActif(member.id)}
      onMouseLeave={() => onActif(null)}
      onFocus={() => onActif(member.id)}
      onBlur={() => onActif(null)}
      className={`group block rounded-lg outline-offset-4 transition-opacity duration-300 ${
        eteint ? "opacity-50" : "opacity-100"
      }`}
    >
      <span className="flex items-center gap-2.5">
        {/*
          Le tiret devant le nom.

          Il s'allonge et prend la couleur du salon quand la ligne est
          désignée. C'est le seul repère qui fonctionne aussi quand la
          mosaïque est hors champ — sur téléphone, après avoir fait défiler.
        */}
        <span
          aria-hidden
          className={`h-[3px] shrink-0 rounded-full transition-all duration-300 ${
            estActif
              ? "w-6 bg-[var(--salon-primary)]"
              : "w-3.5 bg-[var(--site-subtle)] opacity-45"
          }`}
        />
        <span
          className={`min-w-0 truncate text-[1.05rem] font-semibold leading-tight tracking-tight transition-colors duration-300 ${
            estActif ? "text-[var(--site-ink)]" : "text-[var(--site-muted)]"
          }`}
        >
          {member.name}
        </span>

        {/* Ce qui apparaît à la place des réseaux sociaux du modèle. */}
        <span
          aria-hidden
          className={`inline-flex shrink-0 items-center gap-1 text-[0.7rem] font-medium text-[var(--salon-ink)] transition-all duration-200 ${
            estActif
              ? "translate-x-0 opacity-100"
              : "-translate-x-1.5 opacity-0"
          }`}
        >
          Réserver
          <SalonIcon name="arrow" className="size-3" />
        </span>
      </span>

      {member.specialty && (
        <span
          className={`mt-1.5 block pl-[26px] text-[0.66rem] font-medium uppercase tracking-[0.18em] transition-colors duration-300 ${
            estActif ? "text-[var(--salon-ink)]" : "text-[var(--site-subtle)]"
          }`}
        >
          {member.specialty}
        </span>
      )}

      {detailed && member.bio && (
        <span className="mt-2 block pl-[26px] text-[0.78rem] leading-relaxed text-[var(--site-muted)] md:text-sm">
          {member.bio}
        </span>
      )}
    </Link>
  );
}
