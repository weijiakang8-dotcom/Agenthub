#!/usr/bin/env bash
set -euo pipefail

# 用法：
#   REGISTRY=ghcr.io ORG=weijiakang TAG=latest ./deploy/k8s-deploy.sh
REGISTRY="${REGISTRY:-ghcr.io}"
ORG="${ORG:-weijiakang}"
TAG="${TAG:-latest}"
NAMESPACE="${NAMESPACE:-agenthub}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "准备 K8s manifests（镜像: ${REGISTRY}/${ORG}/agenthub-*:${TAG}）"
cp "$ROOT_DIR"/k8s/*.yaml "$WORK_DIR"/
rm -f "$WORK_DIR/01-secrets.example.yaml" "$WORK_DIR/external-secret.example.yaml"

find "$WORK_DIR" -name '*.yaml' -print0 | xargs -0 perl -pi \
  -e "s|ghcr.io/weijiakang|${REGISTRY}/${ORG}|g;" \
  -e "s|:latest|:${TAG}|g"

echo "创建 namespace"
kubectl apply -f "$WORK_DIR/00-namespace.yaml"

echo "创建 Secret（从本地 .env）"
(cd "$ROOT_DIR" && NAMESPACE="$NAMESPACE" ENV_FILE="${ENV_FILE:-.env}" ./scripts/create-k8s-secret.sh)

echo "应用 manifests"
kubectl apply -f "$WORK_DIR"

echo "等待部署就绪"
kubectl -n "$NAMESPACE" rollout status deploy/backend --timeout=180s
kubectl -n "$NAMESPACE" rollout status deploy/frontend --timeout=180s
kubectl -n "$NAMESPACE" rollout status deploy/celery-worker --timeout=180s

echo "当前 Pod 状态："
kubectl -n "$NAMESPACE" get pods
echo "部署完成。"
