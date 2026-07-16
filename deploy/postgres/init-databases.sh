#!/bin/sh
set -eu

EVOLUTION_DB_CONNECTION_LIMIT="${EVOLUTION_DB_CONNECTION_LIMIT:-30}"
EVOLUTION_DB_IDLE_SESSION_TIMEOUT="${EVOLUTION_DB_IDLE_SESSION_TIMEOUT:-5min}"

# These values become SQL syntax below, so reject malformed capacity settings
# before psql sees them. The timeout units are PostgreSQL's duration units.
case "$EVOLUTION_DB_CONNECTION_LIMIT" in
  ''|*[!0-9]*)
    echo "EVOLUTION_DB_CONNECTION_LIMIT must be a positive integer" >&2
    exit 1
    ;;
esac
if [ "${#EVOLUTION_DB_CONNECTION_LIMIT}" -gt 9 ] || [ "$EVOLUTION_DB_CONNECTION_LIMIT" -le 0 ]; then
  echo "EVOLUTION_DB_CONNECTION_LIMIT must be a positive integer" >&2
  exit 1
fi
if [ "${#EVOLUTION_DB_IDLE_SESSION_TIMEOUT}" -gt 16 ] || \
   ! printf '%s\n' "$EVOLUTION_DB_IDLE_SESSION_TIMEOUT" | grep -Eq '^[1-9][0-9]*(ms|s|min|h|d)$'; then
  echo "EVOLUTION_DB_IDLE_SESSION_TIMEOUT must be a positive PostgreSQL duration (for example, 5min)" >&2
  exit 1
fi

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
  --set evolution_password="$EVOLUTION_DB_PASSWORD" \
  --set evolution_connection_limit="$EVOLUTION_DB_CONNECTION_LIMIT" \
  --set evolution_idle_session_timeout="$EVOLUTION_DB_IDLE_SESSION_TIMEOUT" <<'EOSQL'
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
ALTER ROLE evolution WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT :evolution_connection_limit PASSWORD :'evolution_password';
ALTER ROLE evolution SET idle_session_timeout TO :'evolution_idle_session_timeout';

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
