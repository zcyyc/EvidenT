import time
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import quote
import xml.etree.ElementTree as ET

def trigger_rebuild_with_cmd(obs_url: str,
    username: str,
    password: str,
    project: str,
    repository: str,
    arch: str,
    package: str):

    # 编码项目名中的特殊字符（如 ":" 编码为 %3A）
    encoded_project = quote(project, safe='')
    # 构建 URL（带查询参数）
    url = (
        f"{obs_url}/build/{encoded_project}"
        f"?package={quote(package, safe='')}"
        f"&repository={quote(repository, safe='')}"
        f"&arch={quote(arch, safe='')}"
        f"&cmd=rebuild"
    )

    try:
        # 发送 POST 请求，空数据体（-d '' 对应 data=''）
        response = requests.post(
            url,
            auth=HTTPBasicAuth(username, password),
            headers={"Accept": "application/xml; charset=utf-8"},
            data=''  # 空请求体，必须传递（对应 curl 的 -d ''）
        )

        print(f"状态码：{response.status_code}")
        print(f"响应内容：{response.text}")

        if response.status_code == 200 and "<status code=\"ok\" />" in response.text:
            print("重建命令触发成功！")
        else:
            print("重建命令触发失败")

    except requests.exceptions.RequestException as e:
        print(f"请求异常：{str(e)}")


def check_build_status(
    obs_url: str,
    username: str,
    password: str,
    project: str,
    repository: str,
    arch: str,
    package: str
) -> str:
    """查询构建状态，返回状态码（如 building、succeeded、failed 等）"""
    # 编码 URL 中的特殊字符
    encoded_project = quote(project, safe='')
    encoded_repo = quote(repository, safe='')
    encoded_arch = quote(arch, safe='')
    encoded_package = quote(package, safe='')
    
    url = f"{obs_url}/build/{encoded_project}/{encoded_repo}/{encoded_arch}/{encoded_package}/_status"
    
    try:
        response = requests.get(
            url,
            auth=HTTPBasicAuth(username, password),
            headers={"Accept": "application/xml; charset=utf-8"}
        )

        if response.status_code != 200:
            print(f"获取状态失败，状态码：{response.status_code}，响应：{response.text}")
            return "unknown"
        
        # 解析 XML 响应
        root = ET.fromstring(response.text)
        code = root.get('code')

        if code:
            return code.strip()
        else:
            print("未找到 code 属性，响应格式异常")
            return "unknown"
    
    except Exception as e:
        print(f"查询状态异常：{str(e)}")
        return "unknown"


def wait_for_build_complete(
    obs_url: str,
    username: str,
    password: str,
    project: str,
    repository: str,
    arch: str,
    package: str,
    timeout: int = 3600,
    interval: int = 30
) -> bool:
    """轮询等待构建完成（非 building 状态）"""
    start_time = time.time()
    print(f"开始轮询构建状态（超时时间：{timeout}秒，间隔：{interval}秒）")
    
    while time.time() - start_time < timeout:
        status = check_build_status(
            obs_url=obs_url,
            username=username,
            password=password,
            project=project,
            repository=repository,
            arch=arch,
            package=package
        )
        
        print(f"当前状态：{status}，已等待 {int(time.time()-start_time)} 秒")
        
        if status == "building":
            # 仍在构建，继续等待
            time.sleep(interval)
        elif status in ["succeeded", "failed", "excluded", "disabled"]:
            # 构建结束（无论成功或失败）
            print(f"构建已完成，最终状态：{status}")
            return True
        else:
            # 未知状态，可能网络异常，继续轮询
            print(f"未知状态：{status}，继续轮询...")
            time.sleep(interval)
    
    print(f"构建超时（超过 {timeout} 秒）")
    return False


def download_build_log(
    obs_url: str,
    username: str,
    password: str,
    project: str,
    repository: str,
    arch: str,
    package: str,
    local_log_path: str
) -> bool:
    """
    下载构建日志到本地文件
    
    参数:
        local_log_path: 本地保存日志的路径（如 "./build_log.txt"）
    """
    # 编码 URL 中的特殊字符
    encoded_project = quote(project, safe='')
    encoded_repo = quote(repository, safe='')
    encoded_arch = quote(arch, safe='')
    encoded_package = quote(package, safe='')
    
    url = f"{obs_url}/build/{encoded_project}/{encoded_repo}/{encoded_arch}/{encoded_package}/_log"
    
    try:
        response = requests.get(
            url,
            auth=HTTPBasicAuth(username, password),
            headers={"Accept": "text/plain"}  # 指定接收纯文本格式
        )
        
        if response.status_code == 200:
            # 保存日志内容到本地文件
            with open(local_log_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            print(f"日志已成功下载到: {local_log_path}")
            return True
        else:
            print(f"下载日志失败，状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
    
    except Exception as e:
        print(f"下载日志异常: {str(e)}")
        return False


if __name__ == "__main__":
    OBS_API_URL = "https://api.opensuse.org"
    OBS_USERNAME = "lalala123"
    OBS_PASSWORD = "zhaochenyu921"  # 替换为实际密码
    PROJECT = "home:lalala123"
    REPOSITORY = "openSUSE_Factory_ARM"
    ARCH = "aarch64"
    PACKAGE = "amanda"

    trigger_rebuild_with_cmd(
        obs_url=OBS_API_URL,
        username=OBS_USERNAME,
        password=OBS_PASSWORD,
        project=PROJECT,
        repository=REPOSITORY,
        arch=ARCH,
        package=PACKAGE
    )
    
    # 检查状态
    status = check_build_status(
        obs_url=OBS_API_URL,
        username=OBS_USERNAME,
        password=OBS_PASSWORD,
        project=PROJECT,
        repository=REPOSITORY,
        arch=ARCH,
        package=PACKAGE
    )
    print(f"初始状态：{status}")
    
    # 轮询等待完成
    if wait_for_build_complete(
        obs_url=OBS_API_URL,
        username=OBS_USERNAME,
        password=OBS_PASSWORD,
        project=PROJECT,
        repository=REPOSITORY,
        arch=ARCH,
        package=PACKAGE,
        timeout=1800  # 30分钟超时
    ):
        print("构建已完成，可以下载日志")
    else:
        print("构建未完成或超时")

    # 下载日志
    if download_build_log(
        obs_url=OBS_API_URL,
        username=OBS_USERNAME,
        password=OBS_PASSWORD,
        project=PROJECT,
        repository=REPOSITORY,
        arch=ARCH,
        package=PACKAGE,
        local_log_path="./obs_build.log"
    ):
        print("日志下载成功")

    