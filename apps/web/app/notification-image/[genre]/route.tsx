/**
 * La grande image d'une notification, quand le salon n'a pas de photo.
 *
 * ---------------------------------------------------------------------------
 * Pourquoi une image composée
 * ---------------------------------------------------------------------------
 *
 * Windows, Android et ChromeOS affichent une grande image en tête de
 * notification. Le serveur y met d'abord la photo de la prestation réservée,
 * puis la bannière du salon (apps/notifications/habillage.py). Un salon qui
 * vient de s'inscrire n'a ni l'une ni l'autre : sans cette route, ses
 * notifications seraient les seules à arriver sans image.
 *
 * Elle est composée aux couleurs du salon, avec le pictogramme que
 * l'événement porte dans le tableau de bord : la notification ressemble à
 * l'écran qu'elle ouvre.
 *
 * ---------------------------------------------------------------------------
 * Ce que la route accepte
 * ---------------------------------------------------------------------------
 *
 *   /notification-image/<genre>?salon=<nom>&couleur=<rrggbb>
 *
 * Le genre vient d'une liste fermée, la couleur doit être un code
 * hexadécimal, le nom est tronqué à quarante caractères : on ne compose pas
 * d'image à partir de n'importe quoi. Les paramètres déterminent entièrement
 * le résultat, qui se garde donc en cache sans limite de durée.
 *
 * Servie à la racine de l'hôte, hors du proxy (voir `proxy.ts`) : le
 * système d'exploitation la télécharge lui-même, sans cookie ni langue.
 */

import { ImageResponse } from "next/og";
import { Children, Fragment, isValidElement, type ReactNode } from "react";

import { PATHS, type IconName } from "@/features/dashboard/icons";

/*
  Les tracés d'une icône, à plat.

  La plupart des icônes du tableau de bord sont un fragment React (`<>…</>`)
  qui regroupe plusieurs formes. Le moteur de rendu de `next/og` ne sait pas
  les ouvrir à l'intérieur d'un `<svg>` : il abandonnait la requête, et le
  serveur rendait une réponse vide pour six genres sur neuf — seuls ceux
  dont l'icône tient en un tracé unique (l'étoile, l'éclair, la croix)
  s'affichaient. On déballe donc le fragment en ses enfants.
*/
function traces(icone: ReactNode): ReactNode[] {
  if (isValidElement(icone) && icone.type === Fragment) {
    return Children.toArray((icone.props as { children?: ReactNode }).children);
  }
  return [icone];
}

const LARGEUR = 720;
const HAUTEUR = 360;
const COULEUR_PAR_DEFAUT = "B4436C";

/** Tenu en phase avec `ACTIONS` dans apps/notifications/habillage.py. */
const GENRES: Record<string, { libelle: string; icone: IconName }> = {
  reservation: { libelle: "Nouvelle réservation", icone: "calendar" },
  acompte_a_verifier: { libelle: "Acompte à vérifier", icone: "wallet" },
  acompte_expire: { libelle: "Créneau libéré", icone: "clock" },
  annulation: { libelle: "Rendez-vous annulé", icone: "close" },
  avis: { libelle: "Nouvel avis", icone: "star" },
  liste_attente: { libelle: "Liste d'attente", icone: "users" },
  salon_inscrit: { libelle: "Nouveau salon", icone: "store" },
  facture: { libelle: "Facturation", icone: "receipt" },
  incident: { libelle: "Incident", icone: "bolt" },
};

function rvb(hex: string): [number, number, number] {
  return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];
}

/** Luminance relative, au sens des règles de contraste WCAG. */
function luminance([r, v, b]: [number, number, number]): number {
  const canal = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * canal(r) + 0.7152 * canal(v) + 0.0722 * canal(b);
}

/** La même teinte, assombrie : l'autre bout du dégradé. */
function assombrir([r, v, b]: [number, number, number], part: number): string {
  const f = (c: number) => Math.round(c * (1 - part));
  return `rgb(${f(r)}, ${f(v)}, ${f(b)})`;
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ genre: string }> },
) {
  const { genre } = await params;
  const modele = GENRES[genre];
  if (!modele) return new Response("Genre inconnu.", { status: 404 });

  const requete = new URL(request.url).searchParams;
  const brute = (requete.get("couleur") ?? "").replace(/^#/, "");
  const couleur = /^[0-9a-f]{6}$/i.test(brute) ? brute : COULEUR_PAR_DEFAUT;
  // Caractères de contrôle retirés : ils ne s'affichent pas, ils ne font que
  // décaler la mise en page.
  const salon = (requete.get("salon") ?? "")
    .replace(/[\u0000-\u001f\u007f]/g, "")
    .trim()
    .slice(0, 40);

  const base = rvb(couleur);
  /*
    Le texte est blanc, sauf si la couleur du salon est trop claire pour lui.

    Le titre fait 50 px en gras : c'est du « grand texte », pour lequel le
    seuil de lisibilité est 3:1. Une palette pastel — un rose poudré, un
    jaune — tomberait bien en dessous ; on passe alors à l'encre sombre.
  */
  const blancLisible = 1.05 / (luminance(base) + 0.05) >= 3;
  const encre = blancLisible ? "#ffffff" : "#17171c";
  const voile = blancLisible ? "rgba(255,255,255,0.16)" : "rgba(23,23,28,0.10)";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          position: "relative",
          padding: "0 56px",
          backgroundImage: `linear-gradient(135deg, #${couleur} 0%, ${assombrir(base, blancLisible ? 0.35 : 0.12)} 100%)`,
          color: encre,
        }}
      >
        {/* Deux disques en filigrane : de la profondeur, sans rien à lire. */}
        <div
          style={{
            // Au-dessus du titre, jamais dessous : un libellé long
            // (« Acompte à vérifier ») s'étend jusqu'au bord droit.
            position: "absolute",
            right: -130,
            top: -170,
            width: 300,
            height: 300,
            borderRadius: 9999,
            background: voile,
          }}
        />
        <div
          style={{
            position: "absolute",
            right: 120,
            bottom: -150,
            width: 260,
            height: 260,
            borderRadius: 9999,
            background: voile,
          }}
        />

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 148,
            height: 148,
            borderRadius: 40,
            background: voile,
            flexShrink: 0,
          }}
        >
          <svg
            width="84"
            height="84"
            viewBox="0 0 24 24"
            fill="none"
            stroke={encre}
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {traces(PATHS[modele.icone])}
          </svg>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            marginLeft: 40,
            maxWidth: 440,
          }}
        >
          {salon && (
            <div
              style={{
                fontSize: 24,
                letterSpacing: 2,
                textTransform: "uppercase",
                opacity: 0.85,
                marginBottom: 10,
              }}
            >
              {salon}
            </div>
          )}
          <div style={{ fontSize: 50, fontWeight: 700, lineHeight: 1.1 }}>
            {modele.libelle}
          </div>
        </div>
      </div>
    ),
    {
      width: LARGEUR,
      height: HAUTEUR,
      headers: {
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    },
  );
}
