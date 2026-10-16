"""Ce que disent les e-mails adresses aux professionnels, dans chaque langue.

Les e-mails a la cliente parlent la langue de sa reservation ; ceux-ci
parlent la langue que chaque compte a retenue dans son espace
(`User.locale`). Un meme evenement peut donc partir en francais a la
proprietaire et en anglais a la gerante — et un salon cree demain, dans
n'importe quelle langue proposee, n'a rien a configurer.

Ces cles rejoignent le catalogue commun (`textes.py`) : `t.dire("cle")`
s'emploie de la meme maniere, et `tests/test_emails_langues.py` refuse toute
cle presente d'un cote seulement.

Le contenu saisi par le salon ou la cliente — nom de la prestation, message,
motif — reste tel qu'il a ete ecrit.
"""

from __future__ import annotations

FR_PRO: dict[str, str] = {
    # --- commun ---------------------------------------------------------------
    "pro_bonjour": "Bonjour,",
    "pro_signature": "L'équipe Beauty Salon",
    "pro_pied": "Message automatique de votre espace professionnel.",
    "pro_cliente": "Cliente",
    "pro_telephone": "Téléphone",
    "pro_prestataire": "Prestataire",
    "pro_origine": "Origine",
    "pro_motif": "Motif",
    "pro_message_cliente": "Message de la cliente",
    "source_web": "Mini-site",
    "source_staff": "Saisie salon",
    "source_whatsapp": "WhatsApp",
    "source_marketplace": "Marketplace",
    "role_owner": "Propriétaire",
    "role_manager": "Gérant",
    "role_receptionist": "Réceptionniste",
    "role_staff": "Prestataire",
    # --- nouvelle reservation -------------------------------------------------
    "pro_resa_objet": "Nouvelle réservation - {prestation}",
    "pro_resa_titre": "Nouvelle réservation",
    "pro_resa_intro": "Une nouvelle cliente vient de réserver.",
    "pro_resa_txt": "Nouvelle réservation sur votre mini-site.",
    "pro_resa_attente_titre": "En attente du versement",
    "pro_resa_attente": (
        "Le créneau est bloqué. Vous serez prévenu dès que la cliente aura envoyé "
        "sa preuve de paiement."
    ),
    "pro_ouvrir_agenda": "Ouvrir mon agenda",
    "pro_retrouver_agenda": "Retrouvez ce rendez-vous dans votre agenda :",
    # --- acompte a verifier ---------------------------------------------------
    "pro_acompte_objet": "Acompte à vérifier — {cliente}",
    "pro_acompte_pre": "{cliente} a envoyé sa preuve de paiement — à vérifier",
    "pro_acompte_titre": "Un acompte attend votre vérification",
    "pro_acompte_bloque": (
        "Tant que vous n'avez pas répondu, le créneau reste bloqué et la cliente attend."
    ),
    "pro_acompte_intro": "Une cliente a envoyé une preuve de versement pour son acompte.",
    "pro_acompte_txt": "{cliente} a envoyé une preuve de versement pour son acompte.",
    "pro_acompte_suite": (
        "Retrouvez le versement dans votre application de paiement, puis acceptez "
        "ou refusez depuis votre agenda."
    ),
    "pro_acompte_bouton": "Vérifier maintenant",
    # --- annulation -----------------------------------------------------------
    "pro_annule_objet": "Annulation — {cliente}",
    "pro_annule_pre": "{cliente} a annulé — créneau du {date} libéré",
    "pro_annule_titre": "Une cliente a annulé",
    "pro_annule_intro": "Une cliente a annulé son rendez-vous.",
    "pro_annule_txt": "{cliente} a annulé son rendez-vous.",
    "pro_annule_libre": "Le créneau est de nouveau libre.",
    "pro_annule_attente": (
        "Si des clientes sont sur votre liste d'attente, c'est le moment de les prévenir."
    ),
    "pro_annule_bouton": "Voir la liste d'attente",
    # --- bienvenue ------------------------------------------------------------
    "bienvenue_objet": "Bienvenue sur Beauty Salon, {salon}",
    "bienvenue_pre": (
        "Votre espace est prêt — préparez votre catalogue en attendant la mise en ligne"
    ),
    "bienvenue_titre": "Bienvenue sur Beauty Salon",
    "bienvenue_intro": "Votre salon {salon} est créé. Voici où le retrouver.",
    "bienvenue_mini_site": "Mini-site",
    "bienvenue_espace": "Espace professionnel",
    "bienvenue_compte": "Compte",
    "bienvenue_pas_public": "Votre mini-site n'est pas encore public.",
    "bienvenue_verification": (
        "Notre équipe le vérifie avant sa mise en ligne. Vous recevrez un message "
        "dès qu'il sera visible."
    ),
    "bienvenue_preparer": (
        "En attendant, préparez votre catalogue, vos horaires et votre équipe : tout "
        "sera déjà en place le jour de l'ouverture."
    ),
    "bienvenue_bouton": "Ouvrir mon espace",
    "bienvenue_pied": (
        "Vous recevez ce message parce qu'un salon vient d'être créé avec cette adresse."
    ),
    "bienvenue_txt_cree": "Votre salon {salon} est créé sur Beauty Salon.",
    "bienvenue_txt_adresse": "Adresse de votre mini-site : {adresse}",
    "bienvenue_txt_espace": "Votre espace professionnel : {adresse}",
    "bienvenue_txt_suite": (
        "Prochaine étape : notre équipe vérifie votre salon avant de rendre votre "
        "mini-site public. En attendant, vous pouvez déjà préparer votre catalogue, "
        "vos horaires et votre équipe depuis votre espace."
    ),
    "bienvenue_txt_en_ligne": "Vous recevrez un message dès que votre mini-site sera en ligne.",
    # --- invitation d'equipe --------------------------------------------------
    "invitation_objet": "Rejoignez l'équipe de {salon}",
    "invitation_pre": "Rejoignez l'équipe de {salon} — le lien est valable 7 jours",
    "invitation_titre": "Vous êtes invitée à rejoindre une équipe",
    "invitation_intro": "{salon} vous invite à rejoindre son équipe sur Beauty Salon.",
    "invitation_salon": "Salon",
    "invitation_role": "Rôle",
    "invitation_par": "Invitée par",
    "invitation_bouton": "Accepter l'invitation",
    "invitation_validite": (
        "Ce lien est valable 7 jours. Si vous n'attendiez pas cette invitation, "
        "ignorez simplement ce message : sans votre accord, rien ne se passe."
    ),
    "invitation_pied": "Invitation envoyée depuis l'espace professionnel de {salon}.",
    "invitation_txt": "Vous êtes invité(e) à rejoindre l'équipe de {salon} sur Beauty Salon.",
    "invitation_txt_lien": "Acceptez l'invitation ici :",
    # --- mot de passe oublie --------------------------------------------------
    "reinit_objet": "Réinitialiser votre mot de passe Beauty Salon",
    "reinit_pre": "Choisissez un nouveau mot de passe — lien valable {heures} heures",
    "reinit_titre": "Réinitialiser votre mot de passe",
    "reinit_intro": (
        "Vous avez demandé à réinitialiser le mot de passe de votre compte Beauty Salon."
    ),
    "reinit_bouton": "Choisir un nouveau mot de passe",
    "reinit_pas_vous": "Vous n'avez rien demandé ?",
    "reinit_ignorer": (
        "Ignorez ce message : votre mot de passe actuel reste valable, et personne "
        "n'a accès à votre compte."
    ),
    "reinit_validite": (
        "Ce lien est valable {heures} heures et ne fonctionne qu'une seule fois."
    ),
    "reinit_pied": "Ce message a été envoyé à la suite d'une demande sur Beauty Salon.",
    "reinit_txt_lien": "Choisissez un nouveau mot de passe ici :",
    "reinit_txt_ignorer": (
        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : votre "
        "mot de passe actuel reste valable."
    ),
    # --- alertes de securite --------------------------------------------------
    "secu_mot_de_passe_objet": "Votre mot de passe Beauty Salon a été modifié",
    "secu_mot_de_passe": (
        "Le mot de passe de votre compte vient d'être modifié. Toutes les autres "
        "sessions ouvertes ont été fermées."
    ),
    "secu_mfa_active_objet": "Double authentification activée sur votre compte Beauty Salon",
    "secu_mfa_active": (
        "La double authentification vient d'être activée : un code de votre "
        "application sera demandé à chaque connexion. Gardez vos codes de secours "
        "en lieu sûr."
    ),
    "secu_mfa_desactive_objet": (
        "Double authentification désactivée sur votre compte Beauty Salon"
    ),
    "secu_mfa_desactive": (
        "La double authentification vient d'être désactivée : votre mot de passe "
        "suffit de nouveau pour vous connecter."
    ),
    "secu_adresse_objet": "L'adresse e-mail de votre compte Beauty Salon a changé",
    "secu_adresse": (
        "L'adresse de connexion de votre compte a été remplacée par {adresse}. Ce "
        "message est envoyé à l'ancienne adresse."
    ),
    "secu_encaissement_objet": "Moyen d'encaissement modifié — {salon}",
    "secu_encaissement_creation": (
        "{auteur} a ajouté {moyen} aux moyens d'encaissement des acomptes de {salon}. "
        "Vos clientes paieront désormais à : {nouveau}."
    ),
    "secu_encaissement_modification": (
        "{auteur} a modifié {moyen} pour {salon}. Avant : {ancien}. Désormais : "
        "{nouveau}. Vos clientes enverront leurs acomptes à ces nouvelles coordonnées."
    ),
    "secu_encaissement_suppression": (
        "{auteur} a retiré {moyen} des moyens d'encaissement de {salon} "
        "(coordonnées retirées : {ancien})."
    ),
    "secu_pas_vous": "Ce n'était pas vous ?",
    "secu_aide": (
        "Ce n'était pas vous ? Choisissez tout de suite un nouveau mot de passe "
        "depuis « Mot de passe oublié », puis écrivez-nous en répondant à ce message."
    ),
    "secu_bouton": "Sécuriser mon compte",
    "secu_pied": "Message de sécurité envoyé automatiquement par Beauty Salon.",
}

EN_PRO: dict[str, str] = {
    # --- commun ---------------------------------------------------------------
    "pro_bonjour": "Hello,",
    "pro_signature": "The Beauty Salon team",
    "pro_pied": "Automatic message from your professional space.",
    "pro_cliente": "Client",
    "pro_telephone": "Phone",
    "pro_prestataire": "Staff member",
    "pro_origine": "Source",
    "pro_motif": "Reason",
    "pro_message_cliente": "Message from the client",
    "source_web": "Mini-site",
    "source_staff": "Entered by the salon",
    "source_whatsapp": "WhatsApp",
    "source_marketplace": "Marketplace",
    "role_owner": "Owner",
    "role_manager": "Manager",
    "role_receptionist": "Receptionist",
    "role_staff": "Staff member",
    # --- nouvelle reservation -------------------------------------------------
    "pro_resa_objet": "New booking - {prestation}",
    "pro_resa_titre": "New booking",
    "pro_resa_intro": "A new client has just booked.",
    "pro_resa_txt": "New booking on your mini-site.",
    "pro_resa_attente_titre": "Awaiting payment",
    "pro_resa_attente": (
        "The time slot is on hold. You will be notified as soon as the client sends "
        "proof of payment."
    ),
    "pro_ouvrir_agenda": "Open my calendar",
    "pro_retrouver_agenda": "Find this appointment in your calendar:",
    # --- acompte a verifier ---------------------------------------------------
    "pro_acompte_objet": "Deposit to check — {cliente}",
    "pro_acompte_pre": "{cliente} sent proof of payment — please check",
    "pro_acompte_titre": "A deposit is waiting for your check",
    "pro_acompte_bloque": (
        "Until you respond, the time slot stays on hold and the client is waiting."
    ),
    "pro_acompte_intro": "A client sent proof of payment for the deposit.",
    "pro_acompte_txt": "{cliente} sent proof of payment for the deposit.",
    "pro_acompte_suite": (
        "Find the payment in your payment app, then accept or decline it from your "
        "calendar."
    ),
    "pro_acompte_bouton": "Check now",
    # --- annulation -----------------------------------------------------------
    "pro_annule_objet": "Cancellation — {cliente}",
    "pro_annule_pre": "{cliente} cancelled — the {date} slot is free again",
    "pro_annule_titre": "A client cancelled",
    "pro_annule_intro": "A client cancelled their appointment.",
    "pro_annule_txt": "{cliente} cancelled their appointment.",
    "pro_annule_libre": "The time slot is free again.",
    "pro_annule_attente": (
        "If clients are on your waiting list, now is the time to let them know."
    ),
    "pro_annule_bouton": "View the waiting list",
    # --- bienvenue ------------------------------------------------------------
    "bienvenue_objet": "Welcome to Beauty Salon, {salon}",
    "bienvenue_pre": "Your space is ready — set up your catalogue before going live",
    "bienvenue_titre": "Welcome to Beauty Salon",
    "bienvenue_intro": "Your salon {salon} has been created. Here is where to find it.",
    "bienvenue_mini_site": "Mini-site",
    "bienvenue_espace": "Professional space",
    "bienvenue_compte": "Account",
    "bienvenue_pas_public": "Your mini-site is not public yet.",
    "bienvenue_verification": (
        "Our team reviews it before it goes live. You will receive a message as soon "
        "as it is visible."
    ),
    "bienvenue_preparer": (
        "In the meantime, set up your catalogue, opening hours and team: everything "
        "will be ready on opening day."
    ),
    "bienvenue_bouton": "Open my space",
    "bienvenue_pied": (
        "You are receiving this message because a salon was just created with this address."
    ),
    "bienvenue_txt_cree": "Your salon {salon} has been created on Beauty Salon.",
    "bienvenue_txt_adresse": "Your mini-site address: {adresse}",
    "bienvenue_txt_espace": "Your professional space: {adresse}",
    "bienvenue_txt_suite": (
        "Next step: our team reviews your salon before making your mini-site public. "
        "In the meantime, you can already set up your catalogue, opening hours and "
        "team from your space."
    ),
    "bienvenue_txt_en_ligne": "You will receive a message as soon as your mini-site is live.",
    # --- invitation d'equipe --------------------------------------------------
    "invitation_objet": "Join the {salon} team",
    "invitation_pre": "Join the {salon} team — the link is valid for 7 days",
    "invitation_titre": "You are invited to join a team",
    "invitation_intro": "{salon} invites you to join its team on Beauty Salon.",
    "invitation_salon": "Salon",
    "invitation_role": "Role",
    "invitation_par": "Invited by",
    "invitation_bouton": "Accept the invitation",
    "invitation_validite": (
        "This link is valid for 7 days. If you were not expecting this invitation, "
        "simply ignore this message: nothing happens without your consent."
    ),
    "invitation_pied": "Invitation sent from the professional space of {salon}.",
    "invitation_txt": "You are invited to join the {salon} team on Beauty Salon.",
    "invitation_txt_lien": "Accept the invitation here:",
    # --- mot de passe oublie --------------------------------------------------
    "reinit_objet": "Reset your Beauty Salon password",
    "reinit_pre": "Choose a new password — link valid for {heures} hours",
    "reinit_titre": "Reset your password",
    "reinit_intro": "You asked to reset the password of your Beauty Salon account.",
    "reinit_bouton": "Choose a new password",
    "reinit_pas_vous": "Didn't ask for this?",
    "reinit_ignorer": (
        "Ignore this message: your current password still works, and nobody has "
        "access to your account."
    ),
    "reinit_validite": "This link is valid for {heures} hours and works only once.",
    "reinit_pied": "This message was sent following a request on Beauty Salon.",
    "reinit_txt_lien": "Choose a new password here:",
    "reinit_txt_ignorer": (
        "If you did not make this request, ignore this message: your current "
        "password still works."
    ),
    # --- alertes de securite --------------------------------------------------
    "secu_mot_de_passe_objet": "Your Beauty Salon password was changed",
    "secu_mot_de_passe": (
        "The password of your account was just changed. All other open sessions "
        "have been signed out."
    ),
    "secu_mfa_active_objet": "Two-factor authentication enabled on your Beauty Salon account",
    "secu_mfa_active": (
        "Two-factor authentication was just enabled: a code from your app will be "
        "asked at each sign-in. Keep your recovery codes somewhere safe."
    ),
    "secu_mfa_desactive_objet": (
        "Two-factor authentication disabled on your Beauty Salon account"
    ),
    "secu_mfa_desactive": (
        "Two-factor authentication was just disabled: your password alone is enough "
        "to sign in again."
    ),
    "secu_adresse_objet": "The email address of your Beauty Salon account changed",
    "secu_adresse": (
        "The sign-in address of your account was replaced by {adresse}. This message "
        "is sent to the previous address."
    ),
    "secu_encaissement_objet": "Payment method changed — {salon}",
    "secu_encaissement_creation": (
        "{auteur} added {moyen} to the deposit payment methods of {salon}. Your "
        "clients will now pay to: {nouveau}."
    ),
    "secu_encaissement_modification": (
        "{auteur} changed {moyen} for {salon}. Before: {ancien}. Now: {nouveau}. "
        "Your clients will send their deposits to these new details."
    ),
    "secu_encaissement_suppression": (
        "{auteur} removed {moyen} from the deposit payment methods of {salon} "
        "(removed details: {ancien})."
    ),
    "secu_pas_vous": "Wasn't you?",
    "secu_aide": (
        "Wasn't you? Choose a new password right away from “Forgot password”, then "
        "write to us by replying to this message."
    ),
    "secu_bouton": "Secure my account",
    "secu_pied": "Security message sent automatically by Beauty Salon.",
}
