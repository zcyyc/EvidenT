import os
import fnmatch
from html import escape
from urllib.parse import quote
import requests
from requests.auth import HTTPBasicAuth
from config_utils import load_config


DEFAULT_EXCLUDES = [
    "_link",
    "log_failed.txt",
    "log_succeeded.txt",
    "obs_log_*.txt",
    "obs_meta_*.json",
    "*.log",
]

DELETE_BEFORE_UPLOAD = ["_link"]


def should_exclude(filename: str) -> bool:
    return any(fnmatch.fnmatch(filename, pattern) for pattern in DEFAULT_EXCLUDES)


def obs_path_part(value: str) -> str:
    return quote(value, safe="")


def obs_package_name(package_name: str) -> str:
    return package_name.removeprefix("failed_")


def ensure_package(
    obs_url: str,
    username: str,
    password: str,
    project: str,
    package: str,
) -> str:
    """Create or update package metadata before source upload."""
    url = (
        f"{obs_url}/source/{obs_path_part(project)}/"
        f"{obs_path_part(package)}/_meta"
    )
    meta = (
        f'<package name="{escape(package)}">'
        f"<title>{escape(package)}</title>"
        "<description>EvidenT repaired package.</description>"
        "</package>"
    )
    response = requests.put(
        url,
        auth=HTTPBasicAuth(username, password),
        data=meta.encode("utf-8"),
        headers={"Content-Type": "application/xml", "Accept": "application/xml"},
        timeout=600,
    )
    if response.status_code in (200, 201):
        return f"Success: Package {package} is ready."
    return (
        f"Error: Package metadata update failed for {package}. "
        f"Status code: {response.status_code}, Error message: {response.text}"
    )


def delete_source_file(
    obs_url: str,
    username: str,
    password: str,
    project: str,
    package: str,
    target_filename: str,
) -> str:
    url = (
        f"{obs_url}/source/{obs_path_part(project)}/"
        f"{obs_path_part(package)}/{obs_path_part(target_filename)}"
    )
    response = requests.delete(
        url,
        auth=HTTPBasicAuth(username, password),
        headers={"Accept": "application/xml"},
        timeout=600,
    )
    if response.status_code in (200, 202, 404):
        return f"Success: OBS source file {target_filename} is absent."
    return (
        f"Error: Could not delete OBS source file {target_filename}. "
        f"Status code: {response.status_code}, Error message: {response.text}"
    )


def list_source_files(
    obs_url: str,
    username: str,
    password: str,
    project: str,
    package: str,
) -> tuple[list[str], str | None]:
    url = (
        f"{obs_url}/source/{obs_path_part(project)}/"
        f"{obs_path_part(package)}"
    )
    response = requests.get(
        url,
        auth=HTTPBasicAuth(username, password),
        headers={"Accept": "application/xml"},
        timeout=600,
    )
    if response.status_code != 200:
        return [], (
            f"Error: Could not list OBS source package {package}. "
            f"Status code: {response.status_code}, Error message: {response.text}"
        )

    import xml.etree.ElementTree as ET

    root = ET.fromstring(response.text)
    return [entry.attrib.get("name", "") for entry in root.findall("entry")], None


def verify_uploaded_sources(
    obs_url: str,
    username: str,
    password: str,
    project: str,
    package: str,
) -> str:
    names, error = list_source_files(obs_url, username, password, project, package)
    if error:
        return error

    spec_files = [name for name in names if name.endswith(".spec")]
    if not spec_files:
        return f"Error: OBS package {package} has no .spec file after upload. Files: {names}"
    if "_link" in names:
        return f"Error: OBS package {package} still contains _link after upload. Files: {names}"
    return f"Success: OBS package {package} source files verified: {', '.join(names)}"

def upload_file_to_obs(
    obs_url: str,
    username: str,
    password: str,
    project: str,
    package: str,
    local_file_path: str,
    target_filename: str
) -> None:
    """
        Uploads a local file to a specified package in an OBS project.

        Parameters:
            obs_url: OBS API base URL (e.g., "https://api.opensuse.org")
            username: OBS username
            password: OBS password
            project: Target project name (e.g., "home:your_username")
            package: Target package name under the project
            local_file_path: Absolute/relative path to the local file
            target_filename: File name after uploading to OBS
    """
    url = (
        f"{obs_url}/source/{obs_path_part(project)}/"
        f"{obs_path_part(package)}/{obs_path_part(target_filename)}"
    )
    
    try:
        with open(local_file_path, 'rb') as f:
            file_content = f.read()
        
        # Send a PUT request to upload a file (using Basic Auth authentication)
        response = requests.put(
            url,
            auth=HTTPBasicAuth(username, password),
            data=file_content,
            headers={
                "Content-Type": "application/octet-stream",
                "Accept": "application/xml"
            },
            timeout=600
        )
        # handling the response
        if response.status_code in (200, 201):
            return f"Success: File {target_filename} uploaded to OBS successfully."

        else:
            return f"Error: File {target_filename} uploaded to OBS failed. Status code: {response.status_code}, Error message: {response.text}"
    
    except FileNotFoundError:
        return f"Error: Local file not found - {local_file_path}"
    except requests.exceptions.RequestException as e:
        return f"Error: Request exception - {str(e)}"


def main_upload(package_name, file_name):
    config = load_config()
    obs_url = config["obs"]["url"]
    user_name = os.getenv("OBS_USERNAME") or config["obs"]["user_name"]
    password = os.getenv("OBS_PASSWORD") or config["obs"]["password"]
    project = os.getenv("OBS_PROJECT") or config["obs"]["project"]
    source_package = obs_package_name(package_name)
    print("The user_name of obs:", user_name)
    if source_package != package_name:
        print(f"OBS package name: {package_name} -> {source_package}")

    package_result = ensure_package(obs_url, user_name, password, project, source_package)
    if package_result.startswith("Error:"):
        return package_result

    for stale_file in DELETE_BEFORE_UPLOAD:
        delete_result = delete_source_file(
            obs_url, user_name, password, project, source_package, stale_file
        )
        print(delete_result)
        if delete_result.startswith("Error:"):
            return delete_result

    uploaded = 0
    skipped = 0
    errors = []
    for file in os.listdir(file_name):
        file_path = os.path.join(file_name, file)
        if os.path.isdir(file_path):
            skipped += 1
            print(f"Skip directory: {file}")
            continue
        if should_exclude(file):
            skipped += 1
            print(f"Skip non-source file: {file}")
            continue
        print(file)
        try:
            result = upload_file_to_obs(
                obs_url=obs_url,
                username=user_name,
                password=password,
                project=project,
                package=source_package,
                local_file_path=file_path,
                target_filename=file
            )
            print(result)
            if str(result).startswith("Error:"):
                errors.append(result)
            else:
                uploaded += 1
        except Exception as e:
            print(f"Error: {str(e)}")
            errors.append(f"Error: {str(e)}")

    if errors:
        return (
            f"Error: Uploaded {uploaded} files with {len(errors)} failures "
            f"for OBS package {source_package}. First failure: {errors[0]}"
        )
    verify_result = verify_uploaded_sources(
        obs_url, user_name, password, project, source_package
    )
    if verify_result.startswith("Error:"):
        return verify_result
    print(verify_result)
    return (
        f"Success: Uploaded {uploaded} files to OBS package {source_package} "
        f"(skipped {skipped})."
    )
