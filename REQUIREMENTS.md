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
docker run --rm --platform linux/riscv64 registry.opensuse.org/opensuse/tumbleweed:latest uname -m
```

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

The full 219-package RISC-V dataset is expected outside the Git repository. Set:

```bash
export EVIDENT_DATA_ROOT=/path/to/obs_data/home_lalala123_RISCV_219
```

If unset, the repository uses the committed sample package under `dataset/obs_data/risc_v`.

## LLM Requirements

The full repair loop requires an OpenAI-compatible chat-completions endpoint:

```bash
OPENAI_API_KEY="..."
OPENAI_API_BASE_URL="..."
```

The fast smoke test does not require LLM credentials.
