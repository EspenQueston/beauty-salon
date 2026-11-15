/*
 * La cloche de l'administration plateforme.
 *
 * ===========================================================================
 * Pourquoi du JavaScript écrit à la main
 * ===========================================================================
 *
 * L'administration est rendue par Django : il n'y a pas de React ici, pas
 * d'étape de compilation, et il ne doit pas y en avoir. Ajouter une chaîne de
 * construction pour trois cents lignes reviendrait à rendre l'administration
 * indépendante de Django — c'est-à-dire à créer un second frontend à
 * maintenir, pour une cloche.
 *
 * Ce fichier est donc servi tel quel, sans dépendance. Il parle à la même API
 * que le tableau de bord, et il est sur la même origine : le cookie de
 * session suffit, il n'y a ni CORS ni jeton à gérer.
 */

(function () {
  "use strict";

  var RAFRAICHISSEMENT = 30000;
  var API = "/api/v1";
  var CLE_OPTIN = "beauty-salon.push-admin";

  var racine = document.getElementById("cloche-plateforme");
  if (!racine) return;

  var etat = { ouvert: false, boite: null, push: null, occupe: false };
  var minuteur = null;

  // ---------------------------------------------------------------------
  // Réseau
  // ---------------------------------------------------------------------

  function cookie(nom) {
    var trouve = document.cookie.match(new RegExp("(^| )" + nom + "=([^;]+)"));
    return trouve ? decodeURIComponent(trouve[2]) : "";
  }

  function appel(chemin, options) {
    options = options || {};
    var entetes = { "Content-Type": "application/json" };
    if (options.method && options.method !== "GET") {
      entetes["X-CSRFToken"] = cookie("csrftoken");
    }
    return fetch(API + chemin, {
      method: options.method || "GET",
      headers: entetes,
      body: options.body,
      // Même origine que l'administration : le cookie de session part seul.
      credentials: "same-origin",
    }).then(function (reponse) {
      if (!reponse.ok) throw new Error(String(reponse.status));
      return reponse.status === 204 ? null : reponse.json();
    });
  }

  // ---------------------------------------------------------------------
  // Rendu
  // ---------------------------------------------------------------------

  var GENRES = {
    salon_inscrit: "✦",
    facture: "▤",
    incident: "!",
    reservation: "◷",
  };

  function depuis(iso) {
    var quand = new Date(iso).getTime();
    if (isNaN(quand)) return "";
    var minutes = Math.max(0, Math.round((Date.now() - quand) / 60000));
    if (minutes < 1) return "à l'instant";
    if (minutes < 60) return "il y a " + minutes + " min";
    var heures = Math.round(minutes / 60);
    if (heures < 24) return "il y a " + heures + " h";
    if (heures < 48) return "hier";
    return new Date(iso).toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "2-digit",
    });
  }

  /** Échappe avant toute insertion : ces textes viennent de la base. */
  function texte(valeur) {
    var noeud = document.createElement("span");
    noeud.textContent = valeur == null ? "" : String(valeur);
    return noeud.innerHTML;
  }

  function peindre() {
    var boite = etat.boite;
    var nonLues = boite ? boite.non_lues : 0;

    var html =
      '<button type="button" class="cloche-bouton" aria-haspopup="dialog"' +
      ' aria-expanded="' +
      (etat.ouvert ? "true" : "false") +
      '" aria-label="' +
      (nonLues > 0 ? "Notifications, " + nonLues + " non lues" : "Notifications") +
      '">' +
      '<svg viewBox="0 0 24 24" aria-hidden="true" width="18" height="18">' +
      '<path fill="currentColor" d="M12 2a1.4 1.4 0 0 1 1.4 1.4v.7a6 6 0 0 1 4.6 5.8v3.4l1.6 2.6a1 1 0 0 1-.85 1.5H5.25a1 1 0 0 1-.85-1.5L6 13.3V9.9a6 6 0 0 1 4.6-5.8v-.7A1.4 1.4 0 0 1 12 2Zm0 20a2.6 2.6 0 0 1-2.5-1.9h5A2.6 2.6 0 0 1 12 22Z"/>' +
      "</svg>" +
      (nonLues > 0
        ? '<span class="cloche-pastille">' +
          (nonLues > 9 ? "9+" : nonLues) +
          "</span>"
        : "") +
      "</button>";

    if (etat.ouvert) html += panneau(boite);

    racine.innerHTML = html;
    brancher();
  }

  function panneau(boite) {
    var lignes = boite ? boite.resultats : [];
    var corps;

    if (!lignes.length) {
      corps =
        '<p class="cloche-vide">Rien à signaler. Les inscriptions de salons' +
        " et les incidents de facturation arriveront ici.</p>";
    } else {
      corps =
        '<ul class="cloche-liste">' +
        lignes
          .map(function (ligne) {
            return (
              '<li class="cloche-item' +
              (ligne.lue ? "" : " cloche-item--neuve") +
              '" data-id="' +
              texte(ligne.id) +
              '" data-lien="' +
              texte(ligne.lien) +
              '">' +
              '<span class="cloche-glyphe" aria-hidden="true">' +
              (GENRES[ligne.genre] || "•") +
              "</span>" +
              '<span class="cloche-corps">' +
              '<span class="cloche-titre">' +
              texte(ligne.titre) +
              "</span>" +
              (ligne.salon
                ? '<span class="cloche-salon">' + texte(ligne.salon) + "</span>"
                : "") +
              (ligne.corps
                ? '<span class="cloche-detail">' + texte(ligne.corps) + "</span>"
                : "") +
              "</span>" +
              '<span class="cloche-quand">' +
              texte(depuis(ligne.created_at)) +
              "</span>" +
              "</li>"
            );
          })
          .join("") +
        "</ul>";
    }

    return (
      '<div class="cloche-panneau" role="dialog" aria-label="Notifications">' +
      '<div class="cloche-entete">' +
      "<strong>Notifications</strong>" +
      '<button type="button" class="cloche-tout"' +
      (boite && boite.non_lues ? "" : " disabled") +
      ">Tout marquer lu</button>" +
      "</div>" +
      corps +
      reglagePush(boite) +
      "</div>"
    );
  }

  function reglagePush(boite) {
    if (!boite || !boite.push_actif || !etat.push) return "";

    var messages = {
      pret: ["Notifications activées sur cet appareil.", "Désactiver"],
      possible: ["Être prévenu sur cet appareil, même hors du navigateur.", "Activer"],
      refuse: [
        "Les notifications sont bloquées pour ce site. Rouvrez-les dans les réglages du navigateur.",
        null,
      ],
      incompatible: ["Ce navigateur ne gère pas les notifications.", null],
      desactive: ["", null],
    };
    var message = messages[etat.push];
    if (!message || !message[0]) return "";

    return (
      '<div class="cloche-push">' +
      "<span>" +
      texte(message[0]) +
      "</span>" +
      (message[1]
        ? '<button type="button" class="cloche-push-action"' +
          (etat.occupe ? " disabled" : "") +
          ">" +
          (etat.occupe ? "…" : texte(message[1])) +
          "</button>"
        : "") +
      "</div>"
    );
  }

  // ---------------------------------------------------------------------
  // Interactions
  // ---------------------------------------------------------------------

  function brancher() {
    var bouton = racine.querySelector(".cloche-bouton");
    if (bouton) {
      bouton.addEventListener("click", function (evenement) {
        evenement.stopPropagation();
        etat.ouvert = !etat.ouvert;
        peindre();
        if (etat.ouvert) lireEtatPush();
      });
    }

    var tout = racine.querySelector(".cloche-tout");
    if (tout) {
      tout.addEventListener("click", function () {
        appel("/plateforme/notifications", {
          method: "POST",
          body: JSON.stringify({ toutes: true }),
        })
          .then(charger)
          .catch(function () {});
      });
    }

    Array.prototype.forEach.call(
      racine.querySelectorAll(".cloche-item"),
      function (item) {
        item.addEventListener("click", function () {
          var id = item.getAttribute("data-id");
          var lien = item.getAttribute("data-lien");
          appel("/plateforme/notifications", {
            method: "POST",
            body: JSON.stringify({ ids: [id] }),
          }).catch(function () {});
          if (lien) window.location.href = lien;
          else {
            etat.ouvert = false;
            charger();
          }
        });
      },
    );

    var action = racine.querySelector(".cloche-push-action");
    if (action) action.addEventListener("click", basculerPush);
  }

  document.addEventListener("click", function (evenement) {
    if (!etat.ouvert) return;
    if (racine.contains(evenement.target)) return;
    etat.ouvert = false;
    peindre();
  });

  document.addEventListener("keydown", function (evenement) {
    if (evenement.key !== "Escape" || !etat.ouvert) return;
    etat.ouvert = false;
    peindre();
  });

  // ---------------------------------------------------------------------
  // Push
  // ---------------------------------------------------------------------

  function versOctets(base64url) {
    var bourrage = new Array((4 - (base64url.length % 4)) % 4 + 1).join("=");
    var base64 = (base64url + bourrage).replace(/-/g, "+").replace(/_/g, "/");
    var brut = atob(base64);
    var octets = new Uint8Array(brut.length);
    for (var index = 0; index < brut.length; index += 1) {
      octets[index] = brut.charCodeAt(index);
    }
    return octets;
  }

  function nomAppareil() {
    var ua = navigator.userAgent;
    var systeme = /Android/.test(ua)
      ? "Android"
      : /iPhone|iPad/.test(ua)
        ? "iPhone"
        : /Windows/.test(ua)
          ? "Windows"
          : /Mac OS X/.test(ua)
            ? "Mac"
            : "";
    var navigateur = /Edg\//.test(ua)
      ? "Edge"
      : /OPR\//.test(ua)
        ? "Opera"
        : /Chrome\//.test(ua)
          ? "Chrome"
          : /Firefox\//.test(ua)
            ? "Firefox"
            : /Safari\//.test(ua)
              ? "Safari"
              : "Navigateur";
    return systeme ? navigateur + " sur " + systeme : navigateur;
  }

  function lireEtatPush() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      etat.push = "incompatible";
      peindre();
      return;
    }

    appel("/push")
      .then(function (serveur) {
        if (!serveur.actif) {
          etat.push = "desactive";
          return peindre();
        }
        if (Notification.permission === "denied") {
          etat.push = "refuse";
          return peindre();
        }
        return navigator.serviceWorker
          .getRegistration("/")
          .then(function (enregistrement) {
            return enregistrement
              ? enregistrement.pushManager.getSubscription()
              : null;
          })
          .then(function (abonnement) {
            var connu =
              abonnement &&
              serveur.appareils.some(function (appareil) {
                return appareil.endpoint === abonnement.endpoint;
              });
            etat.push = connu ? "pret" : "possible";
            peindre();
          });
      })
      .catch(function () {
        etat.push = "incompatible";
        peindre();
      });
  }

  function basculerPush() {
    etat.occupe = true;
    peindre();

    var promesse = etat.push === "pret" ? desactiver() : activer();
    promesse
      .catch(function () {
        etat.push = "incompatible";
      })
      .then(function () {
        etat.occupe = false;
        peindre();
      });
  }

  function activer() {
    return Notification.requestPermission().then(function (permission) {
      if (permission !== "granted") {
        etat.push = permission === "denied" ? "refuse" : "possible";
        return;
      }
      try {
        localStorage.setItem(CLE_OPTIN, "1");
      } catch (erreur) {
        // Stockage refusé : sans conséquence, l'abonnement tient quand même.
      }

      return navigator.serviceWorker
        .register("/sw-admin.js", { scope: "/" })
        .then(function () {
          return navigator.serviceWorker.ready;
        })
        .then(function (enregistrement) {
          return appel("/push").then(function (serveur) {
            var cle = versOctets(serveur.cle);
            return enregistrement.pushManager
              .getSubscription()
              .then(function (ancien) {
                // Une clé VAPID régénérée rend l'ancien abonnement inutile :
                // `subscribe` échouerait, et l'appareil ne recevrait plus
                // jamais rien sans que personne ne le sache.
                return ancien ? ancien.unsubscribe().then(function () {}) : null;
              })
              .then(function () {
                return enregistrement.pushManager.subscribe({
                  userVisibleOnly: true,
                  applicationServerKey: cle,
                });
              });
          });
        })
        .then(function (abonnement) {
          var brut = abonnement.toJSON();
          return appel("/push", {
            method: "POST",
            body: JSON.stringify({
              endpoint: brut.endpoint,
              cle_p256dh: brut.keys.p256dh,
              cle_auth: brut.keys.auth,
              appareil: nomAppareil(),
              portee: "plateforme",
            }),
          });
        })
        .then(function () {
          etat.push = "pret";
        });
    });
  }

  function desactiver() {
    try {
      localStorage.removeItem(CLE_OPTIN);
    } catch (erreur) {
      // Sans conséquence.
    }
    return navigator.serviceWorker
      .getRegistration("/")
      .then(function (enregistrement) {
        return enregistrement
          ? enregistrement.pushManager.getSubscription()
          : null;
      })
      .then(function (abonnement) {
        if (!abonnement) {
          etat.push = "possible";
          return;
        }
        // Le serveur d'abord : l'inverse laisserait une ligne active en base
        // pour une boîte que plus personne ne relève.
        return appel("/push", {
          method: "DELETE",
          body: JSON.stringify({ endpoint: abonnement.endpoint }),
        })
          .catch(function () {})
          .then(function () {
            return abonnement.unsubscribe();
          })
          .then(function () {
            etat.push = "possible";
          });
      });
  }

  // ---------------------------------------------------------------------
  // Boucle de fraîcheur
  // ---------------------------------------------------------------------

  function charger() {
    return appel("/plateforme/notifications")
      .then(function (boite) {
        etat.boite = boite;
        peindre();
      })
      .catch(function () {
        // Session expirée, réseau coupé : on garde le dernier état affiché
        // plutôt que de vider la cloche, ce qui ferait croire à un calme
        // qui n'existe pas.
      });
  }

  function battre() {
    if (minuteur) clearInterval(minuteur);
    // Un onglet d'administration reste ouvert des journées entières. Sans ce
    // test, il interrogerait le serveur trois mille fois pour personne.
    if (document.hidden) return;
    minuteur = setInterval(charger, RAFRAICHISSEMENT);
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) charger();
    battre();
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", function (evenement) {
      if (evenement.data && evenement.data.type === "beauty-salon:notification") {
        charger();
      }
    });
  }

  peindre();
  charger();
  battre();
})();
