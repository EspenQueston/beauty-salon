// Découpage du texte des assistants (features/ui/segmentsTexte.ts).
// Lancer : node --test tests/

import assert from "node:assert/strict";
import { test } from "node:test";

import { decouper, libelleLisible } from "../features/ui/segmentsTexte.ts";

test("un lien Markdown devient un lien", () => {
  assert.deepEqual(
    decouper("Réservez ici : [Réserver en ligne](https://blondrose.beauty.profitexb2b.com/reserver)."),
    [
      { type: "texte", texte: "Réservez ici : " },
      {
        type: "lien",
        texte: "Réserver en ligne",
        href: "https://blondrose.beauty.profitexb2b.com/reserver",
      },
      { type: "texte", texte: "." },
    ],
  );
});

test("un lien Markdown reste cliquable si l'assistant saute une ligne", () => {
  assert.deepEqual(
    decouper("Réservez : [reserver_en_ligne]\n(https://blondrose.beauty.profitexb2b.com/reserver)."),
    [
      { type: "texte", texte: "Réservez : " },
      {
        type: "lien",
        texte: "Reserver en ligne",
        href: "https://blondrose.beauty.profitexb2b.com/reserver",
      },
      { type: "texte", texte: "." },
    ],
  );
});

test("un nom de champ recopié comme libellé devient lisible", () => {
  const [, lien] = decouper("ce lien : [reserver_en_ligne](https://salon.example/reserver)");
  assert.equal(lien.texte, "Reserver en ligne");
  assert.equal(libelleLisible("Book online"), "Book online");
});

test("une adresse nue devient un lien, sans la ponctuation qui la suit", () => {
  assert.deepEqual(decouper("Voir https://salon.example/reserver."), [
    { type: "texte", texte: "Voir " },
    { type: "lien", texte: "https://salon.example/reserver", href: "https://salon.example/reserver" },
    { type: "texte", texte: "." },
  ]);
});

test("seuls http et https deviennent des liens", () => {
  const morceaux = decouper("[cliquez](javascript:alert(1)) et [ici](data:text/html,x)");
  assert.ok(morceaux.every((m) => m.type !== "lien"));
  assert.equal(morceaux.map((m) => m.texte).join(""), "[cliquez](javascript:alert(1)) et [ici](data:text/html,x)");
});

test("le gras est reconnu, le reste reste du texte", () => {
  assert.deepEqual(decouper("Prix : **25 000 FCFA**\nÀ bientôt"), [
    { type: "texte", texte: "Prix : " },
    { type: "gras", texte: "25 000 FCFA" },
    { type: "texte", texte: "\nÀ bientôt" },
  ]);
});

test("un texte sans rien de spécial reste intact", () => {
  assert.deepEqual(decouper("Bonjour !"), [{ type: "texte", texte: "Bonjour !" }]);
});
