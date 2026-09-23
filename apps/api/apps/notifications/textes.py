"""Ce que disent les e-mails, dans chaque langue.

---------------------------------------------------------------------------
Pourquoi un dictionnaire et non `gettext`
---------------------------------------------------------------------------

Django a son propre mecanisme de traduction, et c'est normalement le bon.
Il demande `msgfmt`, l'outil de GNU gettext, pour compiler les catalogues
`.po` en `.mo`. Cet outil n'est pas installe sur la machine de developpement
de ce projet — verifie — et un catalogue qu'on ne peut pas compiler ici est
un piege : il se versionne sans effet, et le premier qui modifie une phrase
ne voit rien changer.

Un dictionnaire Python n'a besoin de rien. Il se lit, se relit et se
verifie — `tests/test_emails_langues.py` refuse toute cle presente d'un cote
et pas de l'autre.

---------------------------------------------------------------------------
Ce qui n'est pas ici
---------------------------------------------------------------------------

Le contenu ecrit par le salon : nom des prestations, politique de retard,
politique d'annulation. Il vit en base et se traduit ailleurs — voir
`apps/translations`. Un e-mail anglais peut donc porter une politique de
retard en francais, si le salon vient de l'ecrire et que la traduction n'est
pas encore passee. C'est voulu : mieux vaut la regle dans la mauvaise langue
que pas de regle.
"""

from __future__ import annotations

LANGUE_PAR_DEFAUT = "fr"

FR: dict[str, str] = {
    # --- vocabulaire commun -------------------------------------------------
    "bonjour": "Bonjour {prenom},",
    "a_bientot": "À bientôt,",
    "pied_cliente": (
        "Vous recevez ce message parce que vous avez pris rendez-vous chez {salon}."
    ),
    "pied_salon": "Vous recevez ce message parce que vous gérez {salon}.",
    "propulse": "Propulsé par Beauty Salon",
    # --- le tableau de details ---------------------------------------------
    "prestation": "Prestation",
    "date": "Date",
    "avec": "Avec",
    "duree": "Durée",
    "option": "Option",
    "article": "Article",
    "inclus": "inclus",
    "a_domicile": "À domicile",
    "adresse": "Adresse",
    "total": "Total",
    "acompte": "Acompte",
    "montant": "Montant",
    "le_a": "{date} à {heure}",
    "duree_heures_minutes": "{heures} h {minutes}",
    "duree_heures": "{heures} h",
    "duree_minutes": "{minutes} min",
    # --- acompte ------------------------------------------------------------
    "acompte_demande": "Acompte demandé",
    "acompte_deja_regle": "Déjà réglé",
    "acompte_a_regler_dans": "À régler dans les {minutes} minutes",
    "regler_acompte": "Régler l'acompte",
    # --- retard -------------------------------------------------------------
    "retard_a_l_heure": "Merci d'arriver à l'heure",
    "retard_tolere": "Retard toléré : {minutes} minutes",
    # --- confirmation -------------------------------------------------------
    "confirmation_titre": "Votre rendez-vous est enregistré",
    "confirmation_objet": "Votre rendez-vous chez {salon}",
    "confirmation_intro": (
        "Votre rendez-vous chez {salon} est enregistré. Voici le détail ; "
        "gardez ce message, il vous servira de justificatif."
    ),
    "confirmation_pied": (
        "Pour annuler ou déplacer votre rendez-vous, contactez directement le salon."
    ),
    # --- rappel -------------------------------------------------------------
    "rappel_titre": "C'est demain",
    "rappel_objet": "Rappel : votre rendez-vous chez {salon}",
    "rappel_intro": (
        "Un mot pour vous rappeler votre rendez-vous chez {salon}. "
        "Rien à préparer, sinon arriver à l'heure."
    ),
    "itineraire": "Voir l'itinéraire",
    # --- accepte ------------------------------------------------------------
    "accepte_titre": "Votre rendez-vous est confirmé",
    "accepte_objet": "Rendez-vous confirmé chez {salon}",
    "accepte_intro": (
        "Le salon a confirmé votre rendez-vous. Il ne reste plus qu'à venir."
    ),
    # --- annulation ---------------------------------------------------------
    "annule_titre": "Votre rendez-vous est annulé",
    "annule_objet": "Rendez-vous annulé chez {salon}",
    "annule_intro": (
        "Votre rendez-vous chez {salon} n'aura pas lieu. "
        "Vous pouvez en reprendre un quand vous voulez."
    ),
    "reprendre_rdv": "Reprendre rendez-vous",
    # --- deplacement --------------------------------------------------------
    "deplace_titre": "Votre rendez-vous a changé d'heure",
    "deplace_objet": "Rendez-vous déplacé — {salon}",
    "deplace_intro": "Le salon a déplacé votre rendez-vous. Voici la nouvelle heure.",
    "ancienne_heure": "Ancienne heure",
    "nouvelle_heure": "Nouvelle heure",
    # --- acompte refuse -----------------------------------------------------
    "acompte_refuse_titre": "Votre versement n'a pas été retrouvé",
    "acompte_refuse_objet": "Acompte à revoir — {salon}",
    "acompte_refuse_intro": (
        "Le salon n'a pas retrouvé votre versement. Votre créneau est toujours "
        "gardé : renvoyez une capture plus lisible, ou contactez le salon."
    ),
    # --- demande d'avis -----------------------------------------------------
    "avis_titre": "Comment ça s'est passé ?",
    "avis_objet": "Votre avis sur {salon}",
    "avis_intro": (
        "Deux minutes suffisent, et votre avis aide les prochaines clientes "
        "à choisir en connaissance de cause."
    ),
    "avis_bouton": "Laisser mon avis",
    # --- e-mails du salon ---------------------------------------------------
    "salon_nouvelle_titre": "Nouveau rendez-vous",
    "salon_nouvelle_objet": "Nouveau rendez-vous — {service}",
    "salon_annule_titre": "Rendez-vous annulé",
    "salon_annule_objet": "Annulation — {service}",
    "salon_preuve_titre": "Une preuve de paiement est arrivée",
    "salon_preuve_objet": "Acompte à vérifier — {service}",
    "voir_agenda": "Voir mon agenda",
    "rappel_prevenir": "Si vous ne pouvez pas venir, prévenez le salon dès que possible.",
    "annule_par_salon": "Votre rendez-vous a été annulé",
    "annule_par_cliente": "Annulation confirmée",
    "annule_intro_salon": "{salon} a dû annuler votre rendez-vous.",
    "annule_intro_cliente": "Votre rendez-vous est bien annulé.",
    "annule_acompte": "Un acompte de {montant} avait été versé.",
    "annule_acompte_suite": "Contactez le salon pour convenir de la suite.",
    "annule_desole": (
        "Nous en sommes désolés. Vous pouvez reprendre rendez-vous quand vous le "
        "souhaitez."
    ),
    "deplace_ancien_titre": "Ancienne date : {date} à {heure}",
    "deplace_ancien_annule": "Ancienne date annulée",
    "deplace_ancien_corps": "Ce créneau n'est plus retenu pour vous.",
    "deplace_inchange": (
        "Rien d'autre ne change : ni le tarif, ni la prestation{acompte}. Si "
        "cette nouvelle date ne vous convient pas, écrivez au salon."
    ),
    "deplace_inchange_acompte": ", ni l'acompte déjà versé",
    "voir_rdv": "Voir mon rendez-vous",
    "acompte_refuse_motif": "Motif indiqué par le salon",
    "acompte_refuse_suite": (
        "Votre créneau est toujours réservé. Si vous avez bien payé, renvoyez "
        "votre capture d'écran."
    ),
    "acompte_refuse_bouton": "Renvoyer ma preuve",
    "avis_comment": "Vous êtes passée chez {salon} — en un mot, c'était comment ?",
    "avis_cinq_points": (
        "Vous noterez cinq points, de 1 à 5 étoiles, et vous pourrez ajouter un "
        "commentaire si vous le souhaitez."
    ),
    "avis_pied": (
        "Vous recevez ce message après votre rendez-vous chez {salon}. Si vous ne "
        "souhaitez pas laisser d'avis, ignorez simplement cet e-mail."
    ),
    "pre_confirmation": "{service} — {date} à {heure}",
    "pre_rappel": "Demain à {heure} chez {salon}",
    "pre_accepte": "C'est confirmé — {date} à {heure}",
    "pre_annule": "{service} du {date} — annulé",
    "pre_deplace": "Nouvelle date : {date} à {heure}",
    "pre_acompte_refuse": "Votre créneau est gardé — renvoyez votre preuve de paiement",
    "pre_avis": "Votre avis sur {service} en deux minutes",
    "cliente": "Cliente",
}

EN: dict[str, str] = {
    "bonjour": "Hello {prenom},",
    "a_bientot": "See you soon,",
    "pied_cliente": (
        "You are receiving this message because you booked an appointment at {salon}."
    ),
    "pied_salon": "You are receiving this message because you manage {salon}.",
    "propulse": "Powered by Beauty Salon",
    "prestation": "Service",
    "date": "Date",
    "avec": "With",
    "duree": "Length",
    "option": "Extra",
    "article": "Item",
    "inclus": "included",
    "a_domicile": "At your place",
    "adresse": "Address",
    "total": "Total",
    "acompte": "Deposit",
    "montant": "Amount",
    "le_a": "{date} at {heure}",
    "duree_heures_minutes": "{heures} h {minutes}",
    "duree_heures": "{heures} h",
    "duree_minutes": "{minutes} min",
    "acompte_demande": "Deposit due",
    "acompte_deja_regle": "Already paid",
    "acompte_a_regler_dans": "To be paid within {minutes} minutes",
    "regler_acompte": "Pay the deposit",
    "retard_a_l_heure": "Please arrive on time",
    "retard_tolere": "Lateness allowed: {minutes} minutes",
    "confirmation_titre": "Your appointment is booked",
    "confirmation_objet": "Your appointment at {salon}",
    "confirmation_intro": (
        "Your appointment at {salon} is booked. Here are the details; keep this "
        "message, it serves as your proof of booking."
    ),
    "confirmation_pied": (
        "To cancel or move your appointment, contact the salon directly."
    ),
    "rappel_titre": "It's tomorrow",
    "rappel_objet": "Reminder: your appointment at {salon}",
    "rappel_intro": (
        "Just a word to remind you of your appointment at {salon}. "
        "Nothing to prepare, other than arriving on time."
    ),
    "itineraire": "Get directions",
    "accepte_titre": "Your appointment is confirmed",
    "accepte_objet": "Appointment confirmed at {salon}",
    "accepte_intro": (
        "The salon has confirmed your appointment. All that is left is to come."
    ),
    "annule_titre": "Your appointment is cancelled",
    "annule_objet": "Appointment cancelled at {salon}",
    "annule_intro": (
        "Your appointment at {salon} will not take place. "
        "You can book another one whenever you like."
    ),
    "reprendre_rdv": "Book again",
    "deplace_titre": "Your appointment has moved",
    "deplace_objet": "New time for your appointment at {salon}",
    "deplace_intro": "The salon has moved your appointment. Here is the new time.",
    "ancienne_heure": "Previous time",
    "nouvelle_heure": "New time",
    "acompte_refuse_titre": "Your payment could not be found",
    "acompte_refuse_objet": "Deposit to review — {salon}",
    "acompte_refuse_intro": (
        "The salon could not find your payment. Your slot is still held: send a "
        "clearer screenshot, or contact the salon."
    ),
    "avis_titre": "How did it go?",
    "avis_objet": "Your review of {salon}",
    "avis_intro": (
        "Two minutes are enough, and your review helps the next clients choose "
        "with their eyes open."
    ),
    "avis_bouton": "Leave my review",
    "salon_nouvelle_titre": "New appointment",
    "salon_nouvelle_objet": "New appointment — {service}",
    "salon_annule_titre": "Appointment cancelled",
    "salon_annule_objet": "Cancellation — {service}",
    "salon_preuve_titre": "A payment proof has arrived",
    "salon_preuve_objet": "Deposit to check — {service}",
    "voir_agenda": "See my diary",
    "rappel_prevenir": "If you cannot make it, let the salon know as soon as you can.",
    "annule_par_salon": "Your appointment has been cancelled",
    "annule_par_cliente": "Cancellation confirmed",
    "annule_intro_salon": "{salon} had to cancel your appointment.",
    "annule_intro_cliente": "Your appointment is cancelled.",
    "annule_acompte": "A deposit of {montant} had been paid.",
    "annule_acompte_suite": "Contact the salon to agree what happens next.",
    "annule_desole": "We are sorry about this. You can book again whenever you like.",
    "deplace_ancien_titre": "Previous date: {date} at {heure}",
    "deplace_ancien_annule": "Previous date cancelled",
    "deplace_ancien_corps": "That slot is no longer held for you.",
    "deplace_inchange": (
        "Nothing else changes: not the price, not the service{acompte}. If this "
        "new date does not suit you, write to the salon."
    ),
    "deplace_inchange_acompte": ", not the deposit already paid",
    "voir_rdv": "See my appointment",
    "acompte_refuse_motif": "Reason given by the salon",
    "acompte_refuse_suite": "Your slot is still held. If you did pay, send your screenshot again.",
    "acompte_refuse_bouton": "Send my proof again",
    "avis_comment": "You came to {salon} — in a word, how was it?",
    "avis_cinq_points": (
        "You will rate five things, from 1 to 5 stars, and you can add a comment "
        "if you like."
    ),
    "avis_pied": (
        "You are receiving this message after your appointment at {salon}. If you "
        "would rather not leave a review, simply ignore this email."
    ),
    "pre_confirmation": "{service} — {date} at {heure}",
    "pre_rappel": "Tomorrow at {heure} at {salon}",
    "pre_accepte": "It's confirmed — {date} at {heure}",
    "pre_annule": "{service} on {date} — cancelled",
    "pre_deplace": "New date: {date} at {heure}",
    "pre_acompte_refuse": "Your slot is held — send your payment proof again",
    "pre_avis": "Your review of {service} in two minutes",
    "cliente": "Client",
}

CATALOGUES: dict[str, dict[str, str]] = {"fr": FR, "en": EN}


class Textes(dict):
    """Le catalogue d'une langue, utilisable depuis un gabarit Django.

    Un dictionnaire suffit pour `{{ t.total }}`. Cette sous-classe n'ajoute
    qu'une chose : `t.dire("cle", ...)` pour les phrases a variables, que la
    syntaxe des gabarits ne sait pas appeler avec des arguments.

    Une cle inconnue rend la cle elle-meme, pas une chaine vide : un e-mail
    ou l'on voit « confirmation_titre » se remarque et se corrige ; un e-mail
    avec un titre vide part sans que personne ne le sache.
    """

    def dire(self, cle: str, **variables) -> str:
        modele = self.get(cle, cle)
        try:
            return modele.format(**variables)
        except (KeyError, IndexError):
            return modele


def textes(langue: str | None) -> Textes:
    """Le catalogue de cette langue, francais par defaut."""
    return Textes(CATALOGUES.get(langue or "", FR))
