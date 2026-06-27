import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> Dict[str, Any]:
    """Load EvidenT configuration from the project-level config files."""
    config = _read_yaml(PROJECT_ROOT / "config" / "paths.yaml")
    obs_config = _read_yaml(PROJECT_ROOT / "config" / "obs_meta.yaml")
    if obs_config:
        config.update(obs_config)
    return config


def resolve_path(path_value: Optional[str], *, root: Path = PROJECT_ROOT) -> Optional[str]:
    if path_value is None:
        return None
    expanded = os.path.expandvars(os.path.expanduser(str(path_value)))
    path = Path(expanded)
    if path.is_absolute():
        return str(path)
    return str(root / path)


def get_path(config: Dict[str, Any], key: str, default: Optional[str] = None) -> str:
    paths = config.get("paths", {}) or {}
    if key == "base_dir" and os.getenv("EVIDENT_DATA_ROOT"):
        return os.getenv("EVIDENT_DATA_ROOT", "")
    value = paths.get(key, default)
    resolved = resolve_path(value)
    return resolved or ""


def get_validator_backend(config: Optional[Dict[str, Any]] = None) -> str:
    config = config or load_config()
    validator = config.get("validator", {}) or {}
    return str(validator.get("backend", "docker")).lower()
