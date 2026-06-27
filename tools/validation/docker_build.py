import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


ARCH_TO_PLATFORM = {
    "amd64": "linux/amd64",
    "x86_64": "linux/amd64",
    "arm64": "linux/arm64",
    "aarch64": "linux/arm64",
    "riscv64": "linux/riscv64",
}


def _cfg(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    docker_cfg = config.get("docker", {}) or {}
    validator_cfg = config.get("validator", {}) or {}
    return docker_cfg.get(key, validator_cfg.get(key, default))


def _target_arch(config: Dict[str, Any]) -> str:
    target = (config.get("target", {}) or {}).get("architecture")
    if not target:
        target = (config.get("obs", {}) or {}).get("architecture", "riscv64")
    return str(target).lower()


def _default_platform(config: Dict[str, Any]) -> Optional[str]:
    return ARCH_TO_PLATFORM.get(_target_arch(config))


def _find_spec(package_dir: Path, package_name: str) -> Path:
    normalized = package_name.removeprefix("failed_")
    preferred = package_dir / f"{normalized}.spec"
    if preferred.is_file():
        return preferred

    specs = sorted(package_dir.glob("*.spec"))
    if not specs:
        raise FileNotFoundError(f"No .spec file found in {package_dir}")
    return specs[0]


def _repo_setup_script(repo_mirror: Optional[str], platform: Optional[str]) -> str:
    if not repo_mirror:
        return ""

    mirror = shlex.quote(repo_mirror.rstrip("/"))
    if platform == "linux/arm64":
        return f"""
rm -f /etc/zypp/repos.d/*.repo
zypper --non-interactive ar -f {mirror}/ports/aarch64/tumbleweed/repo/oss/ repo-oss
zypper --non-interactive ar -f {mirror}/ports/aarch64/update/tumbleweed/ repo-update
"""

    if platform == "linux/riscv64":
        return f"""
rm -f /etc/zypp/repos.d/*.repo
zypper --non-interactive ar -f {mirror}/ports/riscv/tumbleweed/repo/oss/ repo-oss
zypper --non-interactive ar -f {mirror}/ports/riscv/update/tumbleweed/ repo-update
"""

    return f"""
rm -f /etc/zypp/repos.d/*.repo
zypper --non-interactive ar -f {mirror}/tumbleweed/repo/oss/ repo-oss
zypper --non-interactive ar -f {mirror}/tumbleweed/repo/non-oss/ repo-non-oss
zypper --non-interactive ar -f {mirror}/update/tumbleweed/ repo-update
"""


def _container_script(
    spec_name: str,
    repo_mirror: Optional[str],
    platform: Optional[str],
    gpg_check: bool,
    refresh_repositories: bool,
    install_buildrequires: bool,
    rpmbuild_nodeps: bool,
    rpmbuild_defines: Optional[list[str]],
) -> str:
    quoted_spec = shlex.quote(spec_name)
    dependency_setup = ""

    if install_buildrequires:
        repo_setup = _repo_setup_script(repo_mirror, platform)
        gpg_setup = ""
        zypper_gpg_flag = "--gpg-auto-import-keys"
        if not gpg_check:
            gpg_setup = """
zypper --non-interactive modifyrepo --no-gpgcheck --all || true
zypper --non-interactive modifyrepo --disable repo-openh264 || true
sed -i '/^gpgkey=/d' /etc/zypp/repos.d/*.repo || true
"""
            zypper_gpg_flag = "--no-gpg-checks"
        refresh_cmd = ""
        zypper_refresh_flag = ""
        if refresh_repositories:
            refresh_cmd = f"zypper --non-interactive {zypper_gpg_flag} refresh"
        else:
            zypper_refresh_flag = "--no-refresh"

        dependency_setup = f"""
{repo_setup}
{gpg_setup}

{refresh_cmd}
zypper --non-interactive {zypper_gpg_flag} {zypper_refresh_flag} install \\
  bash coreutils rpm-build \\
  tar gzip bzip2 xz unzip patch diffutils findutils which file \\
  make gcc gcc-c++ pkg-config

# Many openSUSE package specs use distribution macros before BuildRequires
# can be queried. Install common macro packages best-effort so one missing
# optional package does not prevent the useful macro packages from loading.
for macro_pkg in \\
  python-rpm-macros \\
  python-rpm-generators \\
  systemd-rpm-macros; do
  zypper --non-interactive {zypper_gpg_flag} {zypper_refresh_flag} install -- "$macro_pkg" || true
done

if ! rpmspec -q --buildrequires {quoted_spec} > /tmp/buildrequires.txt; then
  echo "Build dependency parsing failed."
  exit 87
fi

while IFS= read -r req; do
  test -n "$req" || continue
  if ! zypper --non-interactive {zypper_gpg_flag} {zypper_refresh_flag} install -- "$req"; then
    echo "Build dependency installation failed: $req"
    exit 88
  fi
done < /tmp/buildrequires.txt
"""

    nodeps_flag = "--nodeps" if rpmbuild_nodeps else ""
    define_flags = ""
    if rpmbuild_defines:
        define_flags = " \\\n  ".join(
            f"--define {shlex.quote(str(item))}" for item in rpmbuild_defines
        )
        define_flags = f" \\\n  {define_flags}"

    return f"""
set -o pipefail
export LANG=C.UTF-8
cd /workspace

{dependency_setup}

if test -f /workspace/_constraints; then
  echo "Note: Docker validator does not enforce OBS _constraints."
fi

rm -rf /tmp/rpmbuild
mkdir -p /tmp/rpmbuild/BUILD /tmp/rpmbuild/BUILDROOT /tmp/rpmbuild/RPMS \\
  /tmp/rpmbuild/SOURCES /tmp/rpmbuild/SPECS /tmp/rpmbuild/SRPMS

find /workspace -maxdepth 1 -type f ! -name '*.spec' -exec cp -a {{}} /tmp/rpmbuild/SOURCES/ \\;
cp -a /workspace/{quoted_spec} /tmp/rpmbuild/SPECS/

rpmbuild -ba \\
  {nodeps_flag} \\
  --define '_topdir /tmp/rpmbuild' \\
  --define '_sourcedir /tmp/rpmbuild/SOURCES' \\
  --define '_specdir /tmp/rpmbuild/SPECS' \\
  --define '_builddir /tmp/rpmbuild/BUILD' \\
  --define '_rpmdir /tmp/rpmbuild/RPMS' \\
  --define '_srcrpmdir /tmp/rpmbuild/SRPMS'{define_flags} \\
  /tmp/rpmbuild/SPECS/{quoted_spec}
"""


def run_docker_build(package_dir: str, package_name: str, config: Dict[str, Any]) -> str:
    package_path = Path(package_dir).resolve()
    if not package_path.is_dir():
        return f"Build failed! Package directory not found: {package_path}"

    try:
        spec_path = _find_spec(package_path, package_name)
    except FileNotFoundError as exc:
        return f"Build failed! {exc}"

    image = _cfg(config, "image", "registry.opensuse.org/opensuse/tumbleweed:latest")
    timeout_seconds = int(_cfg(config, "timeout_seconds", 3600))
    pull_policy = _cfg(config, "pull", "missing")
    platform = _cfg(config, "platform", None) or _default_platform(config)
    workdir = _cfg(config, "workdir", "/workspace")
    repo_mirror = _cfg(config, "repo_mirror", None)
    gpg_check = bool(_cfg(config, "gpg_check", False))
    refresh_repositories = bool(_cfg(config, "refresh", True))
    install_buildrequires = bool(_cfg(config, "install_buildrequires", True))
    rpmbuild_nodeps = bool(_cfg(config, "rpmbuild_nodeps", False))
    rpmbuild_defines = _cfg(config, "rpmbuild_defines", None) or []

    log_path = package_path / "log_failed.txt"
    script = _container_script(
        spec_path.name,
        repo_mirror,
        platform,
        gpg_check,
        refresh_repositories,
        install_buildrequires,
        rpmbuild_nodeps,
        rpmbuild_defines,
    )

    cmd = [
        "docker",
        "run",
        "--rm",
        "--pull",
        str(pull_policy),
        "-v",
        f"{package_path}:{workdir}:rw",
        "-w",
        workdir,
    ]
    if platform:
        cmd.extend(["--platform", str(platform)])
    cmd.extend([str(image), "bash", "-lc", script])

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return "Build failed! Docker executable was not found on this host."
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        log_path.write_text(output, encoding="utf-8", errors="replace")
        return (
            f"Build timeout! Docker build exceeded {timeout_seconds} seconds. "
            f"The partial log has been updated to: {log_path}"
        )

    log_path.write_text(proc.stdout or "", encoding="utf-8", errors="replace")
    if proc.returncode == 0:
        return "Build succeeded! The Docker build has been successfully completed."

    output = proc.stdout or ""
    if "exec format error" in output.lower():
        return (
            "Build failed! Docker could not run the requested platform "
            f"({platform or 'host default'}). The failed log has been updated to: "
            f"{log_path}. Enable qemu/binfmt for cross-architecture containers "
            "or override docker.platform for a host-architecture smoke test."
        )

    return (
        "Build failed! The Docker build failed. "
        f"The failed log has been updated to: {log_path}"
    )
