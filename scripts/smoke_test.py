import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config_utils import get_path, get_validator_backend, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a fast EvidenT artifact smoke test.")
    parser.add_argument(
        "--package",
        default=None,
        help="Optional package directory name. Defaults to the first failed_* package.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Also run the configured build validator. This may take several minutes.",
    )
    args = parser.parse_args()

    config = load_config()
    base_dir = Path(get_path(config, "base_dir"))
    print(f"data_root={base_dir}")
    print(f"validator_backend={get_validator_backend(config)}")

    if not base_dir.is_dir():
        print("ERROR: data root does not exist. Set EVIDENT_DATA_ROOT or edit config/paths.yaml.")
        return 2

    packages = sorted(p for p in base_dir.iterdir() if p.is_dir() and p.name.startswith("failed"))
    if not packages:
        print(f"ERROR: no failed_* packages found in {base_dir}")
        return 2

    package = base_dir / args.package if args.package else packages[0]
    if not package.is_dir():
        print(f"ERROR: package not found: {package}")
        return 2

    specs = sorted(package.glob("*.spec"))
    logs = sorted(package.glob("*.log")) + sorted(package.glob("*.txt"))
    print(f"package={package.name}")
    print(f"spec_files={len(specs)}")
    print(f"log_files={len(logs)}")

    if not specs:
        print("ERROR: package has no .spec file")
        return 2

    import mcp  # noqa: F401
    from openai import OpenAI  # noqa: F401
    from tools.analysis_and_repair.dependency_constrain import spec_parser_main

    spec_parser_main(str(specs[0]))
    print("lightweight_imports=ok")
    print("spec_parser=ok")

    if args.validate:
        from tools.validation.check_build_res import check_main

        result = check_main(str(package), package.name)
        print(result)
        return 0 if "Build succeeded!" in result else 1

    print("smoke_test=ok")
    print("Set --validate to run the Docker/OBS build validator.")
    return 0


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    raise SystemExit(main())
