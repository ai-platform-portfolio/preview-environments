#!/bin/sh
# Disposable Compose fixture only; production roles belong to chart values.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=migrator_password="$MIGRATOR_PASSWORD" \
  --set=runtime_password="$RUNTIME_PASSWORD" <<'SQL'
CREATE ROLE app_owner NOLOGIN;
CREATE ROLE app_migrator LOGIN PASSWORD :'migrator_password' IN ROLE app_owner;
CREATE ROLE app_runtime LOGIN PASSWORD :'runtime_password';
CREATE DATABASE app OWNER app_owner;
REVOKE ALL ON DATABASE app FROM PUBLIC;
GRANT CONNECT ON DATABASE app TO app_migrator, app_runtime;
\connect app
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO app_migrator;
GRANT USAGE ON SCHEMA public TO app_runtime;
-- Only subsequently created application tables receive runtime DML grants.
-- Atlas revision metadata lives in a separate, private schema.
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator IN SCHEMA public
  GRANT SELECT, INSERT ON TABLES TO app_runtime;
SQL
