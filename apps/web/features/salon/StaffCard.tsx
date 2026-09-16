/**
 * Fiche d'un prestataire.
 *
 * On réserve chez quelqu'un, pas chez une enseigne : mettre un visage et une
 * spécialité en face d'un nom change le taux de réservation bien plus qu'un
 * argument commercial de plus.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi le portrait occupe maintenant toute la carte
 * ---------------------------------------------------------------------------
 *
 * La version précédente centrait un médaillon rond au milieu d'un rectangle
 * blanc. Pour un salon sans photos — le cas le plus courant les premières
 * semaines — cela donnait quatre grands cercles pastel portant une initiale,
 * au milieu de beaucoup de vide. La section « L'équipe » était la plus haute
 * de la page et la moins informative.
 *
 * Le portrait remplit désormais le haut de la carte, et le nom se pose
 * dessus sur un dégradé. Trois conséquences : la carte est plus courte, la
 * photo est réellement regardée quand il y en a une, et l'initiale — qui
 * occupe la même surface, dans la couleur du salon — se lit comme un parti
 * pris graphique plutôt que comme une photo manquante.
 */

import Link from "next/link";

import type { PublicStaffMember } from "@/lib/types";
import { SalonIcon } from "./icons";
import { Tilt } from "./Tilt";
import { SURFACE } from "./ui";

export function StaffCard({
  member,
  detailed = false,
}: {
  member: PublicStaffMember;
  /** Affiche la présentation complète : réservé à la page « L'équipe ». */
  detailed?: boolean;
}) {
  return (
    <Tilt className="h-full" glare={false}>
      {/* Deux fiches par ligne sur téléphone : les tailles se resserrent en
          dessous de `sm` pour rester lisibles sur 170 px. */}
      <article className={`${SURFACE} group flex h-full flex-col overflow-hidden`}>
        {/*
          Carrée tant qu'il n'y a que deux colonnes, portrait à quatre.

          Un rapport 4/5 sur une grille de deux donne des tuiles de 425 px de
          haut : quatre prestataires occupent alors deux écrans de téléphone
          pour quatre noms. À quatre colonnes, la tuile est deux fois plus
          étroite et le portrait retrouve sa place.
        */}
        <div className="relative aspect-square overflow-hidden lg:aspect-[4/5]">
          {member.photo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={member.photo.url}
              alt={member.photo.alt_text || member.name}
              loading="lazy"
              className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
            />
          ) : (
            /*
              Sans photo : l'initiale, en grand, dans la couleur du salon.

              Ce n'est pas un placeholder gris. Une lettre tenue dans un
              aplat de marque fait une carte assumée, là où un médaillon vide
              faisait une fiche inachevée — et c'est l'état par défaut de
              tous les salons qui viennent d'ouvrir leur site.
            */
            <span
              aria-hidden
              className="flex size-full items-center justify-center text-5xl font-semibold sm:text-6xl"
              style={{
                background: "var(--salon-accent)",
                color: "var(--salon-ink)",
              }}
            >
              {member.name.slice(0, 1).toUpperCase()}
            </span>
          )}

          {/*
            Le nom sur la photo, derrière un dégradé.

            Sous la photo, il ajoutait une bande blanche à une carte qui n'en
            avait pas besoin. Posé dessus, il fait partie du portrait — et le
            dégradé garantit qu'il reste lisible sur une photo claire comme
            sur une photo sombre.
          */}
          <span
            aria-hidden
            className="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-black/70 to-transparent"
          />
          <div className="absolute inset-x-0 bottom-0 p-3 sm:p-4">
            <h3 className="truncate text-[0.9rem] font-semibold text-white drop-shadow sm:text-base">
              {member.name}
            </h3>
            {member.specialty && (
              <p className="mt-0.5 flex items-center gap-1.5 text-[0.72rem] text-white/85 sm:text-[0.8rem]">
                <SalonIcon name="sparkle" className="size-3 shrink-0" />
                <span className="truncate">{member.specialty}</span>
              </p>
            )}
          </div>
        </div>

        {(member.bio || detailed) && (
          <div className="flex flex-1 flex-col p-3 sm:p-4">
            {member.bio && (
              <p
                className={`text-[0.78rem] leading-relaxed text-[var(--site-muted)] sm:text-sm ${
                  detailed ? "" : "line-clamp-2"
                }`}
              >
                {member.bio}
              </p>
            )}

            {detailed && (
              <Link
                href="/reserver"
                className="mt-auto pt-4 text-sm font-medium text-[var(--salon-ink)] underline-offset-4 hover:underline"
              >
                Prendre rendez-vous
              </Link>
            )}
          </div>
        )}
      </article>
    </Tilt>
  );
}
