#!/bin/bash

set -e

set -u

# 아직 만들 데이터베이스가 없음
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
EOSQL
