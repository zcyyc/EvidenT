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
            }
        )
        
        # 处理响应
        if response.status_code in (200, 201):
            print(f"文件上传成功！状态码: {response.status_code}")
            print(f"上传路径: {url}")
        else:
            print(f"上传失败！状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
    
    except FileNotFoundError:
        print(f"错误：本地文件不存在 - {local_file_path}")
    except requests.exceptions.RequestException as e:
        print(f"请求异常：{str(e)}")


# 示例用法
if __name__ == "__main__":
    # 配置参数（需替换为实际信息）
    OBS_API_URL = "https://api.opensuse.org"
    OBS_USERNAME = "lalala123"  # 你的 OBS 用户名
    OBS_PASSWORD = "zhaochenyu921"  # 你的 OBS 密码
    TARGET_PROJECT = "home:lalala123"  # 目标项目（如个人主页项目）
    TARGET_PACKAGE = "amanda"          # 目标包名称
    LOCAL_FILE = "D:\\PythonCodes\\aiops_mcp\\end_to_end\\obs_data\\home_lalala123\\amanda"       # 本地文件路径

    for file in os.listdir(LOCAL_FILE):
        UPLOAD_FILENAME = file  # 上传后的文件名

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