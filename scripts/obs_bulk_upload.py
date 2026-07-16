import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fnmatch
import os
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

import requests
import yaml
from requests.auth import HTTPBasicAuth


DEFAULT_EXCLUDES = [
    "_link",
    "log_failed.txt",
    "log_succeeded.txt",
    "obs_log_*.txt",
    "obs_meta_*.json",
    "*.log",
]


def quote_path_part(value: str) -> str:
    return quote(value, safe="")


def obs_package_name(package_name: str) -> str:
    return package_name.removeprefix("failed_")


def load_obs_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("obs", data)


def should_exclude(path: Path, patterns: list[str]) -> bool:
    name = path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def package_dirs(root: Path, manifest: Path | None, limit: int | None) -> list[Path]:
    if manifest:
        names = [
            line.strip()
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        dirs = [root / name for name in names]
    else:
        dirs = sorted(p for p in root.iterdir() if p.is_dir())

    dirs = [p for p in dirs if p.is_dir()]
    if limit is not None:
        dirs = dirs[:limit]
    return dirs


def request_or_raise(method: str, url: str, auth: HTTPBasicAuth, **kwargs) -> requests.Response:
    response = requests.request(method, url, auth=auth, timeout=kwargs.pop("timeout", 600), **kwargs)
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"{method} {url} failed with HTTP {response.status_code}: {response.text[:500]}"
        )
    return response


def ensure_package(obs_url: str, auth: HTTPBasicAuth, project: str, package: str, dry_run: bool) -> None:
    url = (
        f"{obs_url.rstrip('/')}/source/"
        f"{quote_path_part(project)}/{quote_path_part(package)}/_meta"
    )
    meta = (
        f'<package name="{escape(package)}" project="{escape(project)}">'
        f"<title>{escape(package)}</title>"
        "<description>EvidenT package validation input.</description>"
        "</package>"
    )
    if dry_run:
        print(f"[dry-run] ensure package {project}/{package}")
        return
    request_or_raise(
        "PUT",
        url,
        auth,
        data=meta.encode("utf-8"),
        headers={"Content-Type": "application/xml", "Accept": "application/xml"},
    )


def upload_file(
    obs_url: str,
    auth: HTTPBasicAuth,
    project: str,
    package: str,
    file_path: Path,
    target_name: str,
    dry_run: bool,
) -> None:
    url = (
        f"{obs_url.rstrip('/')}/source/"
        f"{quote_path_part(project)}/{quote_path_part(package)}/{quote_path_part(target_name)}"
    )
    if dry_run:
        print(f"[dry-run] upload {file_path} -> {project}/{package}/{target_name}")
        return
    with file_path.open("rb") as f:
        request_or_raise(
            "PUT",
            url,
            auth,
            data=f,
            headers={"Content-Type": "application/octet-stream", "Accept": "application/xml"},
        )


def trigger_rebuild(
    obs_url: str,
    auth: HTTPBasicAuth,
    project: str,
    package: str,
    repository: str,
    arch: str,
    dry_run: bool,
) -> None:
    url = (
        f"{obs_url.rstrip('/')}/build/{quote_path_part(project)}"
        f"?package={quote_path_part(package)}"
        f"&repository={quote_path_part(repository)}"
        f"&arch={quote_path_part(arch)}"
        "&cmd=rebuild"
    )
    if dry_run:
        print(f"[dry-run] rebuild {project}/{package} {repository}/{arch}")
        return
    request_or_raise("POST", url, auth, data="", headers={"Accept": "application/xml"})


def upload_package(
    obs_url: str,
    auth: HTTPBasicAuth,
    project: str,
    package_dir: Path,
    excludes: list[str],
    create_only: bool,
    dry_run: bool,
) -> tuple[int, int]:
    package = obs_package_name(package_dir.name)
    if package != package_dir.name:
        print(f"[name-map] {package_dir.name} -> {package}")
    ensure_package(obs_url, auth, project, package, dry_run)
    if create_only:
        print(f"[create-only] {project}/{package}")
        return 0, 0

    uploaded = 0
    skipped = 0
    for path in sorted(package_dir.iterdir()):
        if path.is_dir():
            print(f"[skip-dir] {package_dir.name}/{path.name}")
            skipped += 1
            continue
        if should_exclude(path, excludes):
            print(f"[skip] {package_dir.name}/{path.name}")
            skipped += 1
            continue
        upload_file(obs_url, auth, project, package, path, path.name, dry_run)
        action = "dry-run upload" if dry_run else "upload"
        print(f"[{action}] {package}/{path.name}")
        uploaded += 1

    return uploaded, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create OBS packages and bulk-upload EvidenT package source files."
    )
    parser.add_argument("--root", required=True, help="Directory containing package directories.")
    parser.add_argument("--project", help="OBS project, overrides config/obs_meta.yaml.")
    parser.add_argument("--config", default="config/obs_meta.yaml", help="OBS config YAML.")
    parser.add_argument("--manifest", help="Optional package_manifest.txt or package name list.")
    parser.add_argument("--limit", type=int, help="Upload only the first N packages.")
    parser.add_argument("--exclude", action="append", default=[], help="Extra filename glob to skip.")
    parser.add_argument("--include-logs", action="store_true", help="Do not apply default log/meta excludes.")
    parser.add_argument("--create-only", action="store_true", help="Only create OBS packages; do not upload files.")
    parser.add_argument("--jobs", type=int, default=1, help="Parallel jobs for --create-only.")
    parser.add_argument("--rebuild", action="store_true", help="Trigger rebuild after each package upload.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without changing OBS.")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Package root not found: {root}")

    config = load_obs_config(Path(args.config))
    obs_url = config.get("url", "https://api.opensuse.org")
    username = os.getenv("OBS_USERNAME") or config.get("user_name")
    password = os.getenv("OBS_PASSWORD") or config.get("password")
    project = args.project or os.getenv("OBS_PROJECT") or config.get("project")
    repository = config.get("repository", "standard")
    arch = config.get("architecture", "riscv64")

    if not username or not password or not project:
        raise SystemExit(
            "Missing OBS credentials/project. Set OBS_USERNAME, OBS_PASSWORD, OBS_PROJECT "
            "or fill config/obs_meta.yaml."
        )

    manifest = Path(args.manifest).expanduser().resolve() if args.manifest else None
    excludes = ([] if args.include_logs else DEFAULT_EXCLUDES) + args.exclude
    auth = HTTPBasicAuth(username, password)

    dirs = package_dirs(root, manifest, args.limit)
    print(f"package_root={root}")
    print(f"obs_project={project}")
    print(f"packages={len(dirs)}")
    print(f"dry_run={args.dry_run}")

    total_uploaded = 0
    total_skipped = 0
    if args.create_only and args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(
                    upload_package,
                    obs_url,
                    auth,
                    project,
                    package_dir,
                    excludes,
                    True,
                    args.dry_run,
                ): (index, package_dir)
                for index, package_dir in enumerate(dirs, 1)
            }
            for future in as_completed(futures):
                index, package_dir = futures[future]
                try:
                    uploaded, skipped = future.result()
                    total_uploaded += uploaded
                    total_skipped += skipped
                    print(f"== [{index}/{len(dirs)}] {package_dir.name}: ok ==")
                except Exception as exc:
                    print(f"== [{index}/{len(dirs)}] {package_dir.name}: failed: {exc} ==")
    else:
        for index, package_dir in enumerate(dirs, 1):
            print(f"\n== [{index}/{len(dirs)}] {package_dir.name} ==")
            uploaded, skipped = upload_package(
                obs_url, auth, project, package_dir, excludes, args.create_only, args.dry_run
            )
            total_uploaded += uploaded
            total_skipped += skipped
            if args.rebuild and not args.create_only:
                package = obs_package_name(package_dir.name)
                trigger_rebuild(
                    obs_url,
                    auth,
                    project,
                    package,
                    repository,
                    arch,
                    args.dry_run,
                )

    print(f"\nDone. uploaded_files={total_uploaded}, skipped_files={total_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
