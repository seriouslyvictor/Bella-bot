#!/bin/sh
set -eu

# The official image runs this automatically only for an empty data volume; it
# is idempotent so operators can rerun it to reconcile retained roles/ACLs.
# Passwords are passed as psql variables so they are quoted as SQL literals,
# never interpolated into SQL by the shell.
psql --set ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname postgres \
  --set postgres_user="$POSTGRES_USER" \
  --set postgres_password="$POSTGRES_PASSWORD" \
  --set bella_password="$BELLA_DB_PASSWORD" \
  --set evolution_password="$EVOLUTION_DB_PASSWORD" <<'EOSQL'
SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L',
    :'postgres_user',
    :'postgres_password'
) \gexec

SELECT format('CREATE ROLE bella LOGIN PASSWORD %L', :'bella_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bella') \gexec
SELECT format('ALTER ROLE bella WITH LOGIN PASSWORD %L', :'bella_password') \gexec

SELECT format('CREATE ROLE evolution LOGIN PASSWORD %L', :'evolution_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'evolution') \gexec
SELECT format('ALTER ROLE evolution WITH LOGIN PASSWORD %L', :'evolution_password') \gexec

SELECT 'CREATE DATABASE bella OWNER bella'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'bella') \gexec
SELECT 'CREATE DATABASE evogo_auth OWNER evolution'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'evogo_auth') \gexec
SELECT 'CREATE DATABASE evogo_users OWNER evolution'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'evogo_users') \gexec

ALTER DATABASE bella OWNER TO bella;
ALTER DATABASE evogo_auth OWNER TO evolution;
ALTER DATABASE evogo_users OWNER TO evolution;

REVOKE CONNECT, TEMPORARY ON DATABASE bella FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE evogo_auth FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE evogo_users FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE postgres FROM PUBLIC;

GRANT CONNECT, TEMPORARY ON DATABASE bella TO bella;
GRANT CONNECT, TEMPORARY ON DATABASE evogo_auth, evogo_users TO evolution;
-- Evolution Go checks for its databases through the maintenance database at
-- startup, but does not need permission to create arbitrary databases.
GRANT CONNECT ON DATABASE postgres TO evolution;
EOSQL
