# Mini Salon — parrainage, KKIAPAY et Finances

Livraison du 9 octobre 2026. Les migrations ont été appliquées à la base locale. Aucun paiement KKIAPAY marchand réel n’a été réalisé ; l’intégration reste désactivée jusqu’à configuration et validation marchandes.

## Architecture réutilisée

- Réservations : service `create_booking`, transitions de statut réelles, acomptes et instantanés de prix existants.
- Abonnements : demandes de paiement, approbation atomique, factures et périodes calendaires existantes. Les paiements anticipés conservent les règles de renouvellement / conversion Standard–Pro du projet.
- Isolation : `TenantOwnedModel`, contexte salon et politiques PostgreSQL RLS pour le Cas A ; filtres explicites dans les APIs des données plateforme du Cas B et de KKIAPAY.
- Interfaces : page Parrainage existante, espace client FR/EN, réservation, abonnement et composants du dashboard.

## Règles implémentées

### Cas A : client → client, dans un salon

Un client vérifié partage un code propre au salon. Un compte déjà inscrit peut être filleul s’il n’a jamais réservé dans ce salon. Toute réservation antérieure, même annulée, exclut l’éligibilité. L’identité est vérifiée par adresse e-mail, compte et fiche cliente ; l’auto-parrainage est refusé. L’IP partagée n’est pas une preuve de fraude.

L’attribution est enregistrée lors de la création de la première réservation. Elle ne peut pas être ajoutée rétroactivement. La transition réelle vers `confirmed` débloque une seule récompense. Une réservation demandée ou en attente d’acompte ne suffit pas.

Le salon configure : activation, taux entre 10 et 100 %, validité en jours et montant maximal de réduction par réservation dans sa devise. Une configuration incomplète reste inactive. Les règles validées d’éligibilité et d’annulation sont contrôlées côté serveur.

Formule : `(prestation + options − promotions) × taux`, arrondi HALF_UP selon la devise, puis limité au plafond et à l’assiette restante. Produits et déplacement sont exclus du pourcentage. Le total et l’acompte sont recalculés. Un acompte devenu nul ne bloque pas la réservation en attente de paiement. Le projet n’a actuellement pas de moteur promotionnel : la ligne Promotions vaut réellement zéro ; aucun avantage promotionnel fictif n’est ajouté.

Une seule récompense est appliquée automatiquement à la prochaine réservation du parrain dans le même salon. Les conditions accordées sont figées. Verrous et contraintes empêchent les doubles attributions et consommations ; un test utilise deux créations simultanées de rendez-vous.

États : en attente, disponible, réservée, utilisée, annulée, expirée et suspendue pour audit. La confirmation de la réservation déclenchante suffit, sans paiement ni prestation réalisée supplémentaire. Après confirmation, une annulation de cette réservation conserve la récompense. Une réservation utilisant la réduction, annulée par le parrain, restitue le droit s’il est encore valable. Les événements d’origine restent enregistrés. Un rendez-vous annulé dont la réduction a été restituée ne peut pas être reconfirmé directement avec l’ancien prix réduit.

### Cas B : salon / client → nouveau salon

Un seul parrain, fixé à l’inscription. Un parrainage valide ouvre un essai total de **30 jours**, avec dates conservées, au lieu de 14 ; les salons existants ne sont pas prolongés rétroactivement.

Le premier paiement approuvé d’un abonnement Standard ou Pro, mensuel ou annuel, crée une récompense unique de **10 %** pour un salon parrain. Une preuve envoyée, une intention ou un succès frontend ne suffisent pas. Une publication et une validation manuelle du parrainage ne remplacent pas le paiement.

Paramètres retenus après délégation de l’utilisateur, modifiables dans l’administration plateforme :

| Paramètre | Valeur |
| --- | --- |
| Cooling period | Moitié de la période d’abonnement accordée par le premier paiement |
| Validité | 90 jours à compter de la disponibilité effective |
| Remises par échéance | Une seule |
| Réservation pendant un paiement | 24 heures |
| Maximum par parrain | 100 récompenses, plafond global configurable |
| Remboursement / annulation pendant le cooling | Récompense annulée |
| Contestation pendant le cooling | Disponibilité suspendue jusqu’à résolution |
| Remboursement / contestation après disponibilité | Récompense conservée |

Ces valeurs sont des choix de configuration pour cette plateforme, sans affirmation qu’elles constituent un standard universel.

La tâche planifiée s’exécute toutes les dix minutes : cooling, expirations et paiements abandonnés. Les dates sont aussi vérifiées lors de l’utilisation et de l’approbation. Une demande dont la réservation de remise a expiré ne peut pas être approuvée tardivement ; la tâche la refuse et libère le droit non expiré.

L’administration peut **constater** un remboursement, une annulation, une contestation ou sa résolution, avec permission de vérification et motif obligatoire. Ce geste n’initie aucun transfert, ne réécrit pas une facture payée et laisse une trace. Les remboursements réellement exécutés chez le fournisseur doivent être constatés par un administrateur autorisé.

Les droits historiques sont conservés et utilisés individuellement. Un filleul déjà récompensé sous l’ancien programme ne crée pas une seconde récompense au passage au nouveau programme. Aucune récompense d’abonnement ou en espèces n’est inventée pour un client qui parraine un salon ; ses invitations et événements restent consultables.

## KKIAPAY : périmètre et activation

**Abonnements uniquement**, fonds encaissés par le compte de la plateforme. Aucun paiement de réservation ni reversement salon n’est ajouté.

Le widget utilise le SDK React. La vérification privée suit la requête du SDK Python référencé par la [documentation KKIAPAY](https://docs.kkiapay.me/v1/plugin-et-sdk/admin-sdks-server-side/python-admin-sdk), avec `httpx` et un délai de 15 secondes. Le paquet Python actuel impose une ancienne version de pytest incompatible avec le projet ; il n’est pas installé.

Le serveur vérifie transaction, succès, montant, devise XOF, environnement et association à l’intention locale. La liaison `partnerId` doit venir de la réponse privée ou d’un webhook authentifié. Une réponse frontend seule ne suffit jamais. Si la réponse privée ne contient pas cette liaison, la confirmation attend le webhook authentifié.

Seul **XOF** est accepté ; XAF n’est pas assimilé à XOF. Les six pays pris en charge sont **autorisés par défaut** : BJ (Bénin), BF (Burkina Faso), CI (Côte d’Ivoire), TG (Togo), SN (Sénégal) et NE (Niger). Le [site officiel KKIAPAY](https://kkiapay.me/) annonce ces six pays (vérifié le 9 octobre 2026). Le Burkina Faso utilise XOF et Africa/Ouagadougou à l’inscription. Le pays d’encaissement doit être celui du salon. Les autres moyens de paiement sont conservés.

Configurer dans l’environnement serveur, sans copier les secrets dans le frontend :

- `KKIAPAY_ENABLED` : interrupteur, désactivé par défaut.
- `KKIAPAY_SANDBOX` : environnement courant. Le sandbox ne peut pas ouvrir d’abonnement quand `DEBUG=False`.
- `KKIAPAY_ALLOWED_COUNTRIES` : `BJ,BF,CI,TG,SN,NE` par défaut, soit tous les pays disponibles. L’interrupteur `KKIAPAY_ENABLED` contrôle séparément l’ouverture des paiements.
- `KKIAPAY_TEST_PUBLIC_KEY`, `KKIAPAY_TEST_PRIVATE_KEY`, `KKIAPAY_TEST_SECRET_KEY`, `KKIAPAY_TEST_WEBHOOK_SECRET`.
- Les quatre variables correspondantes `KKIAPAY_LIVE_*`, séparées des clés de test.

Dans l’administration : configurer les prix XOF de chaque offre et un moyen de paiement KKIAPAY pour chaque pays autorisé. Le compte marchand créditeur est celui associé aux clés serveur de la plateforme.

Webhooks HTTPS : `/api/v1/webhooks/kkiapay/test` et `/api/v1/webhooks/kkiapay/live`. Authentification par l’en-tête documenté `x-kkiapay-secret`. Une confirmation répétée retrouve le paiement existant ; une même transaction ne peut pas payer deux intentions. Un échec arrivé avant un succès fiable ne rend pas le paiement irréversiblement refusé. Une intention expirée nécessite une revue par le support si des fonds ont effectivement été reçus tardivement.

**État réel :** intégration implémentée et testée avec fournisseur simulé, désactivée par défaut. Aucun parcours marchand réel n’a été certifié. Il reste à fournir/configurer les accès, enregistrer le webhook et vérifier un paiement sandbox complet, puis l’encaissement live du compte plateforme avant activation.

## Finances et données préservées

La section financière s’appelle Finances ; l’URL `/dashboard/comptes` reste valide. Profil, connexion, sécurité et groupe général Compte conservent leurs noms. Les références de l’agenda sont corrigées.

Formulaire, bouton, validation de saisie et endpoints CRUD des transactions manuelles sont retirés. L’ancienne API refuse POST, PATCH, PUT et DELETE. Rapports, export Excel, transactions automatiques et anciennes écritures manuelles restent consultables. L’administration financière était déjà en lecture seule et le reste.

Les migrations ne suppriment aucune réservation, facture, demande de paiement ou écriture historique. Les nouveaux liens d’audit ne bloquent pas la suppression autorisée d’un compte ou salon : les références correspondantes peuvent devenir nulles. Seul le salon temporaire et les deux comptes créés pour la vérification visuelle ont été supprimés.

## Audit de sécurité et corrections

| Constat | Correction |
| --- | --- |
| SDK widget : messages sans validation d’origine / fenêtre, ouverture arbitraire de lien | Filtre installé avant le chargement du SDK, origine et iframe vérifiées ; événements WAVE_LINK bloqués ; tests de messages falsifiés |
| Dépendances Next.js et serialize-javascript vulnérables | Next.js / eslint-config-next 16.3.8, override serialize-javascript 7.0.5 ; audit des dépendances de production à zéro alerte |
| CSP ne permettant pas le widget | Autorisation iframe limitée à `https://widget-v3.kkiapay.me` |
| Remise bloquée après abandon | Date de réservation figée, tâche idempotente et refus des approbations tardives |
| Lecture de tâche filtrée par RLS sans contexte | Index inter-salons lu par l’alias admin ; traitement de chaque paiement dans son contexte salon |
| Ancien rendez-vous réduit réutilisable après restitution | Modification du prix / bénéficiaire et reconfirmation directe refusées ; suppression remplacée par annulation conservant la trace |
| Statut en mémoire obsolète lors d’une modification de note | Transitions sérialisées ; récompenses ignorées si le champ statut n’est pas réellement écrit |
| Liens PROTECT pouvant casser la suppression de compte / salon | Références d’audit nullable SET_NULL ; tests de suppression conservés |
| Anciennes récompenses pouvant générer un second avantage | Détection des droits historiques avant création Cas B |
| Prix nul encore en attente d’acompte | Acompte recalculé et retour à l’état demandé si aucun acompte n’est dû |

Limite résiduelle : l’audit de toutes les dépendances signale `braces` dans la chaîne **de développement ESLint**, avec cinq alertes transitives pour la même vulnérabilité. L’[avis officiel](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) ne propose pas de version corrigée. Cette chaîne ne figure pas dans l’audit des dépendances de production ; ne pas faire traiter des motifs glob provenant de sources non fiables par ces outils de développement. Aucun correctif fournisseur inexistant n’est annoncé.

## Fichiers principaux et migrations

- `apps/api/apps/parrainage/` : modèles, règles A/B, APIs, administration, tâches et journal.
- `apps/api/apps/billing/{kkiapay,views_kkiapay,encaissements,admin_kkiapay}.py` et services : paiement intégré et constats autorisés.
- `apps/api/apps/scheduling/{signals,models,serializers,views,views_public}.py`, service booking : attribution, prix et transitions.
- `apps/api/apps/accounts/services.py`, tenants/models.py : essai et pays/devises.
- `apps/api/apps/finance/views.py`, common/viewsets.py : lecture seule.
- `apps/api/config/{api_urls,settings/base,settings/test}.py` et template de décision de paiement.
- Frontend : `ParrainageClients`, `Parrainage`, `ParrainageCliente`, `KkiapayButton`, `kkiapayMessage`, `Billing`, `BookingFlow`, `Finances`, navigation, Agenda, formulaire d’inscription, traductions FR/EN, format/types, CSP et dépendances.
- Tests : `test_parrainage_v2.py`, adaptations `test_parrainage.py`, `test_finance.py`, test web `kkiapay.test.mjs`.

Migrations : tenants **0005–0006**, scheduling **0017**, billing **0013–0015**, parrainage **0002–0005**. La migration parrainage 0003 active les trois politiques RLS et initialise la politique B validée. `makemigrations --check --dry-run` ne signale aucun changement manquant.

## Vérifications

Les contrôles visuels locaux à **375 et 1365 pixels**, sur Parrainage, Finances et l’espace client, n’ont détecté aucun débordement horizontal ni erreur JavaScript. Les captures sont dans `tmp/mini-salon-*.png`. La vérification navigateur porte sur ces écrans locaux, avec comptes temporaires, pas sur un paiement KKIAPAY réel.

Résultats réellement obtenus :

- Suite backend complète : **1246 tests réussis**, en 299,10 secondes, sans avertissement.
- Après les derniers ajustements de prix et d’acompte : **34 tests Cas A/B et KKIAPAY réussis**, en 31,65 secondes.
- Dernier contrôle du webhook, succès répété et secret non ASCII : **1 test réussi**.
- Tests ciblés incluant les suppressions définitives : **47 tests réussis**.
- Tests web : **21 réussis**, dont quatre sur le filtrage des messages KKIAPAY.
- TypeScript, ESLint, Ruff, vérification Django et cohérence des migrations : réussis.
- Build Next.js **16.3.8** : réussi.
- `npm audit --omit=dev` : **zéro vulnérabilité signalée** ; la limite de l’audit complet des dépendances de développement est expliquée plus haut.
- `git diff --check` sur les fichiers applicatifs : réussi.

## Vérification complémentaire : administration et espace client

Le contrôle demandé sur localhost:8001 et l’espace client a révélé et corrigé :

- Les nouvelles fiches en lecture seule pouvaient s’ouvrir sans leurs champs. Les règles Cas A, codes, récompenses, journal et intentions KKIAPAY montrent désormais les données de suivi.
- Les dates d’essai Cas B, le paiement déclencheur, le cooling et les conditions figées sont visibles dans leurs fiches.
- La supervision propose des accès directs aux deux programmes et à KKIAPAY, selon les permissions du compte.
- L’écran KKIAPAY indique l’environnement, les pays activés et la présence des accès, sans afficher les secrets. La seule existence de clés n’est pas présentée comme une certification marchande.
- Les paiements KKIAPAY en attente indiquent la confirmation automatique serveur, sans bouton de validation manuelle. Le constat d’encaissement sélectionne son état réellement enregistré.
- Un programme Cas A désactivé conserve l’historique des récompenses du client. Les règles, plafond et validité sont affichés ; les invitations sans activité ont un état vide explicite.
- Les erreurs API sont visibles et réessayables, et l’échec du presse-papiers propose la copie manuelle.
- Le Burkina Faso est ajouté aux pays, à l’inscription et aux contrôles KKIAPAY. Les six pays KKIAPAY sont autorisés par défaut ; leurs tarifs doivent être XOF et l’intégration reste désactivée tant que son interrupteur est fermé.
- `infra/production/compose.yml` transmet les paramètres KKIAPAY à l’API, au worker et au planificateur ; le modèle `.env` contient les emplacements TEST et LIVE. Les valeurs locales déjà renseignées sont conservées.

Dernière suite complète : **1256 tests backend réussis** (258,73 s). Tests web : **21 réussis**. TypeScript, ESLint, Ruff, build Next.js et cohérence des migrations : réussis ; audit des dépendances de production sans alerte.

Après l’autorisation des six pays par défaut : **47 tests ciblés réussis**, couvrant chaque pays, l’isolation, les interfaces et les règles de paiement. Les modèles `.env.example` et `infra/production/env.exemple` contiennent tous les emplacements TEST/LIVE ; le `.env` local conserve les valeurs déjà saisies.

Vérification navigateur : **14 écrans à 375 et 1365 pixels**, administrateur et client FR/EN, sans débordement horizontal de page ni erreur JavaScript. Copie du code, historique en pause et reprise après panne API vérifiés. Captures et résultats : `tmp/programmes-*.png` et `tmp/programmes-visual-results.json`. Les comptes, le salon et les sessions temporaires ont été supprimés.

Les logs de vérification sont conservés dans `tmp/mini-salon-final-*.log`. Ces vérifications ne remplacent pas le paiement sandbox marchand encore requis pour activer KKIAPAY.
