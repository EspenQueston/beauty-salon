// Règles du formulaire de prestation (features/dashboard/prestation.ts).
// Lancer : node --test tests/   (Node 24 lit le TypeScript sans outil)

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  corpsPrestation,
  estModifiee,
  premierChampEnErreur,
  validerPrestation,
} from "../features/dashboard/prestation.ts";

const box = {
  id: "s1",
  category: "c1",
  name: "Box braids",
  description: "Pose complète",
  duration_minutes: 240,
  price_kind: "fixed",
  price_amount: "5000.04",
  requires_deposit: true,
  location_mode: "salon",
  active: true,
  image: null,
};

test("une prestation complète est valide", () => {
  assert.deepEqual(validerPrestation(box), {});
});

test("nom vide, durée trop courte, prix négatif : trois erreurs, dans l'ordre de l'écran", () => {
  const erreurs = validerPrestation({ ...box, name: "   ", duration_minutes: 3, price_amount: "-1" });
  assert.ok(erreurs.name);
  assert.ok(erreurs.duration_minutes);
  assert.ok(erreurs.price_amount);
  assert.equal(premierChampEnErreur(erreurs), "name");
});

test("une durée non entière ou démesurée est refusée", () => {
  assert.ok(validerPrestation({ ...box, duration_minutes: 12.5 }).duration_minutes);
  assert.ok(validerPrestation({ ...box, duration_minutes: 2000 }).duration_minutes);
  assert.ok(validerPrestation({ ...box, duration_minutes: "" }).duration_minutes);
});

test("un nom de plus de 150 caractères est refusé", () => {
  assert.ok(validerPrestation({ ...box, name: "x".repeat(151) }).name);
  assert.equal(validerPrestation({ ...box, name: "x".repeat(150) }).name, undefined);
});

test("sur devis, le prix n'est pas demandé et part à 0", () => {
  const devis = { ...box, price_kind: "quote", price_amount: "" };
  assert.deepEqual(validerPrestation(devis), {});
  assert.equal(corpsPrestation(devis).price_amount, "0");
});

test("le corps envoyé est normalisé", () => {
  const corps = corpsPrestation({ ...box, name: "  Box braids  ", duration_minutes: "240" });
  assert.equal(corps.name, "Box braids");
  assert.equal(corps.duration_minutes, 240);
  assert.equal("id" in corps, false); // l'identifiant est dans l'adresse, jamais dans le corps
});

test("rouvrir sans rien changer n'est pas une modification", () => {
  assert.equal(estModifiee(box, { ...box }), false);
  // « 240 » et 240, « 5000.040 » et « 5000.04 » : même valeur envoyée.
  assert.equal(estModifiee(box, { ...box, duration_minutes: "240", price_amount: "5000.040" }), false);
});

test("changer un champ est une modification ; le remettre à l'identique ne l'est plus", () => {
  assert.equal(estModifiee(box, { ...box, name: "Box braids XXL" }), true);
  assert.equal(estModifiee(box, { ...box, requires_deposit: false }), true);
  assert.equal(estModifiee(box, { ...box, name: "Box braids" }), false);
});
