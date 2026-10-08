"""Les domaines personnalises relies, un par ligne.

Lu par `infra/production/scripts/synchroniser-domaines.sh`, qui en tire la
route du proxy d'entree (Traefik, en mode Coolify). Un domaine en pause y
reste : il doit toujours arriver jusqu'au site, qui renvoie alors ses
visiteurs vers le sous-domaine du salon.
"""

from django.core.management.base import BaseCommand

from apps.domains.personnalises import domaines_verifies


class Command(BaseCommand):
    help = "Affiche les domaines personnalisés vérifiés, un par ligne."

    def handle(self, *args, **options):
        for nom in domaines_verifies():
            self.stdout.write(nom)
