import os
import requests
import yaml
from enum import Flag
from ntpath import isdir
from requests.auth import HTTPBasicAuth

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
    url = f"{obs_url}/source/{project}/{package}/{target_filename}"
    
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
    with open("config/obs_meta.yaml", "r") as file:
        config = yaml.safe_load(file)
    obs_url = config["obs"]["url"]
    user_name = config["obs"]["user_name"]
    password = config["obs"]["password"]
    project = config["obs"]["project"]
    print("The user_name of obs:", user_name)


    for file in os.listdir(file_name):
        print(file)
        file_path = os.path.join(file_name, file)
        try:
            upload_file_to_obs(
                obs_url=obs_url,
                username=user_name,
                password=password,
                project=project,
                package=package_name,
                local_file_path=file_path,
                target_filename=file
            )
        except Exception as e:
            print(f"Error: {str(e)}")
            return f"Error: {str(e)}"
    return f"Success: File {file_name} uploaded to OBS {package_name} successfully."