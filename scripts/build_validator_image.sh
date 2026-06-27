#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${1:-evident-opensuse-riscv64:latest}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker build \
  --platform linux/riscv64 \
  -f "${ROOT_DIR}/docker/validator-riscv64.Dockerfile" \
  -t "${IMAGE_NAME}" \
  "${ROOT_DIR}"

printf 'Built %s\n' "${IMAGE_NAME}"
