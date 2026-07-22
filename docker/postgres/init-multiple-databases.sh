#!/bin/sh
set -eu

create_database() {
  database_name="$1"
  role_name="$2"
  role_password="$3"

  psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    --set=database_name="$database_name" \
    --set=role_name="$role_name" \
    --set=role_password="$role_password" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role_name', :'role_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_name')\gexec

SELECT format('CREATE DATABASE %I OWNER %I ENCODING %L TEMPLATE template0', :'database_name', :'role_name', 'UTF8')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name')\gexec

SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'database_name')\gexec
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', :'database_name', :'role_name')\gexec
SELECT format('ALTER ROLE %I SET timezone TO %L', :'role_name', 'UTC')\gexec
SQL
}

create_database "${IFACEOFF_DB_NAME:-ifaceoff_app}" "${IFACEOFF_DB_USER:-ifaceoff_app}" "${IFACEOFF_DB_PASSWORD:-ifaceoff-app-change-me}"
create_database "${AGENT_DB_NAME:-ifaceoff_agent}" "${AGENT_DB_USER:-ifaceoff_agent}" "${AGENT_DB_PASSWORD:-ifaceoff-agent-change-me}"
create_database "${LITELLM_DB_NAME:-litellm}" "${LITELLM_DB_USER:-litellm}" "${LITELLM_DB_PASSWORD:-litellm-change-me}"
create_database "${LANGFUSE_DB_NAME:-langfuse}" "${LANGFUSE_DB_USER:-langfuse}" "${LANGFUSE_DB_PASSWORD:-langfuse-change-me}"
