import os
import requests
from requests.auth import HTTPBasicAuth
from xml.etree import ElementTree
import time
from urllib.parse import quote
from config_utils import load_config
from tools.validation.docker_build import run_docker_build


def obs_path_part(value: str) -> str:
    return quote(value, safe="")


def obs_package_name(package_name: str) -> str:
    return package_name.removeprefix("failed_")


OBS_PENDING_STATES = {
    "blocked",
    "building",
    "dispatching",
    "scheduled",
    "signing",
}


def obs_status_kind(code: str | None) -> str:
    """Classify OBS states without treating queued builds as failures."""
    normalized = (code or "").lower()
    if normalized == "succeeded":
        return "success"
    if normalized in {"failed", "broken", "unresolvable"}:
        return "failure"
    if normalized in {"disabled", "excluded", "locked"}:
        return "inactive"
    return "pending"


def download_logs_and_sources(temp_dir, base_url, user_name, password):
    log_url = f"{base_url}/_log"
    response = requests.get(
        log_url,
        auth=HTTPBasicAuth(user_name, password),
        headers={"Accept": "application/xml"},
        timeout=600,
    )
    response.raise_for_status()

    try:
        if "temp" in temp_dir:
            with open(
                os.path.join(temp_dir, "obs_log_None_standard_riscv64.txt"), "wb"
            ) as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return os.path.join(temp_dir, "obs_log_None_standard_riscv64.txt")
        else:
            return None
    except Exception as e:
        return None


def check_obs_main(temp_dir: str, package_name: str, config: dict):
    obs_url = os.getenv("OBS_URL") or config["obs"]["url"]
    user_name = os.getenv("OBS_USERNAME") or config["obs"]["user_name"]
    password = os.getenv("OBS_PASSWORD") or config["obs"]["password"]
    project = os.getenv("OBS_PROJECT") or config["obs"]["project"]
    repository_name = (
        os.getenv("OBS_REPOSITORY") or config["obs"].get("repository", "standard")
    )
    architecture_name = (
        os.getenv("OBS_ARCHITECTURE") or config["obs"].get("architecture", "riscv64")
    )

    max_wait_seconds = 600
    check_interval = 30
    elapsed_seconds = 0
    source_package = obs_package_name(package_name)

    base_url = (
        f"{obs_url}/build/{obs_path_part(project)}/"
        f"{obs_path_part(repository_name)}/{obs_path_part(architecture_name)}/"
        f"{obs_path_part(source_package)}/"
    )
    status_url = base_url + "_status"

    while elapsed_seconds < max_wait_seconds:
        try:
            response = requests.get(
                status_url,
                auth=HTTPBasicAuth(user_name, password),
                headers={"Accept": "application/xml"},
                timeout=600,
            )

            if response.status_code == 404:
                return f"[ERROR] Status URL not found (404): {status_url}"

            if response.status_code in (401, 403):
                return (
                    f"[ERROR] Unauthorized (HTTP {response.status_code}). "
                    "Check your OBS username/password."
                )

            if response.status_code >= 500:
                return (
                    f"[ERROR] OBS server error ({response.status_code}). "
                    "Try again later."
                )

            response.raise_for_status()

            root = ElementTree.fromstring(response.text)
            print("root.attrib:\n", root.attrib)

            code_value = root.attrib.get("code")

            status_kind = obs_status_kind(code_value)
            if status_kind == "success":
                return "Build succeeded! The build has been successfully completed."

            if status_kind == "failure":
                if code_value == "broken":
                    details = root.findtext("details") or response.text[:1000]
                    return (
                        "Build broken! OBS could not process the source package. "
                        f"Package: {source_package}. Details: {details}"
                    )
                if code_value == "unresolvable":
                    return "Build unresolvable! The build can not begin, because required packages are either missing or not explicitly defined."
                log_path = download_logs_and_sources(
                    temp_dir, base_url, user_name, password
                )
                if log_path is None:
                    return "Build failed! The failed log could not be saved locally."
                return f"Build failed! The failed log has been updated to: {log_path}"

            if status_kind == "inactive":
                details = root.findtext("details") or "no details provided"
                return (
                    f"Build inactive! OBS status is {code_value}. "
                    f"Package: {source_package}. Details: {details}"
                )

            # OBS commonly reports scheduled/blocked/dispatching before a
            # RISC-V worker starts. Unknown transient states are also polled
            # until the bounded timeout rather than being mislabeled failed.
            time.sleep(check_interval)
            elapsed_seconds += check_interval

        except requests.exceptions.RequestException as e:
            print(f"Check build status failed: {str(e)}. Will retry in 10 seconds.")
            time.sleep(10)
            elapsed_seconds += 10
            continue

    return f"Build timeout! The build has not been completed within {max_wait_seconds} seconds. Default build failed."


def check_main(temp_dir: str, package_name: str):
    config = load_config()
    backend = (config.get("validator", {}) or {}).get("backend", "docker").lower()
    if backend == "obs":
        return check_obs_main(temp_dir, package_name, config)
    if backend == "docker":
        return run_docker_build(temp_dir, package_name, config)
    return f"Build failed! Unknown validator backend: {backend}"
