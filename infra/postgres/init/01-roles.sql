-- ---------------------------------------------------------------------------
-- Les deux roles sur lesquels repose l'isolation multi-tenant.
--
--   salon_app   : NOBYPASSRLS, ne possede aucune table. C'est la connexion
--                 utilisee par tout le trafic applicatif. Les politiques RLS
--                 s'appliquent a lui sans exception possible.
--   salon_admin : proprietaire des tables, BYPASSRLS. Reserve aux migrations,
--                 a l'admin plateforme et aux taches Celery inter-tenants.
--
-- Ne s'execute qu'a la creation du volume Postgres. Pour le rejouer :
--   docker compose down -v && docker compose up -d
-- ---------------------------------------------------------------------------

CREATE ROLE salon_admin LOGIN PASSWORD 'salon_admin' BYPASSRLS CREATEDB;

-- CREATEDB est necessaire uniquement pour que la suite de tests puisse creer
-- sa base test_salon. A retirer sur un deploiement reel.
CREATE ROLE salon_app LOGIN PASSWORD 'salon_app' NOBYPASSRLS CREATEDB;

ALTER DATABASE salon OWNER TO salon_admin;

\connect salon

ALTER SCHEMA public OWNER TO salon_admin;
GRANT USAGE ON SCHEMA public TO salon_app;

-- Les tables sont creees par salon_admin pendant les migrations ; salon_app
-- doit recevoir automatiquement les droits DML sur tout ce qui sera cree.
ALTER DEFAULT PRIVILEGES FOR ROLE salon_admin IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO salon_app;

ALTER DEFAULT PRIVILEGES FOR ROLE salon_admin IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO salon_app;

-- La suite de tests cree sa propre base (test_salon) via le role salon_app,
-- qui devient donc proprietaire des tables de test. Pour que l'alias `admin`
-- puisse quand meme y travailler, salon_admin herite des droits de salon_app.
-- Les attributs de role (BYPASSRLS) ne se transmettent pas par appartenance :
-- salon_app ne gagne aucun privilege dans l'operation.
GRANT salon_app TO salon_admin;
