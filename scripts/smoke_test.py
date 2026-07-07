import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config_utils import get_path, get_validator_backend, load_config


DEFAULT_VALIDATION_PACKAGE = (
    PROJECT_ROOT / "dataset/obs_data/risc_v_reduced/failed_python-stomper"
)


def _select_package(base_dir: Path, package_name: str | None, validate: bool) -> Path:
    if package_name:
        return base_dir / package_name

    if validate and DEFAULT_VALIDATION_PACKAGE.is_dir():
        return DEFAULT_VALIDATION_PACKAGE

    all_packages = sorted(p for p in base_dir.iterdir() if p.is_dir())
    failed_packages = [p for p in all_packages if p.name.startswith("failed")]
    if failed_packages:
        return failed_packages[0]
    if all_packages:
        return all_packages[0]
    return base_dir / "__missing_package__"


def _reached_expected_validator_failure(package: Path) -> bool:
    log_path = package / "log_failed.txt"
    if not log_path.is_file():
        return False
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    return "assertEquals" in log_text and "%check" in log_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a fast EvidenT artifact smoke test.")
    parser.add_argument(
        "--package",
        default=None,
        help=(
            "Optional package directory name under EVIDENT_DATA_ROOT. "
            "Without --package, --validate uses the reduced python-stomper case."
        ),
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

    package = _select_package(base_dir, args.package, args.validate)
    if not package.is_dir():
        if args.package:
            print(f"ERROR: package not found: {package}")
        else:
            print(f"ERROR: no package directories found in {base_dir}")
        return 2

    is_default_validation = args.validate and args.package is None and package == DEFAULT_VALIDATION_PACKAGE

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
        if "Build succeeded!" in result:
            print("validator_build=ok")
            print("smoke_test=ok")
            return 0
        if (
            is_default_validation
            and "Docker build failed" in result
            and _reached_expected_validator_failure(package)
        ):
            print("validator_reached_expected_check_failure=ok")
            print("smoke_test=ok")
            return 0
        return 1

    print("smoke_test=ok")
    print("Set --validate to run the Docker/OBS build validator.")
    return 0


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    raise SystemExit(main())
