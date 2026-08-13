-- infra/grants.sql — idempotent Postgres grants (docs/01, the one deliberate
-- exception to pure declarative IaC). Run post-provision by deploy.ps1, AFTER the
-- server and the `mlflow`/`results` databases exist, as the AAD administrator.
--
-- Per-workload objectIds are injected by deploy.ps1 from `terraform output`:
--   psql "host=... dbname=postgres ..." \
--     -v oid_jobs_train=... -v oid_jobs_batch=... -v oid_mlflow=... -v oid_dashboard=... \
--     -f grants.sql
--
-- Each workload identity becomes an Entra-mapped Postgres role with the LEAST
-- privilege it needs, on ONLY its database(s). objectType 'service' = managed
-- identity. Idempotent: role creation is guarded by NOT EXISTS.

\set ON_ERROR_STOP on

-- 1) Create per-workload principals mapped to their managed-identity objectIds.
SELECT pgaadauth_create_principal_with_oid('id-jobs-train', :'oid_jobs_train', 'service', false, false)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'id-jobs-train');

SELECT pgaadauth_create_principal_with_oid('id-jobs-batch', :'oid_jobs_batch', 'service', false, false)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'id-jobs-batch');

SELECT pgaadauth_create_principal_with_oid('id-mlflow', :'oid_mlflow', 'service', false, false)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'id-mlflow');

SELECT pgaadauth_create_principal_with_oid('id-dashboard', :'oid_dashboard', 'service', false, false)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'id-dashboard');

-- 2) Database CONNECT grants (grantable from any database).
GRANT CONNECT ON DATABASE mlflow  TO "id-jobs-train";
GRANT CONNECT ON DATABASE results TO "id-jobs-train";
GRANT CONNECT ON DATABASE results TO "id-jobs-batch";
GRANT CONNECT ON DATABASE mlflow  TO "id-mlflow";
GRANT CONNECT ON DATABASE results TO "id-dashboard";

-- 3) Per-database schema privileges (must run inside each database).

-- mlflow DB: id-mlflow owns/creates the registry+tracking tables; id-jobs-train
-- reads them.
\connect mlflow
GRANT USAGE, CREATE ON SCHEMA public TO "id-mlflow";
ALTER DEFAULT PRIVILEGES FOR ROLE "id-mlflow" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "id-mlflow";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO "id-jobs-train";
ALTER DEFAULT PRIVILEGES FOR ROLE "id-mlflow" IN SCHEMA public
  GRANT SELECT ON TABLES TO "id-jobs-train";

-- results DB: train/batch read+write; dashboard read-only. The `results` table
-- itself is created by the results migration in Chapter 04 (owned by id-jobs-train).
\connect results
GRANT USAGE, CREATE ON SCHEMA public TO "id-jobs-train";
GRANT USAGE ON SCHEMA public TO "id-jobs-batch";
GRANT USAGE ON SCHEMA public TO "id-dashboard";
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO "id-jobs-batch";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO "id-dashboard";
ALTER DEFAULT PRIVILEGES FOR ROLE "id-jobs-train" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE ON TABLES TO "id-jobs-batch";
ALTER DEFAULT PRIVILEGES FOR ROLE "id-jobs-train" IN SCHEMA public
  GRANT SELECT ON TABLES TO "id-dashboard";
