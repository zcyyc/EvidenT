# Artifact Status

## Requested Badges

- Functional
- Reusable

## Badge Rationale

EvidenT is packaged with source code, prompt templates, configuration files, a small smoke-test package, and scripts that exercise the artifact without requiring OBS credentials.

The Docker validation backend makes the build validation path executable on a local machine or server. The original OBS backend is retained for paper-aligned reproduction.

The artifact is structured for reuse:

- configuration is centralized in `config/paths.yaml` and `config/obs_meta.yaml`;
- data can be mounted or selected through `EVIDENT_DATA_ROOT`;
- small runs can be bounded with `EVIDENT_PACKAGES` and `EVIDENT_PACKAGE_LIMIT`;
- validation can be run independently through `scripts/validate_package.py`;
- a fast smoke test is available through `scripts/smoke_test.py`.

For full MCP client/server execution, run `uv run python client.py` with LLM credentials configured in `.env`.

## Available Badge

The repository is ready to be archived for an Available badge after uploading the final artifact bundle to a DOI-backed archival service such as Zenodo, Figshare, or Dryad. Add the DOI to the paper and README once archival is complete.
