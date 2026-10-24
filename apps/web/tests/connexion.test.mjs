import assert from "node:assert/strict";
import { test } from "node:test";

import { adresseDeConnexion, modeSession } from "../features/dashboard/connexion.ts";

test("une session sans salon ouvre le changement de compte, pas un écran bloqué", () => {
  assert.equal(modeSession(null), "connexion");
  assert.equal(modeSession({ memberships: [] }), "changer_compte");
  assert.equal(modeSession({ memberships: [{ id: "salon-1" }] }), "salon");
});

test("l'adresse d'un compte sans salon n'est pas reproposée", () => {
  assert.equal(adresseDeConnexion("", "cliente@example.com", "cliente@example.com"), "");
  assert.equal(
    adresseDeConnexion("cliente@example.com", "pro@example.com", "cliente@example.com"),
    "pro@example.com",
  );
  assert.equal(adresseDeConnexion("nouveau@example.com", "ancien@example.com"), "nouveau@example.com");
});
