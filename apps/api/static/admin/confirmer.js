/*
 * Les confirmations de l'administration plateforme.
 *
 * Remplace le `confirm()` du navigateur — une boîte grise, titrée du nom de
 * domaine (« api.beauty.profitexb2b.com says »), sans mise en forme ni
 * possibilité de dire ce qui va se passer — par une vraie fenêtre :
 * un titre, ce qui est en jeu, et deux boutons dont un seul engage.
 *
 * Deux usages, sans aucun JavaScript dans les gabarits :
 *
 *   1. un formulaire déclare sa confirmation :
 *        <form data-confirmer="Message"
 *              data-confirmer-titre="Titre"
 *              data-confirmer-bouton="Libellé du bouton"
 *              data-confirmer-ton="ok|danger"
 *              data-confirmer-details='[["Montant","399 CNY"],["Salon","blondrose"]]'>
 *
 *   2. la liste d'un modèle : les actions en masse marquées « sensibles »
 *      (voir ACTIONS_SENSIBLES) demandent confirmation avec le nombre
 *      d'éléments cochés.
 *
 * `<dialog>` + `showModal()` : le navigateur gère le piège du focus, la
 * touche Échap et l'arrière-plan inerte. Si `<dialog>` manque (navigateur
 * très ancien), on retombe sur `confirm()` : jamais d'action sans demande.
 */
(function () {
  "use strict";

  // Actions de liste qui changent l'état d'un salon en ligne, sans page
  // intermédiaire. Les gestes « motivés » ont déjà la leur.
  var ACTIONS_SENSIBLES = {
    action_publish: { ton: "ok", titre: "Publier les mini-sites ?" },
    action_suspend: {
      ton: "danger",
      titre: "Suspendre les salons ?",
      message: "Leurs mini-sites seront mis hors ligne immédiatement. Leurs données sont conservées.",
    },
  };

  var dialogue = null;

  function element(tag, classe, texte) {
    var el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texte) el.textContent = texte;
    return el;
  }

  function construire() {
    if (dialogue) return dialogue;
    dialogue = element("dialog", "bs-confirmer");
    dialogue.setAttribute("aria-labelledby", "bs-confirmer-titre");
    dialogue.setAttribute("aria-describedby", "bs-confirmer-message");
    dialogue.innerHTML =
      '<form method="dialog" class="bs-confirmer__carte">' +
      '  <div class="bs-confirmer__icone" aria-hidden="true"></div>' +
      '  <h2 id="bs-confirmer-titre" class="bs-confirmer__titre"></h2>' +
      '  <p id="bs-confirmer-message" class="bs-confirmer__message"></p>' +
      '  <dl class="bs-confirmer__details"></dl>' +
      '  <div class="bs-confirmer__actions">' +
      '    <button type="submit" value="annuler" class="bs-confirmer__annuler">Annuler</button>' +
      '    <button type="submit" value="confirmer" class="bs-confirmer__valider"></button>' +
      "  </div>" +
      "</form>";
    // Un clic sur le voile (hors de la carte) annule, comme Échap.
    dialogue.addEventListener("click", function (event) {
      if (event.target === dialogue) dialogue.close("annuler");
    });
    document.body.appendChild(dialogue);
    return dialogue;
  }

  /**
   * Ouvre la fenêtre ; `suite` n'est appelée que sur « confirmer ».
   */
  function demander(options, suite) {
    if (typeof HTMLDialogElement === "undefined") {
      if (window.confirm(options.titre + "\n\n" + (options.message || ""))) suite();
      return;
    }
    var d = construire();
    var ton = options.ton === "danger" ? "danger" : "ok";
    d.dataset.ton = ton;
    d.querySelector(".bs-confirmer__icone").textContent = ton === "danger" ? "!" : "✓";
    d.querySelector(".bs-confirmer__titre").textContent = options.titre || "Confirmer ?";
    var message = d.querySelector(".bs-confirmer__message");
    message.textContent = options.message || "";
    message.hidden = !options.message;

    var details = d.querySelector(".bs-confirmer__details");
    details.textContent = "";
    (options.details || []).forEach(function (ligne) {
      var bloc = element("div", "bs-confirmer__ligne");
      bloc.appendChild(element("dt", "", ligne[0]));
      bloc.appendChild(element("dd", "", ligne[1]));
      details.appendChild(bloc);
    });
    details.hidden = !(options.details && options.details.length);

    var valider = d.querySelector(".bs-confirmer__valider");
    valider.textContent = options.bouton || "Confirmer";

    d.returnValue = "";
    d.onclose = function () {
      d.onclose = null;
      if (d.returnValue === "confirmer") suite();
    };
    d.showModal();
    // Le focus va sur « Annuler » : Entrée par réflexe n'engage rien.
    d.querySelector(".bs-confirmer__annuler").focus();
  }

  /*
   * Renvoie le formulaire tel qu'il serait parti, avec le bouton cliqué :
   * les actions de liste de Django exigent son nom (`index`), et
   * `form.submit()` l'oublierait.
   */
  function envoyer(form, bouton) {
    form.dataset.confirme = "1";
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit(bouton || undefined);
    } else {
      HTMLFormElement.prototype.submit.call(form);
    }
    // Après l'envoi : un bouton désactivé avant ne serait pas transmis.
    if (bouton) {
      window.setTimeout(function () {
        bouton.disabled = true;
      }, 0);
    }
  }

  function lireDetails(form) {
    try {
      return JSON.parse(form.dataset.confirmerDetails || "[]");
    } catch (e) {
      return [];
    }
  }

  // 1. Formulaires qui déclarent leur confirmation.
  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!(form instanceof HTMLFormElement) || !form.dataset.confirmer) return;
      if (form.dataset.confirme === "1") return; // déjà accepté : on laisse partir
      // Les champs obligatoires d'abord : confirmer un formulaire incomplet
      // ferait cliquer deux fois pour rien.
      if (!form.checkValidity()) return;
      event.preventDefault();
      var bouton = event.submitter || null;
      demander(
        {
          titre: form.dataset.confirmerTitre,
          message: form.dataset.confirmer,
          bouton: form.dataset.confirmerBouton,
          ton: form.dataset.confirmerTon,
          details: lireDetails(form),
        },
        function () {
          envoyer(form, bouton);
        }
      );
    },
    true
  );

  // 2. Actions en masse des listes.
  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!(form instanceof HTMLFormElement) || form.id !== "changelist-form") return;
      if (form.dataset.confirme === "1") return;
      var choix = form.querySelector('select[name="action"]');
      var regle = choix && ACTIONS_SENSIBLES[choix.value];
      if (!regle) return;
      var coches = form.querySelectorAll('input.action-select:checked').length;
      var tous = form.querySelector('input[name="select_across"]');
      if (!coches && !(tous && tous.value === "1")) return; // Django dira « aucun élément »
      event.preventDefault();
      var declencheur = event.submitter || null;
      var libelle = choix.options[choix.selectedIndex].textContent.trim();
      demander(
        {
          titre: regle.titre,
          message: regle.message || "",
          bouton: libelle,
          ton: regle.ton,
          details: [["Éléments sélectionnés", tous && tous.value === "1" ? "Tous" : String(coches)]],
        },
        function () {
          envoyer(form, declencheur);
        }
      );
    },
    true
  );
})();
