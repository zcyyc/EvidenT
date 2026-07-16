# Requirements

## Tested Host Setup

- macOS or Linux host with Python 3.11+
- `uv` for Python environment management
- Docker with Linux containers
- At least 20 GB free disk space for the full dataset and temporary package workspaces

## Architecture

The included dataset and default configuration target RISC-V package builds:

- Target ISA: `riscv64`
- Docker platform: inferred as `linux/riscv64`
- Default build image: `evident-opensuse-riscv64:latest`

For RISC-V validation on an x86_64 or arm64 host, Docker must support qemu/binfmt:

```bash
docker run --rm --privileged tonistiigi/binfmt --install riscv64
docker run --rm --platform linux/riscv64 evident-opensuse-riscv64:latest uname -m
```

QEMU 9.2 or newer is recommended for the submitted openSUSE RISC-V validator
image. Recent openSUSE userspace can use the `openat2` syscall, which older host
qemu-riscv64 versions do not implement. Ubuntu 24.04 commonly ships QEMU 8.2
and Debian 12 commonly ships QEMU 7.2; these versions may fail during archive
extraction with:

```text
tar: ...: Cannot open: Function not implemented
```

Check the loaded validator image with:

```bash
docker run --rm \
  --platform linux/riscv64 \
  -v "$PWD/dataset/obs_data/risc_v_reduced/failed_python-stomper:/workspace:rw" \
  -w /workspace \
  evident-opensuse-riscv64:latest \
  bash -lc 'set -e; uname -m; rm -rf /tmp/tar-test; mkdir -p /tmp/tar-test; cd /tmp/tar-test; tar -xzf /workspace/stomper-0.4.3.tar.gz; echo tar_ok'
```

If the check fails, install or re-register a recent static qemu-riscv64
emulator:

```bash
docker pull tonistiigi/binfmt:latest
docker run --privileged --rm tonistiigi/binfmt --install riscv64
```

Re-run the binfmt command after host reboot if registrations are reset. If a
registry mirror serves a stale `tonistiigi/binfmt` image, pull an explicit
recent tag or install `qemu-user` / `qemu-user-static` 9.2 or newer from the host
distribution or backports and re-register binfmt.

For long or repeated runs, use the preheated validator image built by:

```bash
bash scripts/build_validator_image.sh evident-opensuse-riscv64:latest
```

The submitted artifact archive includes a saved copy of this image:

```bash
docker load -i images/evident-opensuse-riscv64.tar.gz
```

The preheated image avoids running `zypper` during each RISC-V validation case,
which improves reliability under qemu-riscv64.

## Software Dependencies

Python dependencies are captured in:

- `pyproject.toml`
- `requirements.txt`
- `uv.lock`

Install with:

```bash
uv sync
```

## Data Requirements

The full 219-package RISC-V dataset is distributed as a separate archive. Set:

```bash
export EVIDENT_DATA_ROOT=/path/to/EvidenT-riscv-219-dataset/packages
```

If unset, the repository uses the committed sample package under `dataset/obs_data/risc_v`.

## LLM Requirements

The full repair loop requires an OpenAI-compatible chat-completions endpoint:

```bash
OPENAI_API_KEY="..."
OPENAI_API_BASE_URL="..."
```

The fast smoke test does not require LLM credentials.
