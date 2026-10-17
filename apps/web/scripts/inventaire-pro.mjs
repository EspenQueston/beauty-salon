#!/usr/bin/env node
/**
 * Ce qu'il reste à traduire dans l'espace professionnel.
 *
 * Usage :  node scripts/inventaire-pro.mjs [--detail fichier.tsx]
 *
 * Le mini-site et le site de la plateforme sont bilingues ; l'espace pro est
 * traduit écran par écran. Ce script dit, pour chaque fichier, combien de
 * textes visibles sont encore écrits en dur — c'est-à-dire ne passent pas
 * par `t(…)`. Il lit le code avec le compilateur TypeScript, pas avec des
 * expressions régulières : un commentaire ou un nom de classe Tailwind n'est
 * jamais compté.
 *
 * Ce qui compte comme « texte visible » :
 *   - le texte entre deux balises JSX ;
 *   - les attributs lus par une personne : `aria-label`, `title`,
 *     `placeholder`, `alt`, `label`, `description`, `hint`, `detail`… ;
 *   - les chaînes passées à `toast.*`, et celles qui contiennent une espace
 *     ou une lettre accentuée hors des attributs techniques.
 *
 * C'est une estimation honnête, pas une preuve : un écran à zéro peut
 * encore contenir un texte construit autrement. Le juge reste l'écran.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";

const RACINE = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const DOSSIERS = ["features/dashboard"];

// Attributs dont la valeur n'est jamais lue par une personne.
const TECHNIQUES = new Set([
  "className", "href", "src", "type", "key", "id", "role", "name", "htmlFor",
  "method", "rel", "target", "inputMode", "autoComplete", "fetchPriority",
  "loading", "decoding", "sizes", "srcSet", "tone", "icon", "icone", "variant",
  "fonction", "mode", "as", "lang", "dir", "value", "defaultValue", "pattern",
  "accept", "capture", "enterKeyHint", "spellCheck", "form", "media", "style",
  // SVG : des coordonnées, pas des mots.
  "d", "viewBox", "points", "transform", "fill", "stroke", "strokeWidth",
  "strokeLinecap", "strokeLinejoin", "cx", "cy", "r", "x", "y", "width", "height",
]);
// Ceux qui le sont toujours.
const LUS = new Set([
  "aria-label", "title", "placeholder", "alt", "label", "description", "hint",
  "detail", "titre", "sousTitre", "texte", "message", "aria-description",
]);

const lettres = /\p{L}/u;
const accent = /[àâäçéèêëîïôöùûüÿœæ]/i;
const classes = /^[a-z0-9\-:[\]/.\s_#%()=,>!&*+'@~|]*$/;

// Des jetons techniques, jamais lus : méthodes HTTP, noms de touches.
const JETONS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE", "Escape", "Enter", "Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Backspace"]);

function texteHumain(valeur) {
  const v = valeur.trim();
  if (JETONS.has(v)) return false;
  if (v.length < 2 || !lettres.test(v)) return false;
  if (accent.test(v)) return true;
  if (classes.test(v)) return false; // classes Tailwind, chemins, clés
  return /\s/.test(v) || /^[A-ZÀ-Ý]/.test(v);
}

function attributDe(noeud) {
  let p = noeud.parent;
  while (p && !ts.isJsxAttribute(p)) {
    if (ts.isJsxElement(p) || ts.isJsxSelfClosingElement(p) || ts.isBlock(p)) return null;
    p = p.parent;
  }
  return p ? p.name.getText() : null;
}

function dansAppelDeTraduction(noeud) {
  let p = noeud.parent;
  while (p) {
    if (ts.isCallExpression(p)) {
      const nom = p.expression.getText();
      if (/^(t|tt|c|g|m|f|film|t\.rich|t\.raw|t\.markup)$/.test(nom)) return true;
    }
    if (ts.isBlock(p) || ts.isSourceFile(p)) return false;
    p = p.parent;
  }
  return false;
}

function dansImportOuType(noeud) {
  let p = noeud.parent;
  while (p) {
    if (
      ts.isImportDeclaration(p) || ts.isExportDeclaration(p) ||
      ts.isLiteralTypeNode(p) || ts.isTypeAliasDeclaration(p) ||
      ts.isInterfaceDeclaration(p)
    ) return true;
    p = p.parent;
  }
  return false;
}

function inventaire(fichier) {
  const source = ts.createSourceFile(
    fichier, readFileSync(fichier, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX,
  );
  const trouves = [];
  const visiter = (noeud) => {
    if (ts.isJsxText(noeud)) {
      const v = noeud.getText().replace(/\s+/g, " ").trim();
      if (v && lettres.test(v) && !JETONS.has(v)) trouves.push(v);
    } else if (ts.isStringLiteral(noeud) || ts.isNoSubstitutionTemplateLiteral(noeud)) {
      if (!dansImportOuType(noeud) && !dansAppelDeTraduction(noeud)) {
        const attribut = attributDe(noeud);
        const v = noeud.text;
        if (attribut && TECHNIQUES.has(attribut)) {
          // jamais lu
        } else if ((attribut && LUS.has(attribut) && lettres.test(v) && !JETONS.has(v)) || texteHumain(v)) {
          trouves.push(v.replace(/\s+/g, " ").trim());
        }
      }
    } else if (ts.isTemplateExpression(noeud)) {
      const v = noeud.head.text + noeud.templateSpans.map((s) => s.literal.text).join("…");
      if (!dansAppelDeTraduction(noeud) && texteHumain(v) && !attributDe(noeud)?.match(/className/)) {
        trouves.push(v.replace(/\s+/g, " ").trim());
      }
    }
    ts.forEachChild(noeud, visiter);
  };
  visiter(source);
  return trouves;
}

const detail = process.argv.includes("--detail")
  ? process.argv[process.argv.indexOf("--detail") + 1]
  : null;

const lignes = [];
for (const dossier of DOSSIERS) {
  for (const nom of readdirSync(join(RACINE, dossier))) {
    if (!/\.(tsx|ts)$/.test(nom)) continue;
    const chemin = join(RACINE, dossier, nom);
    const textes = inventaire(chemin);
    lignes.push({ fichier: relative(RACINE, chemin).replaceAll("\\", "/"), n: textes.length, textes });
  }
}

if (detail) {
  const ligne = lignes.find((l) => l.fichier.endsWith(detail));
  if (!ligne) {
    console.error(`Aucun fichier ne finit par « ${detail} ».`);
    process.exit(1);
  }
  for (const texte of ligne.textes) console.log(`  · ${texte}`);
  console.log(`\n${ligne.n} texte(s) en dur dans ${ligne.fichier}`);
} else {
  lignes.sort((a, b) => b.n - a.n);
  const total = lignes.reduce((s, l) => s + l.n, 0);
  const faits = lignes.filter((l) => l.n === 0).length;
  for (const l of lignes) {
    console.log(`${String(l.n).padStart(5)}  ${l.n === 0 ? "✓" : " "} ${l.fichier}`);
  }
  console.log(`\n${total} texte(s) en dur · ${faits}/${lignes.length} fichier(s) sans texte en dur`);
}
