import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config_utils import load_config
from tools.validation.check_build_res import check_main


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one package directory with the configured backend."
    )
    parser.add_argument("package_dir", help="Package directory containing a .spec file.")
    parser.add_argument(
        "--package-name",
        default=None,
        help="Package name. Defaults to the directory name.",
    )
    args = parser.parse_args()

    package_dir = Path(args.package_dir).resolve()
    package_name = args.package_name or package_dir.name
    load_config()

    result = check_main(str(package_dir), package_name)
    print(result)
    return 0 if "Build succeeded!" in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
