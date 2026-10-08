import test from "node:test";
import assert from "node:assert/strict";
import { messageKkiapayRejete } from "../features/dashboard/kkiapayMessage.mjs";

test("un faux succès KKIAPAY provenant d’un autre site est bloqué", () => {
  const frame = { contentWindow: {} };
  assert.equal(messageKkiapayRejete({ origin: "https://evil.example", source: frame.contentWindow, data: { name: "PAYMENT_SUCCESS" } }, frame), true);
});
test("même origine, autre fenêtre : succès bloqué", () => {
  assert.equal(messageKkiapayRejete({ origin: "https://widget-v3.kkiapay.me", source: {}, data: { name: "PAYMENT_SUCCESS" } }, { contentWindow: {} }), true);
});
test("le vrai widget peut confirmer ; les URL de fenêtre arbitraires sont bloquées", () => {
  const frame = { contentWindow: {} };
  const event = { origin: "https://widget-v3.kkiapay.me", source: frame.contentWindow, data: { name: "PAYMENT_SUCCESS" } };
  assert.equal(messageKkiapayRejete(event, frame), false);
  assert.equal(messageKkiapayRejete({ ...event, data: { name: "WAVE_LINK", data: "javascript:alert(1)" } }, frame), true);
});
test("un succès sans widget est bloqué, les autres protocoles restent utilisables", () => {
  assert.equal(messageKkiapayRejete({ origin: "https://widget-v3.kkiapay.me", data: { name: "PAYMENT_SUCCESS" } }, null), true);
  assert.equal(messageKkiapayRejete({ data: { name: "another-app-event" } }, null), false);
});
