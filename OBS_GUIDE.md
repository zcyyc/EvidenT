# OBS Backend Guide

This guide describes the paper-aligned validation path for EvidenT. The Docker
backend is intended for artifact smoke tests and reduced local validation. The
OBS backend is the authoritative path for full openSUSE package build
validation because OBS provides the project configuration, repository layering,
dependency resolution, scheduler, worker, and architecture-specific build root.

Use a reviewer-owned OBS account and project when reproducing this path. Do not
use author-owned project names or links in anonymous review material.

Official references:

- OBS user guide: https://openbuildservice.org/help/manuals/obs-user-guide/
- Basic OBS workflow: https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-basicworkflow
- osc command-line tool: https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-osc
- OBS build process: https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-build-process
- OBS build constraints: https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-build-constraints

## 1. Install and Configure `osc`

Install `osc` on a Linux machine:

```bash
sudo apt-get update
sudo apt-get install -y osc
```

Configure access to the public openSUSE OBS instance:

```bash
osc -A https://api.opensuse.org ls /
```

When prompted, enter the OBS username and password or API token. `osc` stores
the credentials in `~/.oscrc`.

## 2. Create a RISC-V Project

Choose a reviewer-owned project name:

```bash
export OBS_PROJECT='home:<your_obs_user>:EvidenT-AE'
```

Create or edit the project metadata:

```bash
cat > /tmp/evident-prj.xml <<'XML'
<project name="home:<your_obs_user>:EvidenT-AE">
  <title>EvidenT artifact evaluation</title>
  <description>Reviewer-owned project for EvidenT RISC-V package validation.</description>
  <repository name="standard">
    <path project="openSUSE:Factory:RISCV" repository="standard"/>
    <arch>riscv64</arch>
  </repository>
</project>
XML

osc -A https://api.opensuse.org meta prj "$OBS_PROJECT" -F /tmp/evident-prj.xml
```

Replace `home:<your_obs_user>:EvidenT-AE` inside the XML with the same value used
in `OBS_PROJECT`.

If `openSUSE:Factory:RISCV` is unavailable on the OBS instance, list available
targets and select the current openSUSE RISC-V project:

```bash
osc -A https://api.opensuse.org ls / | grep -i 'RISCV\|Factory'
osc -A https://api.opensuse.org meta prj openSUSE:Factory:RISCV
```

The important requirements are:

- repository name used by EvidenT: `standard`
- architecture used by EvidenT: `riscv64`
- a repository path that provides the openSUSE RISC-V build dependencies

## 3. Upload One Package Manually

This is a direct OBS sanity check independent of the EvidenT repair loop.

```bash
cd /tmp
osc -A https://api.opensuse.org checkout "$OBS_PROJECT"
cd "$OBS_PROJECT"

export LOCAL_PKG='failed_python-stomper'
export OBS_PKG='python-stomper'
osc mkpac "$OBS_PKG"
cp -a /path/to/EvidenT-issta2026-artifact/dataset/obs_data/risc_v_reduced/"$LOCAL_PKG"/* "$OBS_PKG"/

cd "$OBS_PKG"
osc addremove
osc commit -m "Add EvidenT validation package"
```

Check status and logs:

```bash
osc results
osc buildlogtail standard riscv64
```

The unrepaired reduced package is expected to fail in `%check` with deprecated
`assertEquals` calls. That means OBS reached the package's own test suite.

## 4. Configure EvidenT for OBS

Edit `config/paths.yaml`:

```yaml
validator:
  backend: "obs"
```

Edit `config/obs_meta.yaml`:

```yaml
obs:
  url: "https://api.opensuse.org"
  user_name: "<your_obs_user>"
  password: "<your_obs_password_or_token>"
  project: "home:<your_obs_user>:EvidenT-AE"
  repository: "standard"
  architecture: "riscv64"
```

Keep `config/obs_meta.yaml` private. Do not commit real OBS credentials.
`OBS_USERNAME`, `OBS_PASSWORD`, and `OBS_PROJECT` environment variables override
the corresponding YAML values, which is usually preferable on shared or
temporary servers.

## 5. Bulk Package Preparation

For the full 219-package dataset, use the bulk uploader instead of creating
packages one by one. The recommended OBS workflow is to create empty package
placeholders first. This avoids uploading and building all known-failing inputs
up front. During an EvidenT run, the repair loop uploads the complete repaired
package directory from `temp_workspace/<package>/` to the matching OBS package
and then polls the OBS build result.

The same script can also upload package source files directly. By default it
skips local logs and metadata such as `log_failed.txt`, `obs_log_*.txt`, and
`obs_meta_*.json`.

Use credentials from environment variables so they do not appear in the command:

```bash
export OBS_USERNAME='<your_obs_user>'
export OBS_PASSWORD='<your_obs_password_or_token>'
export OBS_PROJECT='home:<your_obs_user>:EvidenT-AE'
```

Dry-run the first few packages:

```bash
uv run python scripts/obs_bulk_upload.py \
  --root /path/to/EvidenT-riscv-219-dataset/packages \
  --manifest /path/to/EvidenT-riscv-219-dataset/package_manifest.txt \
  --limit 3 \
  --dry-run
```

Create empty OBS package placeholders for all 219 packages. Use `--jobs` to
parallelize the package metadata creation:

```bash
uv run python scripts/obs_bulk_upload.py \
  --root /path/to/EvidenT-riscv-219-dataset/packages \
  --manifest /path/to/EvidenT-riscv-219-dataset/package_manifest.txt \
  --project "$OBS_PROJECT" \
  --create-only \
  --jobs 8
```

If you instead want to upload the unrepaired package sources directly, omit
`--create-only`. This is useful for OBS sanity checks, but it will schedule
known-failing packages:

```bash
uv run python scripts/obs_bulk_upload.py \
  --root /path/to/EvidenT-riscv-219-dataset/packages \
  --manifest /path/to/EvidenT-riscv-219-dataset/package_manifest.txt \
  --project "$OBS_PROJECT"
```

Upload and trigger rebuilds:

```bash
uv run python scripts/obs_bulk_upload.py \
  --root /path/to/EvidenT-riscv-219-dataset/packages \
  --manifest /path/to/EvidenT-riscv-219-dataset/package_manifest.txt \
  --rebuild
```

For a reduced single-case check:

```bash
uv run python scripts/obs_bulk_upload.py \
  --root dataset/obs_data/risc_v_reduced \
  --limit 1 \
  --rebuild
```

## 6. Run EvidenT with the OBS Backend

For a bounded one-package run:

```bash
export EVIDENT_DATA_ROOT=/path/to/EvidenT-riscv-219-dataset/packages
export EVIDENT_PACKAGES=<package_name>

export OPENAI_API_KEY='<your_openai_compatible_key>'
export OPENAI_API_BASE_URL='<your_openai_compatible_base_url>'
export LLM_MODEL='<your_model_name>'

uv run python client.py
```

EvidenT will initialize a temporary package workspace, use MCP tools and the LLM
to repair the package, upload the package files to OBS, and poll the configured
OBS build result.

The dataset may use local directory names prefixed with `failed_` to identify
known failing inputs. OBS source package names should not include that prefix.
EvidenT automatically maps local `failed_python-stomper` to OBS
`python-stomper` during upload, rebuild, and status polling.

When the OBS package was created with `--create-only`, the first EvidenT upload
for that package populates the OBS source package. EvidenT uploads the repaired
package directory as a whole, not only the modified file, so OBS receives the
`.spec`, source archives, patches, `_service`, and other top-level package
inputs needed for a build. Local logs, OBS metadata snapshots, and stale
`_link` files are excluded; removing `_link` ensures OBS builds the uploaded
repaired sources rather than following the original remote package link.

Expected output locations:

```text
auto_repair_log_files/<package>.log
auto_repair_results/<package>_result.txt
temp_workspace/<package>/
```

## 7. Running More Packages

Use either an explicit package list or a small limit:

```bash
EVIDENT_PACKAGES=<package_name>,<another_package_name> uv run python client.py
EVIDENT_PACKAGE_LIMIT=3 uv run python client.py
```

Full 219-package reproduction can take many hours and depends on OBS queue time,
RISC-V worker availability, package dependency state, and LLM latency. For
artifact evaluation, report the bounded package list and preserve the logs above.

## 8. Troubleshooting

- `404` while uploading: create the package with `osc mkpac <package>` and
  commit once, or verify the project name in `config/obs_meta.yaml`.
- `unresolvable`: OBS could not resolve a build dependency. Check the project
  repository path and whether the package needs additional repository layering.
- `broken`: OBS could not parse the package sources or spec. Check that the
  `.spec`, source archives, patches, and required `_service` files were uploaded.
- long `building` state: the build is queued or running on an OBS RISC-V worker.
  Use `osc results` and `osc buildlogtail standard riscv64`.
- anonymous review: use a reviewer-owned OBS project; do not submit
  author-owned OBS links as artifact download links.
