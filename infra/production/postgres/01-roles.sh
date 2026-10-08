#!/bin/sh
# ---------------------------------------------------------------------------
# Les deux roles sur lesquels repose l'isolation multi-tenant — production.
#
#   salon_app   : NOBYPASSRLS, ne possede aucune table. Tout le trafic
#                 applicatif passe par lui ; les politiques RLS s'appliquent
#                 a lui sans exception possible.
#   salon_admin : proprietaire des tables, BYPASSRLS. Migrations, admin
#                 plateforme et taches Celery inter-tenants.
#
# Ce que ce fichier change par rapport a infra/postgres/init/01-roles.sql :
#
#   - les mots de passe viennent de l'environnement, jamais du depot ;
#   - aucun des deux roles n'a CREATEDB. En developpement il sert a la suite
#     de tests, qui cree sa propre base ; ici, un role applicatif capable de
#     creer des bases est une capacite offerte a qui le compromettrait ;
#   - `GRANT salon_app TO salon_admin` disparait pour la meme raison : il
#     n'existe que pour la base de test.
#
# Les noms des roles, eux, ne changent pas : deux migrations les citent
# (apps/common/rls.py, billing 0003).
#
# Ne s'execute qu'a la creation du volume, par l'image officielle de
# Postgres. Changer un mot de passe ensuite se fait avec `ALTER ROLE`.
#
# Pas de `set -eu` ici, et c'est delibere. L'image *execute* ce fichier s'il
# est executable, mais le *source* sinon — ce qui arrive des qu'il a ete
# versionne depuis Windows, sans le bit x. Source, un `set -u` s'etendrait
# au script d'entree de Postgres lui-meme et le ferait echouer plus loin, sur
# une de ses propres variables. Les deux verifications ci-dessous arretent
# tout dans les deux cas, et `ON_ERROR_STOP` fait sortir psql en erreur.
# ---------------------------------------------------------------------------

: "${SALON_ADMIN_PASSWORD:?manquant}"
: "${SALON_APP_PASSWORD:?manquant}"

# Les mots de passe passent en variables psql, jamais dans le texte SQL :
# `:'nom'` les cite correctement quel que soit leur contenu.
psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v admin_pw="$SALON_ADMIN_PASSWORD" \
     -v app_pw="$SALON_APP_PASSWORD" <<'SQL'
CREATE ROLE salon_admin LOGIN PASSWORD :'admin_pw' BYPASSRLS;
CREATE ROLE salon_app LOGIN PASSWORD :'app_pw' NOBYPASSRLS;

ALTER DATABASE salon OWNER TO salon_admin;
ALTER SCHEMA public OWNER TO salon_admin;
GRANT USAGE ON SCHEMA public TO salon_app;

-- Les tables naissent pendant les migrations, creees par salon_admin :
-- salon_app doit recevoir d'office les droits de lecture et d'ecriture sur
-- tout ce qui sera cree, et rien de plus — ni DDL, ni TRUNCATE.
ALTER DEFAULT PRIVILEGES FOR ROLE salon_admin IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO salon_app;
ALTER DEFAULT PRIVILEGES FOR ROLE salon_admin IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO salon_app;
SQL
