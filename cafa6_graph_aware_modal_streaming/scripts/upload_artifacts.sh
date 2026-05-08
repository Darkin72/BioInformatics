#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_DIR="${1:-./cafa6_graph_aware_artifacts}"
VOLUME_NAME="${CAFA6_MODAL_VOLUME:-cafa6-artifacts}"
REMOTE_DIR="/cafa6_graph_aware_artifacts"

if [ ! -f "${ARTIFACT_DIR}/config.json" ]; then
  echo "Missing ${ARTIFACT_DIR}/config.json"
  exit 1
fi

if [ ! -f "${ARTIFACT_DIR}/go_terms.json" ]; then
  echo "Missing ${ARTIFACT_DIR}/go_terms.json"
  exit 1
fi

if [ ! -d "${ARTIFACT_DIR}/branch_checkpoints" ] && [ ! -f "${ARTIFACT_DIR}/graph_aware_models.pt" ]; then
  echo "Expected branch_checkpoints/ or graph_aware_models.pt in ${ARTIFACT_DIR}"
  exit 1
fi

if ! modal volume ls | awk '{print $1}' | grep -Fxq "${VOLUME_NAME}"; then
  modal volume create "${VOLUME_NAME}"
fi

modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/config.json" "${REMOTE_DIR}/config.json"
modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/go_terms.json" "${REMOTE_DIR}/go_terms.json"
modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/go_metadata.json" "${REMOTE_DIR}/go_metadata.json"

if [ -d "${ARTIFACT_DIR}/branch_checkpoints" ]; then
  modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/branch_checkpoints" "${REMOTE_DIR}/branch_checkpoints"
fi

if [ -f "${ARTIFACT_DIR}/graph_aware_models.pt" ]; then
  modal volume put "${VOLUME_NAME}" "${ARTIFACT_DIR}/graph_aware_models.pt" "${REMOTE_DIR}/graph_aware_models.pt"
fi

modal volume ls "${VOLUME_NAME}" "${REMOTE_DIR}"
modal volume ls "${VOLUME_NAME}" "${REMOTE_DIR}/branch_checkpoints" || true
