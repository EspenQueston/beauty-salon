"use client";

/**
 * Le panneau illustré de l'écran d'identification cliente.
 *
 * ---------------------------------------------------------------------------
 * Ce qu'il était, et pourquoi il a changé
 * ---------------------------------------------------------------------------
 *
 * Trois photos décalées en perspective, plus une pastille « Confirmé ».
 * Deux problèmes, et le second était le sérieux :
 *
 *   1. Les trois cartes se chevauchaient assez pour qu'aucune ne se lise.
 *      Une image bien cadrée dit la même chose et se regarde vraiment.
 *
 *   2. La pastille « Confirmé » avait la forme d'une notification de
 *      réservation. Sur un écran de connexion, devant quelqu'un qui n'est
 *      pas encore identifié, une pastille d'état laisse croire qu'un
 *      rendez-vous existe — et il n'y en a aucun. Un décor n'a pas le droit
 *      de ressembler à une donnée.
 *
 * ---------------------------------------------------------------------------
 * Ce qui reste
 * ---------------------------------------------------------------------------
 *
 * La légère inclinaison au passage du pointeur : elle coûte une `transform`
 * composée par le processeur graphique, donc rien, et elle suffit à
 * distinguer une page vivante d'une capture d'écran. `prefers-reduced-motion`
 * la fige, et l'image ne paraît que sur grand écran — sur un téléphone elle
 * repousserait les trois arguments sans rien ajouter.
 */

import { useRef, useState } from "react";

import { illustrationUrl, pickIllustration } from "@/lib/illustrations";
import { AuthAsideTitle, AuthPoint, AuthPoints } from "./AuthShell";

/** Amplitude de la rotation, en degrés. Au-delà, l'effet devient un gadget. */
const TILT = 5;

export interface ShowcasePoint {
  title: string;
  body: string;
}

export function AuthShowcase({
  seed,
  title,
  points,
}: {
  /** Graine de l'illustration : un salon garde la même photo. */
  seed: string;
  title: string;
  points: ShowcasePoint[];
}) {
  const frame = useRef<HTMLDivElement>(null);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });

  function follow(event: React.PointerEvent<HTMLDivElement>) {
    const box = frame.current?.getBoundingClientRect();
    if (!box) return;

    // Position du pointeur ramenée à [-1, 1] depuis le centre du panneau.
    const x = (event.clientX - box.left) / box.width - 0.5;
    const y = (event.clientY - box.top) / box.height - 0.5;
    setTilt({ x: -y * TILT * 2, y: x * TILT * 2 });
  }

  const photo = pickIllustration(`${seed}-a`, "braids");

  return (
    <div>
      <div
        ref={frame}
        onPointerMove={follow}
        onPointerLeave={() => setTilt({ x: 0, y: 0 })}
        aria-hidden
        className="auth-stage mb-8 hidden h-64 w-full lg:block"
      >
        <div
          className="auth-stage-inner"
          style={{ transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)` }}
        >
          {/* Cadrage panoramique : une photo de salon se lit à la coiffure,
              pas au plafond. */}
          <span className="absolute inset-0 overflow-hidden rounded-2xl border border-line shadow-card">
            {/*
              Positionnée, et non simplement « 100 % de haut ».

              `height: 100%` ne se résout pas ici — l'image reprenait son
              rapport naturel, débordait du cadre, et le recadrage promis par
              `object-cover` n'avait plus lieu. Ancrée sur les quatre côtés,
              sa boîte est celle du cadre, quoi qu'il arrive.
            */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              // Le rapport demandé est celui du cadre : ainsi le recadrage
              // se fait une seule fois, chez l'hébergeur d'images, et
              // `object-cover` n'a plus rien à rogner — c'est ce double
              // rognage qui coupait les visages.
              src={illustrationUrl(photo.id, { width: 760, ratio: 0.42 })}
              alt=""
              loading="lazy"
              className="absolute inset-0 size-full object-cover"
            />
          </span>
        </div>
      </div>

      <AuthAsideTitle>{title}</AuthAsideTitle>
      <AuthPoints>
        {points.map((point) => (
          <AuthPoint key={point.title} title={point.title}>
            {point.body}
          </AuthPoint>
        ))}
      </AuthPoints>
    </div>
  );
}
