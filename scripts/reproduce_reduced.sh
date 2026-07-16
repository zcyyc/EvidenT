#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

IMAGE="evident-opensuse-riscv64:latest"
IMAGE_ARCHIVE="images/evident-opensuse-riscv64.tar.gz"

command -v docker >/dev/null || {
  echo "ERROR: Docker is required for reduced RISC-V validation." >&2
  exit 2
}
command -v uv >/dev/null || {
  echo "ERROR: uv is required. See REQUIREMENTS.md." >&2
  exit 2
}

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  if [[ ! -f "$IMAGE_ARCHIVE" ]]; then
    echo "ERROR: $IMAGE is not loaded and $IMAGE_ARCHIVE is missing." >&2
    exit 2
  fi
  docker load -i "$IMAGE_ARCHIVE"
fi

echo "Checking the submitted RISC-V validator image..."
docker run --rm --platform linux/riscv64 "$IMAGE" uname -m

echo "Installing the locked Python environment..."
uv sync

echo "Running the credential-free framework smoke test..."
uv run python scripts/smoke_test.py

echo "Running the reduced RISC-V validator smoke test..."
uv run python scripts/smoke_test.py --validate
