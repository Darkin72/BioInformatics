#!/usr/bin/env bash
set -euo pipefail

CASSANDRA_HOST="${CASSANDRA_HOST:-cassandra}"
CASSANDRA_PORT="${CASSANDRA_PORT:-9042}"

until cqlsh "${CASSANDRA_HOST}" "${CASSANDRA_PORT}" -e "DESCRIBE KEYSPACES" >/dev/null 2>&1; do
  echo "Waiting for Cassandra at ${CASSANDRA_HOST}:${CASSANDRA_PORT}..."
  sleep 5
done

cqlsh "${CASSANDRA_HOST}" "${CASSANDRA_PORT}" -f /schema.cql
echo "Cassandra schema initialized."
