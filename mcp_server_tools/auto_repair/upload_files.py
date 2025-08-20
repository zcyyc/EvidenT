from enum import Flag
from ntpath import isdir
import os
import requests
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
    将本地文件上传到 OBS 项目的指定包中。
    
    参数:
        obs_url: OBS API 基础 URL（如 "https://api.opensuse.org"）
        username: OBS 用户名
        password: OBS 密码
        project: 目标项目名称（如 "home:your_username"）
        package: 项目下的目标包名称
        local_file_path: 本地文件的绝对/相对路径
        target_filename: 上传到 OBS 后的文件名
    """
    # 构建 API 端点 URL（上传到 source 服务）
    url = f"{obs_url}/source/{project}/{package}/{target_filename}"
    
    try:
        # 读取本地文件内容
        with open(local_file_path, 'rb') as f:
            file_content = f.read()
        
        # 发送 PUT 请求上传文件（使用 Basic Auth 认证）
        response = requests.put(
            url,
            auth=HTTPBasicAuth(username, password),
            data=file_content,
            headers={
                "Content-Type": "application/octet-stream",  # 通用二进制流类型
                "Accept": "application/xml"  # OBS 通常返回 XML 响应
            },
            timeout=600
        )
        
        # 处理响应
        if response.status_code in (200, 201):
            return f"Success: File {target_filename} uploaded to OBS successfully."

        else:
            return f"Error: File {target_filename} uploaded to OBS failed. Status code: {response.status_code}, Error message: {response.text}"
    
    except FileNotFoundError:
        return f"Error: Local file not found - {local_file_path}"
    except requests.exceptions.RequestException as e:
        return f"Error: Request exception - {str(e)}"


def main_upload(package_name, file_name):

    # 配置参数（需替换为实际信息）
    OBS_API_URL = "https://api.opensuse.org"
    OBS_USERNAME = "lalala123"  # 你的 OBS 用户名
    OBS_PASSWORD = "zhaochenyu921"  # 你的 OBS 密码
    TARGET_PROJECT = "home:lalala123:RISCV_test1"

    for file in os.listdir(file_name):
        print(file)
        file_path = os.path.join(file_name, file)
        try:
            upload_file_to_obs(
                obs_url=OBS_API_URL,
                username=OBS_USERNAME,
                password=OBS_PASSWORD,
                project=TARGET_PROJECT,
                package=package_name,
                local_file_path=file_path,
                target_filename=file
            )
        except Exception as e:
            print(f"Error: {str(e)}")
            return f"Error: {str(e)}"
    return f"Success: File {file_name} uploaded to OBS {package_name} successfully."



if __name__ == "__main__":
    # 配置参数（需替换为实际信息）
    OBS_API_URL = "https://api.opensuse.org"
    OBS_USERNAME = "lalala123"  # 你的 OBS 用户名
    OBS_PASSWORD = "zhaochenyu921"  # 你的 OBS 密码
    TARGET_PROJECT = "home:lalala123:RISCV_test1"

    need_package_name = []
    for target_package_name in os.listdir("/Users/zcy/Codes/PythonCodes/aiops_mcp/temp_workspace"):
        flag = False
        LOCAL_FILE = os.path.join("/Users/zcy/Codes/PythonCodes/aiops_mcp/temp_workspace", target_package_name)
        for data in os.listdir(LOCAL_FILE):
            if os.path.isdir(os.path.join(LOCAL_FILE, data)):
                flag = True
                break
        if flag:
            need_package_name.append(target_package_name)
    print("len(need_package_name)", len(need_package_name))

    for target_package_name in need_package_name:
        LOCAL_FILE = os.path.join("/Users/zcy/Codes/PythonCodes/aiops_mcp/temp_workspace", target_package_name)       # 本地文件路径
        TARGET_PACKAGE = target_package_name

        for file in os.listdir(LOCAL_FILE):
            file_path = os.path.join(LOCAL_FILE, file)
            if os.path.isfile(file_path):

                UPLOAD_FILENAME = file

                if file.startswith("repair_"):
                    original_name = file.split("repair_", 1)[1]
                    original_path = os.path.join(LOCAL_FILE, original_name)
                    if os.path.exists(original_path):
                        os.remove(original_path)
                        print(f"已删除目标文件: {original_name}")
                    
                    # 2. 将当前文件重命名为目标文件名
                    os.rename(file_path, original_path)
                    print(f"已将 {file} 重命名为 {original_name}")
                    UPLOAD_FILENAME = original_name

            
                print("TARGET_PROJECT", TARGET_PROJECT)
                print("TARGET_PACKAGE", TARGET_PACKAGE)
                print("local_file_path", os.path.join(LOCAL_FILE, UPLOAD_FILENAME))
                # 调用上传函数
                upload_file_to_obs(
                    obs_url=OBS_API_URL,
                    username=OBS_USERNAME,
                    password=OBS_PASSWORD,
                    project=TARGET_PROJECT,
                    package=TARGET_PACKAGE,
                    local_file_path=os.path.join(LOCAL_FILE, UPLOAD_FILENAME),
                    target_filename=UPLOAD_FILENAME
                )