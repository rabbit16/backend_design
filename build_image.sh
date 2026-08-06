#!/usr/bin/env bash
set -eu

IMAGE_NAME="${IMAGE_NAME:-ai-fastapi-backend}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-}"
BUILD_TIME="$(date +%Y%m%d-%H%M%S)"
TAG="${IMAGE_TAG:-${BUILD_TIME}}"

# 国内加速（可用环境变量覆盖）
# 基础镜像：DaoCloud 代理 Docker Hub
PYTHON_BASE_IMAGE="${PYTHON_BASE_IMAGE:-docker.m.daocloud.io/library/python:3.11-slim}"
# apt：中科大 Debian
APT_MIRROR="${APT_MIRROR:-mirrors.ustc.edu.cn}"
# pip：中科大 PyPI
PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.ustc.edu.cn/pypi/simple}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-mirrors.ustc.edu.cn}"

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
echo "  base=${PYTHON_BASE_IMAGE}"
echo "  apt=${APT_MIRROR}"
echo "  pip=${PIP_INDEX_URL}"

docker build \
  --pull \
  --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" \
  --build-arg "APT_MIRROR=${APT_MIRROR}" \
  --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL}" \
  --build-arg "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}" \
  --label "build.time=${BUILD_TIME}" \
  --label "app.name=${IMAGE_NAME}" \
  -t "${FULL_IMAGE_NAME}" \
  -t "${LATEST_IMAGE_NAME}" \
  .

echo "Built images:"
echo "  ${FULL_IMAGE_NAME}"
echo "  ${LATEST_IMAGE_NAME}"
