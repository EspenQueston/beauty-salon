"use client";

/**
 * L'équipe, en mosaïque.
 *
 * Des portraits décalés d'un côté, la liste des noms de l'autre. Désigner
 * l'un met l'autre en couleur et atténue le reste : le regard fait le lien
 * entre un visage et un nom sans qu'on ait à légender chaque photo, et la
 * section respire au lieu d'aligner quatre cartes inertes.
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
 * **Le survol ne suffit pas.** Sur un téléphone il n'existe pas : la
 * mosaïque serait restée grise en permanence, c'est-à-dire éteinte pour la
 * moitié des visiteuses. Le toucher et le focus clavier déclenchent donc le
 * même état que le survol.
 *
 * **Les réseaux sociaux deviennent la réservation.** Un prestataire n'a pas
 * de compte X dans notre modèle de données, et n'en aura pas : ce qu'on veut
 * voir apparaître au survol d'un nom, sur le site d'un salon, c'est le
 * chemin vers le rendez-vous. Chaque ligne est donc un lien vers
 * « Réserver ».
 *
 * **Le repli sans photo n'est pas gris.** Aucun des salons en service n'a
 * encore chargé de portrait, et ce sera le cas de tous les nouveaux pendant
 * leurs premières semaines. Une photo désaturée se lit comme un parti pris ;
 * une initiale grise se lit comme une image cassée. Les tuiles sans photo
 * gardent donc la teinte du salon, simplement assourdie au repos.
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
    <div className="flex flex-col gap-7 md:flex-row md:items-start md:gap-10 lg:gap-14">
      {/* ── La mosaïque ─────────────────────────────────────────────── */}
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

      {/* ── Les noms ────────────────────────────────────────────────── */}
      {/*
        Deux colonnes sur téléphone, une seule dès que la mosaïque passe à
        gauche : côte à côte, la liste doit rester étroite pour que l'œil
        fasse l'aller-retour avec les photos sans balayer la page.

        Sauf quand chaque ligne porte une présentation écrite. Une colonne de
        160 px tient vingt-deux caractères : le nom et la spécialité y
        gagnent en densité, un paragraphe y devient une colonne de confettis.
        La page « L'équipe » repasse donc à une colonne sur téléphone — c'est
        la seule qui affiche les biographies.
      */}
      <div
        className={`grid min-w-0 flex-1 gap-x-4 gap-y-5 md:flex md:flex-col md:gap-5 md:pt-1 ${
          detailed ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-2"
        }`}
      >
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
            /*
              Trois teintes de marque en rotation.

              Quatre aplats identiques feraient un nuancier ; un écart de
              quelques pour cent d'un tuile à l'autre suffit à ce que la
              mosaïque se lise comme un assemblage. Les deux bornes restent
              assez sombres pour que le blanc y tienne ses 4:1.
            */
            background: `linear-gradient(${135 + (rang % 3) * 25}deg,
              color-mix(in srgb, var(--salon-primary) 92%, black) 0%,
              color-mix(in srgb, var(--salon-primary) ${88 - (rang % 3) * 4}%, var(--salon-accent)) 100%)`,
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
          className={`min-w-0 truncate text-[0.95rem] font-semibold leading-tight tracking-tight transition-colors duration-300 md:text-[1.05rem] ${
            estActif ? "text-[var(--site-ink)]" : "text-[var(--site-muted)]"
          }`}
        >
          {member.name}
        </span>

        {/* Ce qui apparaît à la place des réseaux sociaux du modèle. */}
        <span
          aria-hidden
          className={`hidden shrink-0 items-center gap-1 text-[0.7rem] font-medium text-[var(--salon-ink)] transition-all duration-200 sm:inline-flex ${
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
          className={`mt-1.5 block pl-[26px] text-[0.58rem] font-medium uppercase tracking-[0.14em] transition-colors duration-300 md:text-[0.66rem] md:tracking-[0.18em] ${
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
