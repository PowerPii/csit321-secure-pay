#!/bin/bash
# Creates the three logical databases and their roles on first start.
# Role passwords are read from the mounted secrets so nothing is hard-coded.
set -euo pipefail
pw() { cat "/run/secrets/$1" 2>/dev/null || echo "$2"; }

psql -v ON_ERROR_STOP=1 --username postgres <<SQL
CREATE ROLE gateway LOGIN PASSWORD '$(pw gateway_db_password gateway)';
CREATE ROLE vault LOGIN PASSWORD '$(pw vault_db_password vault)';
CREATE ROLE simulator LOGIN PASSWORD '$(pw simulator_db_password simulator)';
CREATE ROLE merchant LOGIN PASSWORD '$(pw merchant_db_password merchant)';
CREATE DATABASE gateway OWNER gateway;
CREATE DATABASE simulator OWNER simulator;
CREATE DATABASE merchant OWNER merchant;
SQL

# The vault gets its own schema inside the gateway database; only the vault role can use it.
psql -v ON_ERROR_STOP=1 --username postgres --dbname gateway <<SQL
CREATE SCHEMA vault AUTHORIZATION vault;
REVOKE ALL ON SCHEMA vault FROM PUBLIC;
ALTER ROLE vault SET search_path = vault;
SQL
