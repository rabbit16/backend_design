#!/usr/bin/env bash
set -eu

IMAGE_NAME="${IMAGE_NAME:-ai-fastapi-backend}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-}"
BUILD_TIME="$(date +%Y%m%d-%H%M%S)"
TAG="${IMAGE_TAG:-${BUILD_TIME}}"

if [ -n "$IMAGE_REGISTRY" ]; then
  FULL_IMAGE_NAME="${IMAGE_REGISTRY}/${IMAGE_NAME}:${TAG}"
else
  FULL_IMAGE_NAME="${IMAGE_NAME}:${TAG}"
fi

LATEST_IMAGE_NAME="${IMAGE_NAME}:latest"
if [ -n "$IMAGE_REGISTRY" ]; then
  LATEST_IMAGE_NAME="${IMAGE_REGISTRY}/${IMAGE_NAME}:latest"
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building image: ${FULL_IMAGE_NAME}"
docker build \
  --pull \
  --label "build.time=${BUILD_TIME}" \
  --label "app.name=${IMAGE_NAME}" \
  -t "${FULL_IMAGE_NAME}" \
  -t "${LATEST_IMAGE_NAME}" \
  .

echo "Built images:"
echo "  ${FULL_IMAGE_NAME}"
echo "  ${LATEST_IMAGE_NAME}"
