#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_DIR="${1:-./cafa6_high_performance_artifacts}"
VOLUME_NAME="${CAFA6_MODAL_VOLUME:-cafa6-artifacts}"
REMOTE_DIR="/cafa6_high_performance_artifacts"

if [ ! -f "${ARTIFACT_DIR}/config.json" ]; then
  echo "Missing ${ARTIFACT_DIR}/config.json"
  exit 1
fi

if [ ! -f "${ARTIFACT_DIR}/go_terms.json" ]; then
  echo "Missing ${ARTIFACT_DIR}/go_terms.json"
  exit 1
fi

if [ ! -d "${ARTIFACT_DIR}/branch_checkpoints" ] && [ ! -f "${ARTIFACT_DIR}/cafa6_high_performance_models.pt" ]; then
  echo "Expected branch_checkpoints/ or cafa6_high_performance_models.pt in ${ARTIFACT_DIR}"
  exit 1
fi

modal volume create "${VOLUME_NAME}" || true

modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/config.json" "${REMOTE_DIR}/config.json"
modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/go_terms.json" "${REMOTE_DIR}/go_terms.json"
modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/go_metadata.json" "${REMOTE_DIR}/go_metadata.json"

if [ -d "${ARTIFACT_DIR}/branch_checkpoints" ]; then
  modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/branch_checkpoints" "${REMOTE_DIR}/branch_checkpoints"
fi

if [ -f "${ARTIFACT_DIR}/cafa6_high_performance_models.pt" ]; then
  modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/cafa6_high_performance_models.pt" "${REMOTE_DIR}/cafa6_high_performance_models.pt"
fi

modal volume ls "${VOLUME_NAME}" "${REMOTE_DIR}"
modal volume ls "${VOLUME_NAME}" "${REMOTE_DIR}/branch_checkpoints" || true
