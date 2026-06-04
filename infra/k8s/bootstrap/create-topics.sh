#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"
KAFKA_TOPICS_BIN="${KAFKA_TOPICS_BIN:-/opt/kafka/bin/kafka-topics.sh}"

until "${KAFKA_TOPICS_BIN}" --bootstrap-server "${BOOTSTRAP_SERVER}" --list >/dev/null 2>&1; do
  echo "Waiting for Kafka at ${BOOTSTRAP_SERVER}..."
  sleep 5
done

topics=(
  "protein.raw-input.v1"
  "protein.validated-input.v1"
  "protein.prediction-result.v1"
  "protein.dead-letter.v1"
  "request_status"
  "prediction_result"
  "dead_letter"
)

for topic in "${topics[@]}"; do
  "${KAFKA_TOPICS_BIN}" \
    --bootstrap-server "${BOOTSTRAP_SERVER}" \
    --create \
    --if-not-exists \
    --topic "${topic}" \
    --partitions 3 \
    --replication-factor 3 \
    --config min.insync.replicas=2
done

"${KAFKA_TOPICS_BIN}" --bootstrap-server "${BOOTSTRAP_SERVER}" --list
