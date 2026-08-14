#!/usr/bin/env bash
set -euo pipefail

# 用法：
#   REGISTRY=ghcr.io ORG=weijiakang TAG=v0.1.0 PUSH=1 ./scripts/build-images.sh
REGISTRY="${REGISTRY:-ghcr.io}"
ORG="${ORG:-weijiakang}"
TAG="${TAG:-latest}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_IMAGE="${REGISTRY}/${ORG}/agenthub-backend:${TAG}"
FRONTEND_IMAGE="${REGISTRY}/${ORG}/agenthub-frontend:${TAG}"

echo "Building backend image: ${BACKEND_IMAGE}"
docker build -f docker/Dockerfile.backend -t "${BACKEND_IMAGE}" .

echo "Building frontend image: ${FRONTEND_IMAGE}"
docker build -f docker/Dockerfile.frontend -t "${FRONTEND_IMAGE}" .

if [[ "${PUSH:-0}" == "1" ]]; then
  echo "Pushing images..."
  docker push "${BACKEND_IMAGE}"
  docker push "${FRONTEND_IMAGE}"
fi

echo "Done."
