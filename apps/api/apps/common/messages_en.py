"""Les messages que l'API renvoie, en anglais.

---------------------------------------------------------------------------
Pourquoi un dictionnaire, et pourquoi a la sortie
---------------------------------------------------------------------------

L'API ecrit ses refus en francais, au fil du code : « Ce creneau est deja
passe. », « Mot de passe incorrect. ». Les reecrire tous derriere `gettext`
demanderait `msgfmt`, absent de la machine de developpement (voir
`notifications/textes.py`), et toucherait deux cent cinquante endroits.

Ces phrases sont donc traduites au moment ou la reponse part
(`common.renderers`), quand la requete demande l'anglais. La phrase
francaise reste la source : un message ajoute demain et oublie ici sort en
francais — lisible, et rattrape par `tests/test_messages_en.py`, qui
verifie que chaque message du code a sa traduction.

Les messages de Django et de DRF eux-memes (« This field is required. »,
regles de mot de passe, limitation de debit) n'ont pas besoin d'etre ici :
le middleware de langue active l'anglais pour les requetes d'API, et ils
sortent directement dans la bonne langue.

Le contenu saisi par quelqu'un — un nom, une liste d'articles — passe tel
quel : seuls les modeles de phrase sont traduits.
"""

from __future__ import annotations

import re

#: Les phrases sans variable, francais -> anglais.
EXACTS: dict[str, str] = {
    # --- comptes, connexion, double authentification ------------------------
    "La double authentification se règle depuis l'espace professionnel.": (
        "Two-factor authentication is set up from the professional space."
    ),
    "Saisissez le code de votre application d'authentification.": (
        "Enter the code from your authenticator app."
    ),
    "Mot de passe incorrect.": "Incorrect password.",
    "Le délai est dépassé. Saisissez de nouveau votre mot de passe.": (
        "Time is up. Enter your password again."
    ),
    "Session expirée.": "Session expired.",
    "Trop de tentatives. Patientez quelques minutes avant de réessayer.": (
        "Too many attempts. Wait a few minutes before trying again."
    ),
    "Code incorrect ou expiré.": "Incorrect or expired code.",
    "La double authentification est déjà active.": "Two-factor authentication is already on.",
    "Code incorrect. Vérifiez que l'heure de votre téléphone est juste.": (
        "Incorrect code. Check that your phone's clock is correct."
    ),
    "La double authentification n'est pas active.": "Two-factor authentication is not on.",
    "Une adresse e-mail est obligatoire.": "An email address is required.",
    "Cette adresse est réservée.": "This address is reserved.",
    "Cette adresse est déjà prise.": "This address is already taken.",
    "Code de parrainage inconnu.": "Unknown referral code.",
    "Vous devez accepter les conditions.": "You must accept the terms.",
    "Fuseau horaire inconnu.": "Unknown time zone.",
    "Un compte existe déjà avec cette adresse e-mail.": (
        "An account already exists with this email address."
    ),
    "Cette personne fait déjà partie de l'équipe.": "This person is already on the team.",
    "Lien d'invitation invalide.": "Invalid invitation link.",
    "Cette invitation n'est plus valable.": "This invitation is no longer valid.",
    (
        "Cette adresse est celle d'un compte client. Un compte professionnel utilise "
        "une autre adresse e-mail : demandez une invitation sur une autre adresse."
    ): (
        "This address belongs to a client account. A professional account uses a "
        "different email address: ask for an invitation on another address."
    ),
    (
        "Un compte existe déjà pour cette adresse : saisissez son mot de passe pour "
        "accepter l'invitation."
    ): (
        "An account already exists for this address: enter its password to accept "
        "the invitation."
    ),
    "Un mot de passe est requis pour créer le compte.": (
        "A password is required to create the account."
    ),
    (
        "Ce mot de passe figure dans des fuites de données connues : il est déjà essayé "
        "par les pirates. Choisissez-en un autre."
    ): (
        "This password appears in known data breaches: attackers already try it. "
        "Choose another one."
    ),
    "Adresse e-mail confirmée.": "Email address confirmed.",
    "Un nouveau lien vient de vous être envoyé.": "A new link has just been sent to you.",
    "Si un compte existe, un e-mail vient d'être envoyé.": (
        "If an account exists, an email has just been sent."
    ),
    "Mot de passe mis à jour.": "Password updated.",
    "Adresse e-mail ou mot de passe incorrect.": "Incorrect email address or password.",
    "Votre adresse est déjà confirmée.": "Your address is already confirmed.",
    "Un e-mail vient d'être envoyé. Patientez quelques minutes avant d'en demander un autre.": (
        "An email has just been sent. Wait a few minutes before asking for another one."
    ),
    "Langue non proposée.": "Language not available.",
    "Lien invalide ou expiré.": "Invalid or expired link.",
    "Mot de passe actuel incorrect.": "Incorrect current password.",
    "Vous ne pouvez pas changer votre propre rôle.": "You cannot change your own role.",
    "Seul un propriétaire peut nommer ou modifier un propriétaire.": (
        "Only an owner can appoint or change an owner."
    ),
    "Ce salon doit conserver au moins un propriétaire.": (
        "This salon must keep at least one owner."
    ),
    "Seul un propriétaire peut inviter un propriétaire.": "Only an owner can invite an owner.",
    "Cette invitation n'est plus en attente.": "This invitation is no longer pending.",
    "Une invitation est déjà en attente pour cette adresse.": (
        "An invitation is already pending for this address."
    ),
    # --- assistants -----------------------------------------------------------
    "Adresse inconnue.": "Unknown address.",
    "Offre Pro requise.": "Pro plan required.",
    "Conversation vide.": "Empty conversation.",
    "Le dernier message doit venir de la personne.": "The last message must come from the person.",
    "Conversation trop longue.": "Conversation too long.",
    "Message invalide.": "Invalid message.",
    "Message vide.": "Empty message.",
    "La passerelle WhatsApp n'est pas configurée sur la plateforme.": (
        "The WhatsApp gateway is not set up on the platform."
    ),
    "L'assistant n'est pas activé.": "The assistant is not enabled.",
    "Seul le propriétaire du salon branche n8n.": "Only the salon owner can connect n8n.",
    "Seul le propriétaire du salon débranche n8n.": "Only the salon owner can disconnect n8n.",
    "L'assistant ne peut pas répondre pour le moment.": "The assistant cannot answer right now.",
    "Cette fonction fait partie de l'offre Pro.": "This feature is part of the Pro plan.",
    "Instance ou jeton inconnu.": "Unknown instance or token.",
    # --- abonnement et paiements ------------------------------------------------
    "Autorisation de vérification requise.": "Verification permission required.",
    "Indiquez un état valide et un motif de dix caractères au moins.": (
        "Give a valid state and a reason of at least ten characters."
    ),
    "Ce paiement n'existe pas.": "This payment does not exist.",
    "Seul un paiement confirmé peut faire l'objet de ce constat.": (
        "Only a confirmed payment can be reported this way."
    ),
    "KKIAPAY n'est pas configuré.": "KKIAPAY is not set up.",
    "Réponse KKIAPAY invalide.": "Invalid KKIAPAY response.",
    "KKIAPAY n'est pas disponible dans le pays de ce salon.": (
        "KKIAPAY is not available in this salon's country."
    ),
    "KKIAPAY accepte uniquement XOF, pas XAF.": "KKIAPAY only accepts XOF, not XAF.",
    "Configurez un tarif KKIAPAY en XOF entiers.": "Set a KKIAPAY price in whole XOF.",
    "Configurez le délai d'abandon des paiements dans l'administration.": (
        "Set the payment abandonment delay in the administration."
    ),
    "Référence KKIAPAY invalide.": "Invalid KKIAPAY reference.",
    "Ce paiement a été archivé.": "This payment has been archived.",
    "Cet environnement KKIAPAY n'est pas actif.": "This KKIAPAY environment is not active.",
    "Transaction non associée à ce paiement.": "Transaction not linked to this payment.",
    "Le paiement n'est pas confirmé par KKIAPAY.": "The payment is not confirmed by KKIAPAY.",
    "Devise KKIAPAY incompatible.": "Incompatible KKIAPAY currency.",
    "La vérification KKIAPAY est indisponible. Réessayez.": (
        "KKIAPAY verification is unavailable. Try again."
    ),
    "Montant KKIAPAY invalide.": "Invalid KKIAPAY amount.",
    "Le montant vérifié ne correspond pas à l'abonnement.": (
        "The verified amount does not match the subscription."
    ),
    "Cette intention de paiement a expiré. Contactez le support.": (
        "This payment intent has expired. Contact support."
    ),
    "Un paiement KKIAPAY est déjà en cours.": "A KKIAPAY payment is already in progress.",
    "Ce paiement est déjà associé à une autre transaction.": (
        "This payment is already linked to another transaction."
    ),
    "Cet abonnement est suspendu. Contactez le support de la plateforme.": (
        "This subscription is suspended. Contact the platform support."
    ),
    (
        "Votre abonnement a expiré : le tableau de bord est en lecture seule. Réglez votre "
        "abonnement depuis la page Abonnement pour tout rouvrir."
    ): (
        "Your subscription has expired: the dashboard is read-only. Pay your "
        "subscription from the Subscription page to reopen everything."
    ),
    (
        "Les réservations en ligne de ce salon sont momentanément indisponibles. "
        "Contactez-le directement."
    ): (
        "Online bookings for this salon are temporarily unavailable. Contact the "
        "salon directly."
    ),
    "Format non accepté : envoyez une capture en JPEG, PNG ou WebP.": (
        "Format not accepted: send a screenshot in JPEG, PNG or WebP."
    ),
    (
        "Impossible de convertir les jours restants : l'offre actuelle et la nouvelle "
        "n'ont de prix dans aucune devise commune. Complétez les tarifs, puis réessayez."
    ): (
        "The remaining days cannot be converted: the current plan and the new one have "
        "no price in a common currency. Complete the prices, then try again."
    ),
    "Aucune offre d'essai n'est configurée.": "No trial plan is set up.",
    (
        "Confirmez d'abord votre adresse e-mail : le lien vous a été envoyé à "
        "l'inscription (vous pouvez le renvoyer depuis le bandeau en haut de l'écran)."
    ): (
        "Confirm your email address first: the link was sent to you when you signed "
        "up (you can resend it from the banner at the top of the screen)."
    ),
    "Cette offre n'existe pas.": "This plan does not exist.",
    "Ce pays n'est pas proposé.": "This country is not available.",
    "Cette devise n'est pas proposée.": "This currency is not available.",
    "Utilisez le paiement KKIAPAY intégré.": "Use the built-in KKIAPAY payment.",
    "Ce moyen de paiement n'est pas disponible pour ce pays et cette devise.": (
        "This payment method is not available for this country and currency."
    ),
    "La référence contient des caractères non valides. Recopiez-la depuis votre reçu.": (
        "The reference contains invalid characters. Copy it again from your receipt."
    ),
    (
        "Indiquez la référence de la transaction, telle qu'elle apparaît dans votre "
        "application de paiement."
    ): (
        "Enter the transaction reference, as it appears in your payment app."
    ),
    "Indiquez le motif du refus : il sera montré au salon.": (
        "Give the reason for the refusal: it will be shown to the salon."
    ),
    "Une prolongation manuelle doit être justifiée.": "A manual extension must be justified.",
    "Une prolongation porte sur 1 ou 12 mois.": "An extension covers 1 or 12 months.",
    "Un changement d'offre doit être justifié.": "A plan change must be justified.",
    "Offre inconnue ou non vendue.": "Unknown or unsold plan.",
    "On offre 0, 1 ou 12 mois.": "0, 1 or 12 months can be offered.",
    "Cette offre est désactivée.": "This plan is disabled.",
    "Une suspension doit être motivée.": "A suspension must be justified.",
    "Cette facture est déjà réglée.": "This invoice is already paid.",
    "Cette facture est annulée.": "This invoice is cancelled.",
    "Ce paiement nécessite une vérification serveur KKIAPAY.": (
        "This payment needs a KKIAPAY server check."
    ),
    "La réservation de la remise a expiré. Préparez un nouveau paiement.": (
        "The discount hold has expired. Prepare a new payment."
    ),
    "Ce salon est suspendu : réactivez-le avant de changer son offre.": (
        "This salon is suspended: reactivate it before changing its plan."
    ),
    (
        "Une période déjà payée est programmée après l'offre en cours : changer l'offre "
        "la ferait perdre. Laissez-la s'appliquer d'abord."
    ): (
        "An already paid period is scheduled after the current plan: changing the plan "
        "would lose it. Let it apply first."
    ),
    "Cet abonnement est déjà suspendu.": "This subscription is already suspended.",
    "Cet abonnement n'est pas suspendu.": "This subscription is not suspended.",
    "Ce salon n'a pas d'abonnement. Contactez le support.": (
        "This salon has no subscription. Contact support."
    ),
    (
        "Un retour à Standard est déjà programmé à la fin de votre période Pro : un "
        "nouveau paiement Pro sera possible une fois ce changement en vigueur."
    ): (
        "A return to Standard is already scheduled at the end of your Pro period: a new "
        "Pro payment will be possible once this change takes effect."
    ),
    (
        "Un paiement est déjà en cours de vérification. Vous serez prévenu(e) dès qu'il "
        "aura été examiné."
    ): (
        "A payment is already being checked. You will be notified as soon as it has "
        "been reviewed."
    ),
    "Cette référence de transaction a déjà été déclarée.": (
        "This transaction reference has already been declared."
    ),
    "Un paiement est déjà en cours de vérification.": "A payment is already being checked.",
    "Paiement introuvable.": "Payment not found.",
    "Transaction déjà utilisée.": "Transaction already used.",
    # --- espace cliente ---------------------------------------------------------
    "Un compte existe déjà avec cette adresse. Connectez-vous.": (
        "An account already exists with this address. Sign in."
    ),
    "Numéro de téléphone trop court.": "Phone number too short.",
    "Cet espace est réservé aux clientes.": "This space is for clients only.",
    "Si un compte existe pour cette adresse, un e-mail vient d'être envoyé.": (
        "If an account exists for this address, an email has just been sent."
    ),
    "Retiré de votre historique.": "Removed from your history.",
    "Rendez-vous manquant.": "Missing appointment.",
    "Ce rendez-vous n'est pas dans votre historique.": "This appointment is not in your history.",
    "Ce rendez-vous est encore à venir. Contactez le salon pour l'annuler.": (
        "This appointment is still upcoming. Contact the salon to cancel it."
    ),
    # --- commun : salon, droits ---------------------------------------------
    "Cette opération entre en conflit avec l'état actuel.": (
        "This operation conflicts with the current state."
    ),
    "Ce créneau n'est plus disponible.": "This time slot is no longer available.",
    "Événement invalide.": "Invalid event.",
    "Événement réservé.": "Reserved event.",
    "Salon introuvable.": "Salon not found.",
    "Accès refusé à ce salon.": "Access to this salon is denied.",
    "Précisez le salon avec l'en-tête X-Tenant-Id.": (
        "Specify the salon with the X-Tenant-Id header."
    ),
    "Une publication exige l'autorisation et la vérification.": (
        "Publishing requires consent and verification."
    ),
    "Le portrait doit utiliser HTTPS.": "The portrait must use HTTPS.",
    "Utilisez uniquement l'indicatif et les chiffres.": "Use only the country code and digits.",
    "Aucun salon n'a pu être déterminé pour cette requête.": (
        "No salon could be determined for this request."
    ),
    "Vous n'appartenez pas à ce salon.": "You do not belong to this salon.",
    "Votre rôle ne permet pas cette action.": "Your role does not allow this action.",
    "Réservé aux administrateurs de la plateforme.": "Reserved for platform administrators.",
    "Notes réservées au propriétaire et au gérant.": (
        "Notes are reserved for the owner and manager."
    ),
    # --- domaines, medias ------------------------------------------------------
    "Indiquez seulement le nom de domaine, par exemple monsalon.com.": (
        "Enter only the domain name, for example mysalon.com."
    ),
    "Ce nom de domaine n'est pas valide.": "This domain name is not valid.",
    "Ce domaine appartient à la plateforme : votre adresse gratuite existe déjà.": (
        "This domain belongs to the platform: your free address already exists."
    ),
    "Ce domaine est déjà relié à un autre site.": "This domain is already linked to another site.",
    "Cette adresse renvoie vers trop de redirections.": "This address redirects too many times.",
    (
        "Ce lien ne pointe pas vers une image ou une vidéo acceptée (JPEG, PNG, WebP, "
        "MP4, WebM)."
    ): (
        "This link does not point to an accepted image or video (JPEG, PNG, WebP, "
        "MP4, WebM)."
    ),
    "Ce lien renvoie un fichier vide.": "This link returns an empty file.",
    "Cette adresse n'a pas répondu. Vérifiez le lien.": (
        "This address did not respond. Check the link."
    ),
    "Cette adresse renvoie vers nulle part.": "This address leads nowhere.",
    "Introuvable dans ce salon.": "Not found in this salon.",
    "Format non accepté. Images JPEG, PNG, WebP ou vidéos MP4, WebM.": (
        "Format not accepted. JPEG, PNG, WebP images or MP4, WebM videos."
    ),
    # --- notifications ----------------------------------------------------------
    "Réservé aux comptes clientes.": "Reserved for client accounts.",
    "`endpoint` est requis.": "`endpoint` is required.",
    "Les notifications sur appareil ne sont pas configurées sur ce serveur.": (
        "Device notifications are not set up on this server."
    ),
    "Aucun appareil n'est inscrit pour ce compte.": "No device is registered for this account.",
    "`ids` doit être une liste.": "`ids` must be a list.",
    # --- parrainage --------------------------------------------------------------
    "Confirmez votre adresse e-mail pour partager un parrainage.": (
        "Confirm your email address to share a referral."
    ),
    "Impossible de générer un code unique.": "Could not generate a unique code.",
    "Le plafond doit être un montant entier dans cette devise.": (
        "The cap must be a whole amount in this currency."
    ),
    "Impossible de générer un code de parrainage unique.": (
        "Could not generate a unique referral code."
    ),
    "Seul le premier paiement d'abonnement confirmé valide le parrainage.": (
        "Only the first confirmed subscription payment validates the referral."
    ),
    "Code de parrainage inconnu ou désactivé.": "Unknown or disabled referral code.",
    "Une seule remise par échéance.": "Only one discount per billing period.",
    "Seul un parrainage en vérification se valide.": (
        "Only a referral under review can be validated."
    ),
    "Seule une remise disponible s'annule.": "Only an available discount can be cancelled.",
    "Indiquez un motif (10 caractères au moins).": "Give a reason (at least 10 characters).",
    "Cette remise n'est plus disponible.": "This discount is no longer available.",
    "Le délai de réservation de la remise doit être configuré.": (
        "The discount hold delay must be set."
    ),
    "Le plafond doit être dans la devise du salon.": "The cap must be in the salon's currency.",
    "Prestation ou options invalides.": "Invalid service or options.",
    # --- acompte, annulation par lien -----------------------------------------
    "Merci. Le salon vérifie le versement et vous confirme.": (
        "Thank you. The salon is checking the payment and will confirm."
    ),
    "Rendez-vous annulé.": "Appointment cancelled.",
    "Ce lien n'est plus valable.": "This link is no longer valid.",
    "Déjà annulé.": "Already cancelled.",
    "Le délai d'annulation est passé. Contactez le salon, il reste joignable.": (
        "The cancellation deadline has passed. Contact the salon, it can still be reached."
    ),
    # --- avis ---------------------------------------------------------------------
    "Notez au moins un critère.": "Rate at least one criterion.",
    "Lien incomplet.": "Incomplete link.",
    "Ce rendez-vous est introuvable.": "This appointment cannot be found.",
    # --- fiche du salon, apparence -------------------------------------------
    "Liste attendue.": "A list is expected.",
    "Texte attendu.": "Text is expected.",
    "Les chevrons < et > ne sont pas acceptés.": "The < and > characters are not accepted.",
    "Configuration invalide.": "Invalid configuration.",
    "Rubrique inconnue.": "Unknown section.",
    "Rubrique en double.": "Duplicate section.",
    "Page invalide.": "Invalid page.",
    "Identifiant de page invalide.": "Invalid page identifier.",
    "Page en double.": "Duplicate page.",
    "Chaque page a besoin d'un titre.": "Each page needs a title.",
    "Image invalide.": "Invalid image.",
    "Police non proposée.": "Font not available.",
    "Police non proposée pour le texte courant.": "Font not available for body text.",
    "Ce salon est momentanément indisponible.": "This salon is temporarily unavailable.",
    "Ce salon n'est pas encore en ligne.": "This salon is not online yet.",
    "Le thème doit être un objet.": "The theme must be an object.",
    "Image introuvable dans vos médias.": "Image not found in your media.",
    # --- agenda, reservations ----------------------------------------------
    "La date de fin précède la date de début.": "The end date is before the start date.",
    "La politique d'annulation doit être acceptée.": "The cancellation policy must be accepted.",
    "Ce créneau est déjà passé.": "This time slot has already passed.",
    "La fermeture précède l'ouverture.": "The closing time is before the opening time.",
    "La fin précède le début.": "The end is before the start.",
    "Indiquez une cliente existante, ou un nom et un téléphone.": (
        "Choose an existing client, or enter a name and a phone number."
    ),
    "La fin de la période précède son début.": "The end of the period is before its start.",
    "Créez un nouveau rendez-vous pour réutiliser une réduction restituée.": (
        "Create a new appointment to reuse a returned discount."
    ),
    "Cette période est déjà passée : choisissez des dates à venir.": (
        "This period has already passed: choose upcoming dates."
    ),
    "Choisissez une période dans l'année qui vient.": "Choose a period within the coming year.",
    "Ce prestataire ne réalise pas cette prestation.": (
        "This staff member does not perform this service."
    ),
    "Le prix et le bénéficiaire de cette réduction sont figés sur le rendez-vous.": (
        "The price and beneficiary of this discount are fixed on the appointment."
    ),
    (
        "Ce rendez-vous appartient à un historique de parrainage. Annulez-le pour "
        "conserver sa trace."
    ): (
        "This appointment belongs to a referral history. Cancel it to keep its record."
    ),
    "Date invalide.": "Invalid date.",
    "Statut non autorisé par cette route.": "Status not allowed by this route.",
    (
        "Une preuve de versement attend votre verdict. Repondez d'abord a « J'ai recu "
        "l'acompte » ou « Versement introuvable » : c'est ce geste qui enregistre "
        "l'argent en caisse."
    ): (
        "A proof of payment is waiting for your decision. First answer “I received the "
        "deposit” or “Payment not found”: that is what records the money in the till."
    ),
    "Cette prestation ne demande pas d'acompte.": "This service does not require a deposit.",
    "Cet acompte est déjà encaissé.": "This deposit has already been collected.",
    "Aucun acompte n'est noté comme encaissé.": "No deposit is recorded as collected.",
    "Ce code ne correspond à aucun rendez-vous de votre salon.": (
        "This code does not match any appointment in your salon."
    ),
    "Ce prestataire a déjà un rendez-vous sur ce créneau.": (
        "This staff member already has an appointment in this time slot."
    ),
    "Scannez un QR ou saisissez un code d'arrivée.": "Scan a QR code or enter a check-in code.",
    (
        "Ce code n'a pas la bonne forme : six caractères, sans les lettres I, O, S, B, U "
        "ni les chiffres 0, 1, 2, 5, 6, 8, 9."
    ): (
        "This code has the wrong format: six characters, without the letters I, O, S, "
        "B, U or the digits 0, 1, 2, 5, 6, 8, 9."
    ),
    "Deux rendez-vous portent ce code. Scannez le QR de la cliente pour lever le doute.": (
        "Two appointments have this code. Scan the client's QR code to be sure."
    ),
    "Aucun rendez-vous des deux jours passés ou à venir ne porte ce code.": (
        "No appointment in the past or next two days has this code."
    ),
    "Vous êtes inscrite. Le salon vous préviendra si une place se libère.": (
        "You are on the list. The salon will let you know if a spot opens up."
    ),
    "Ce salon n'accepte pas de réservation.": "This salon does not accept bookings.",
    "Aucun prestataire ne réalise cette prestation.": "No staff member performs this service.",
    "Une des options choisies n'est plus proposée.": (
        "One of the chosen options is no longer offered."
    ),
    "Cette prestation se fait uniquement au salon.": "This service is only available at the salon.",
    "Cette zone n'est pas desservie.": "This area is not served.",
    "Indiquez l'adresse où vous souhaitez être reçue.": (
        "Enter the address where you want to be served."
    ),
    "Choisissez la zone de votre domicile.": "Choose the area where you live.",
    # --- boutique -----------------------------------------------------------------
    "Quantité trop élevée pour une réservation.": "Quantity too high for one booking.",
    "Un des articles choisis n'est plus proposé pour cette prestation.": (
        "One of the chosen items is no longer offered for this service."
    ),
    "Quantité invalide.": "Invalid quantity.",
    "Un article de votre boutique porte déjà ce nom.": (
        "An item in your shop already has this name."
    ),
    # --- identite du salon ------------------------------------------------------
    "Le nom du salon ne peut pas être vide.": "The salon name cannot be empty.",
    "Cette adresse est déjà utilisée par un autre compte.": (
        "This address is already used by another account."
    ),
    "Saisissez votre mot de passe actuel pour changer d'adresse e-mail.": (
        "Enter your current password to change your email address."
    ),
    "Devise non proposée.": "Currency not available.",
}

#: Les phrases a variables. `{nom}` capture n'importe quel texte ; dans la
#: version anglaise, `{nom}` le reprend tel quel (apres traduction s'il
#: s'agit lui-meme d'un libelle connu, comme un statut).
MODELES: list[tuple[str, str]] = [
    ("Clés de thème inconnues : {liste}.", "Unknown theme keys: {liste}."),
    (
        "La capture dépasse {limite} Mo. Envoyez une image plus légère.",
        "The screenshot exceeds {limite} MB. Send a lighter image.",
    ),
    (
        "L'offre {offre} n'a pas encore de tarif en {devise}. Choisissez une autre devise.",
        "The {offre} plan has no price in {devise} yet. Choose another currency.",
    ),
    (
        "Ce paiement a déjà été traité ({statut}).",
        "This payment has already been processed ({statut}).",
    ),
    (
        "Le montant de l'offre {offre} a changé : il est maintenant de {montant}. Vérifiez "
        "le montant versé avant de déclarer votre paiement.",
        "The price of the {offre} plan has changed: it is now {montant}. Check the amount "
        "you paid before declaring your payment.",
    ),
    ("Fichier trop volumineux (max {taille} Mo).", "File too large (max {taille} MB)."),
    ("Réglages inconnus : {liste}.", "Unknown settings: {liste}."),
    (
        "Ce délai ({heures} h) dépasse la fenêtre de réservation ({jours} jours) : plus "
        "aucun créneau ne serait proposé.",
        "This notice ({heures} h) exceeds the booking window ({jours} days): no time "
        "slot would be offered any more.",
    ),
    ("Plage limitée à {jours} jours.", "Range limited to {jours} days."),
    (
        "Ce code est celui de {a}, pas du rendez-vous ouvert.",
        "This code belongs to {a}, not to the open appointment.",
    ),
    ("Ce code est celui de {a}, pas de {b}.", "This code belongs to {a}, not to {b}."),
    (
        "Ce rendez-vous n'est pas confirmé : il est « {statut} ».",
        "This appointment is not confirmed: it is “{statut}”.",
    ),
    ("Indiquez ce que vous apportez : {liste}", "Tell us what you are bringing: {liste}"),
    ("« {produit} » : il n'en reste que {reste}.", "“{produit}”: only {reste} left."),
    ("« {produit} » est en rupture.", "“{produit}” is out of stock."),
    ("{nombre} caractères au plus.", "{nombre} characters at most."),
    ("{nombre} pages au plus.", "{nombre} pages at most."),
    ("{nom} est déjà notée arrivée.", "{nom} is already checked in."),
    ("{nom} est arrivée.", "{nom} has arrived."),
    (
        "{nom} a été retirée de votre liste. Ses anciens rendez-vous gardent son nom.",
        "{nom} has been removed from your list. Past appointments keep the name.",
    ),
    (
        "{nom} a {nombre} rendez-vous à venir, dont un le {quand}. Déplacez-les ou "
        "annulez-les d'abord.",
        "{nom} has {nombre} upcoming appointment(s), including one on {quand}. Move or "
        "cancel them first.",
    ),
]

#: Les libelles inseres dans les phrases ci-dessus (statuts, en minuscules).
LIBELLES: dict[str, str] = {
    "en attente de paiement": "awaiting payment",
    "demandée": "requested",
    "confirmée": "confirmed",
    "cliente arrivée": "client arrived",
    "terminée": "completed",
    "annulée": "cancelled",
    "absente": "no-show",
    "en attente de vérification": "awaiting verification",
    "approuvée": "approved",
    "refusée": "declined",
}


def _propre(texte: str) -> str:
    """Les apostrophes typographiques et les espaces ne doivent pas faire
    manquer une traduction : « n’existe » et « n'existe » sont la meme
    phrase."""
    return " ".join(texte.replace("’", "'").split())


_EXACTS = {_propre(fr): en for fr, en in EXACTS.items()}


def _motif(modele: str) -> re.Pattern:
    morceaux = re.split(r"\{(\w+)\}", _propre(modele))
    motif = ""
    for i, morceau in enumerate(morceaux):
        motif += re.escape(morceau) if i % 2 == 0 else f"(?P<{morceau}>.+?)"
    return re.compile(f"^{motif}$", re.S)


_MODELES = [(_motif(fr), en) for fr, en in MODELES]


_DATE_HEURE = re.compile(r"^(\d{1,2}/\d{1,2}) à (\d{1,2}:\d{2})$")


def _valeur(valeur: str) -> str:
    """Une valeur inseree dans une phrase : un statut connu, une date
    « 24/09 à 14:30 » — ou le texte tel quel (un nom, une liste)."""
    date = _DATE_HEURE.match(valeur)
    if date:
        return f"{date.group(1)} at {date.group(2)}"
    return LIBELLES.get(valeur.lower(), valeur)


def traduire(texte: str) -> str:
    """La version anglaise d'un message de l'API, ou le message tel quel."""
    propre = _propre(texte)
    if propre in _EXACTS:
        return _EXACTS[propre]
    for motif, anglais in _MODELES:
        trouve = motif.match(propre)
        if trouve:
            valeurs = {
                nom: _valeur(valeur) for nom, valeur in trouve.groupdict().items()
            }
            return anglais.format(**valeurs)
    return texte
