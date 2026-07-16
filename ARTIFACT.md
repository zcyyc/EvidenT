# Artifact Evaluation Guide

This guide is the reviewer-facing checklist for the EvidenT artifact.

## Status

EvidenT is intended to support the **Functional** and **Reusable** artifact expectations:

- Functional: `scripts/smoke_test.py` checks configuration, imports core runtime dependencies, parses a package spec, and can optionally invoke the build validator.
- Reusable: validation is selected by configuration. The original OBS backend is retained, while Docker is the default backend for local/server-side reproduction.

The artifact and separate 219-package dataset are distributed through the
[DOI-backed Zenodo record](https://doi.org/10.5281/zenodo.20972389), supporting
the **Available** expectation.
The current archived version incorporates the kick-the-tires feedback on the
initial Docker validation case.

## Requirements

- Python 3.11+
- `uv`
- Docker with Linux containers
- For RISC-V Docker validation: binfmt/qemu support for `linux/riscv64`; QEMU 9.2 or newer is recommended for the submitted openSUSE RISC-V image
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

This uses the reduced `failed_python-stomper` case by default. The unrepaired
package is expected to fail in `%check`; the smoke test succeeds when the Docker
validator reaches that expected package-level test failure.

No LLM endpoint or OBS credentials are required for this test. The initial
artifact version selected the larger `postquantumcryptoengine` example, which
could stop in `%build` before reaching a stable smoke-test checkpoint. The
current version instead uses the reduced case above and recognizes only its
expected `%check` failure as a successful validator smoke test.

The complete credential-free sequence is also available as one command:

```bash
bash scripts/reproduce_reduced.sh
```

## Reproduction Scopes

| Scope | Credentials | Expected output |
|:------|:------------|:----------------|
| Basic smoke test | None | `lightweight_imports=ok`, `spec_parser=ok`, `smoke_test=ok` |
| Reduced Docker/RISC-V validation | None | `validator_reached_expected_check_failure=ok`, `smoke_test=ok` |
| Full repair loop with Docker | OpenAI-compatible LLM endpoint | Logs under `auto_repair_log_files/` and summaries under `auto_repair_results/` |
| Paper-aligned OBS reproduction | OpenAI-compatible LLM endpoint and reviewer-owned OBS credentials | The same repair outputs plus OBS build results |

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
uv run python scripts/validate_package.py \
  dataset/obs_data/risc_v_reduced/failed_python-stomper \
  --package-name failed_python-stomper
```

For RISC-V validation on an x86 host, enable binfmt first:

```bash
docker run --rm --privileged tonistiigi/binfmt --install riscv64
docker run --rm --platform linux/riscv64 evident-opensuse-riscv64:latest uname -m
```

Recent openSUSE userspace can use the `openat2` syscall. Host QEMU versions
older than 9.2, including common distribution packages such as Ubuntu 24.04 QEMU
8.2 and Debian 12 QEMU 7.2, may fail with:

```text
tar: ...: Cannot open: Function not implemented
```

Check the validator image with:

```bash
docker run --rm \
  --platform linux/riscv64 \
  -v "$PWD/dataset/obs_data/risc_v_reduced/failed_python-stomper:/workspace:rw" \
  -w /workspace \
  evident-opensuse-riscv64:latest \
  bash -lc 'set -e; uname -m; rm -rf /tmp/tar-test; mkdir -p /tmp/tar-test; cd /tmp/tar-test; tar -xzf /workspace/stomper-0.4.3.tar.gz; echo tar_ok'
```

If this check fails, install or re-register a recent static qemu-riscv64
emulator:

```bash
docker pull tonistiigi/binfmt:latest
docker run --privileged --rm tonistiigi/binfmt --install riscv64
```

For repeated RISC-V package validation, prebuild the validator image:

```bash
bash scripts/build_validator_image.sh evident-opensuse-riscv64:latest
```

Then set `docker.image: "evident-opensuse-riscv64:latest"` and `docker.refresh: false` in `config/paths.yaml`.

## Full Repair Loop

```bash
cp .env.example .env
# fill OPENAI_API_KEY, OPENAI_API_BASE_URL, and LLM_MODEL
uv run python client.py
```

Use `EVIDENT_PACKAGES` or `EVIDENT_PACKAGE_LIMIT` to keep runs bounded:

```bash
EVIDENT_PACKAGES=failed_python-stomper uv run python client.py
EVIDENT_PACKAGE_LIMIT=3 uv run python client.py
```

## OBS Backend

Set `validator.backend: "obs"` in `config/paths.yaml` and fill `config/obs_meta.yaml`. See
`OBS_GUIDE.md` for a reviewer-owned OBS project setup, RISC-V repository
configuration, package upload, and build-log inspection workflow. The MCP tool
interface remains the same:

1. `upload_file_to_obs_tool`
2. `check_build_result`

For full-dataset validation, create empty OBS package placeholders first.

The reviewer-owned project must already define a `standard/riscv64` build
target as described in `OBS_GUIDE.md`; the bulk uploader intentionally does not
modify project-level build targets.

After confirming that target, create the placeholders:

```bash
uv run python scripts/obs_bulk_upload.py \
  --root /path/to/EvidenT-riscv-219-dataset/packages \
  --manifest /path/to/EvidenT-riscv-219-dataset/package_manifest.txt \
  --project "$OBS_PROJECT" \
  --create-only \
  --jobs 8
```

EvidenT then uploads the complete repaired package directory for each selected
package and polls OBS for the build result.

Local dataset directories may use the `failed_` prefix to mark known failing
inputs. OBS source package names should not include this prefix; EvidenT maps
local names such as `failed_python-stomper` to OBS package `python-stomper`
automatically for upload and status polling.

## Expected Outputs

- Runtime logs: `auto_repair_log_files/`
- Final repair summaries: `auto_repair_results/`
- Temporary package workspaces: `temp_workspace/`
- Docker failure logs: `temp_workspace/<package>/log_failed.txt`

## Interpretation Of Reported Results

The result table in `README.md` reports the submitted GPT-5-mini evaluation.
The sample `obs_log_*.txt` files are original failing build logs supplied as
inputs to EvidenT, rather than post-repair outcomes. In particular,
`postquantumcryptoengine` is recorded as successfully repaired, consistently
with the repair log and the paper's case study.
