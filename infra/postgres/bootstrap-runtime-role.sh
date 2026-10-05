#!/bin/sh
set -eu

: "${POSTGRES_DB:=ai_rxos}"
: "${POSTGRES_ADMIN_USER:=${POSTGRES_USER:-ai_rxos}}"
: "${POSTGRES_ADMIN_PASSWORD:=${POSTGRES_PASSWORD:-changeme}}"
: "${POSTGRES_APP_USER:=ai_rxos_app}"
: "${POSTGRES_APP_PASSWORD:=changeme_app}"
: "${POSTGRES_HOST:=127.0.0.1}"

until pg_isready -h "$POSTGRES_HOST" -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB"; do
  sleep 1
done

PGPASSWORD="$POSTGRES_ADMIN_PASSWORD" psql \
  -h "$POSTGRES_HOST" \
  -U "$POSTGRES_ADMIN_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -v runtime_db="$POSTGRES_DB" \
  -v runtime_admin="$POSTGRES_ADMIN_USER" \
  -v runtime_user="$POSTGRES_APP_USER" \
  -v runtime_password="$POSTGRES_APP_PASSWORD" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime_user') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'runtime_user', :'runtime_password');
  ELSE
    EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS', :'runtime_user', :'runtime_password');
  END IF;
END
$$;
ALTER ROLE :runtime_user NOSUPERUSER NOBYPASSRLS CREATEROLE CREATEDB;
GRANT pg_signal_backend TO :runtime_user;
GRANT CONNECT ON DATABASE :runtime_db TO :runtime_user;
GRANT CREATE ON DATABASE :runtime_db TO :runtime_user;
CREATE SCHEMA IF NOT EXISTS canonical AUTHORIZATION :runtime_user;
ALTER SCHEMA canonical OWNER TO :runtime_user;
GRANT USAGE, CREATE ON SCHEMA canonical TO :runtime_user;
GRANT USAGE ON SCHEMA public TO :runtime_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :runtime_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :runtime_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO :runtime_user;
ALTER DEFAULT PRIVILEGES FOR ROLE :runtime_admin IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :runtime_user;
ALTER DEFAULT PRIVILEGES FOR ROLE :runtime_admin IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO :runtime_user;
ALTER DEFAULT PRIVILEGES FOR ROLE :runtime_admin IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO :runtime_user;
SQL
