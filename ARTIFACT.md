# Artifact Evaluation Guide

This guide is the reviewer-facing checklist for the EvidenT artifact.

## Status

EvidenT is intended to support the **Functional** and **Reusable** artifact expectations:

- Functional: `scripts/smoke_test.py` checks configuration, imports core runtime dependencies, parses a package spec, and can optionally invoke the build validator.
- Reusable: validation is selected by configuration. The original OBS backend is retained, while Docker is the default backend for local/server-side reproduction.

The **Available** badge should be requested after the final artifact is placed on a DOI-backed archival repository.

## Requirements

- Python 3.11+
- `uv`
- Docker with Linux containers
- For RISC-V Docker validation: binfmt/qemu support for `linux/riscv64`
- An OpenAI-compatible LLM endpoint for full repair-loop runs

## Data

The full 219-package RISC-V dataset is distributed as a separate archive. Point
EvidenT to a local or mounted copy of the released dataset:

```bash
export EVIDENT_DATA_ROOT=/path/to/EvidenT-riscv-219-dataset/packages
```

The dataset archive includes `package_manifest.txt`. The 219 package directories
under `packages/` are selected from that manifest.

The repository also contains one small sample package under `dataset/obs_data/risc_v`.
The submitted artifact archive includes an additional reduced validation case
under `dataset/obs_data/risc_v_reduced`.

## 30-Minute Smoke Test

```bash
docker load -i images/evident-opensuse-riscv64.tar.gz
uv sync
uv run python scripts/smoke_test.py
```

Expected output includes:

```text
lightweight_imports=ok
spec_parser=ok
smoke_test=ok
```

To include the configured validator:

```bash
uv run python scripts/smoke_test.py --validate
```

## Reduced Reproduction Scope

Run one RISC-V Docker validation case:

```bash
uv run python scripts/validate_package.py \
  dataset/obs_data/risc_v_reduced/failed_python-stomper \
  --package-name failed_python-stomper
```

This unrepaired package is expected to fail in `%check` with deprecated
`assertEquals` calls. That result demonstrates that the artifact reaches the
package test suite inside the `linux/riscv64` Docker validator.

## Docker Backend

Docker validation runs an openSUSE container and executes `rpmbuild -ba`.
The submitted RISC-V configuration uses a preheated validator image and
`rpmbuild --nodeps` to avoid `zypper` stalls under qemu-riscv64.

```bash
uv run python scripts/validate_package.py dataset/obs_data/risc_v/failed_postquantumcryptoengine
```

For RISC-V validation on an x86 host, enable binfmt first:

```bash
docker run --rm --privileged tonistiigi/binfmt --install riscv64
docker run --rm --platform linux/riscv64 registry.opensuse.org/opensuse/tumbleweed:latest uname -m
```

For repeated RISC-V package validation, prebuild the validator image:

```bash
bash scripts/build_validator_image.sh evident-opensuse-riscv64:latest
```

Then set `docker.image: "evident-opensuse-riscv64:latest"` and `docker.refresh: false` in `config/paths.yaml`.

## Full Repair Loop

```bash
cp .env.example .env
# fill OPENAI_API_KEY and OPENAI_API_BASE_URL
uv run python client.py
```

Use `EVIDENT_PACKAGES` or `EVIDENT_PACKAGE_LIMIT` to keep runs bounded:

```bash
EVIDENT_PACKAGES=failed_python-stomper uv run python client.py
EVIDENT_PACKAGE_LIMIT=3 uv run python client.py
```

## OBS Backend

Set `validator.backend: "obs"` in `config/paths.yaml` and fill `config/obs_meta.yaml`. The MCP tool interface remains the same:

1. `upload_file_to_obs_tool`
2. `check_build_result`

## Expected Outputs

- Runtime logs: `auto_repair_log_files/`
- Final repair summaries: `auto_repair_results/`
- Temporary package workspaces: `temp_workspace/`
- Docker failure logs: `temp_workspace/<package>/log_failed.txt`
