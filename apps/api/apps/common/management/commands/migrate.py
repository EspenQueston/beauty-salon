"""`migrate` refuse de tourner sur le mauvais alias.

---------------------------------------------------------------------------
Le piege, et pourquoi il est silencieux
---------------------------------------------------------------------------

`TenantDatabaseRouter.allow_migrate` n'autorise les migrations que sur
`MIGRATION_DATABASE_ALIAS` - `admin` en developpement comme en production,
le seul role proprietaire des tables. C'est une bonne regle : elle empeche
qu'un `migrate` distrait cree des tables appartenant au role applicatif, qui
contournerait alors ses propres politiques RLS.

Mais quand le routeur refuse, Django **ne refuse pas**. Il execute chaque
operation en la transformant en no-op, puis inscrit la migration dans
`django_migrations` comme appliquee. La sortie affiche `... OK` pour chaque
ligne. Rien ne distingue un `migrate` qui a tout fait d'un `migrate` qui n'a
rien fait.

Le resultat est une base ou l'etat enregistre et l'etat reel divergent : la
colonne n'existe pas, mais Django est convaincu du contraire. Le symptome
arrive plus tard et ailleurs - un `ProgrammingError: column ... does not
exist` sur une requete sans rapport - et la reparation demande de
desenregistrer a la main (`migrate <app> <precedente> --fake`) avant de
rejouer sur le bon alias.

Le README le dit a trois endroits. Ca ne suffit pas : un avertissement que
l'outil ignore n'arrete personne au moment ou il se trompe.

---------------------------------------------------------------------------
Ce que fait cette commande
---------------------------------------------------------------------------

Rien, sauf s'arreter avant les degats. Elle compare l'alias demande a celui
que le routeur accepte et, s'ils different, leve une erreur qui donne la
commande a taper. Dans tous les autres cas elle delegue mot pour mot a
Django - y compris sous pytest, ou `MIGRATION_DATABASE_ALIAS` vaut `default`
et ou la comparaison passe donc d'elle-meme.
"""

from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.commands.migrate import Command as MigrateDeDjango


class Command(MigrateDeDjango):
    def handle(self, *args, **options):
        attendu = settings.MIGRATION_DATABASE_ALIAS
        demande = options.get("database")

        if demande != attendu:
            raise CommandError(
                f"Les migrations ne s'appliquent que sur l'alias « {attendu} » : "
                f"c'est le seul role proprietaire des tables.\n"
                f"L'alias « {demande} » serait accepte par Django, qui "
                f"enregistrerait les migrations sans en appliquer une seule.\n\n"
                f"    python manage.py migrate --database={attendu}"
            )

        return super().handle(*args, **options)
