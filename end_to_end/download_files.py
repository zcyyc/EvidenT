import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import quote
import xml.etree.ElementTree as ET
import os

# 复用之前的源文件下载函数
def download_source_file(obs_url, username, password, project, package, filename, local_save_path):
    encoded_project = quote(project, safe='')
    encoded_package = quote(package, safe='')
    encoded_filename = quote(filename, safe='')
    url = f"{obs_url}/source/{encoded_project}/{encoded_package}/{encoded_filename}"
    
    try:
        response = requests.get(
            url,
            auth=HTTPBasicAuth(username, password),
            headers={"Accept": "*/*"}
        )
        if response.status_code == 200:
            os.makedirs(os.path.dirname(local_save_path), exist_ok=True)
            try:
                with open(local_save_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
            except UnicodeDecodeError:
                with open(local_save_path, 'wb') as f:
                    f.write(response.content)
            print(f"已下载源文件：{local_save_path}")
            return True
        else:
            print(f"下载源文件 {filename} 失败，状态码：{response.status_code}")
            return False
    except Exception as e:
        print(f"下载 {filename} 异常：{e}")
        return False


def download_all_source_files(
    obs_url: str,
    username: str,
    password: str,
    project: str,
    package: str,
    local_dir: str
) -> None:
    """下载指定 package 下的所有源文件"""
    # 1. 获取源文件列表
    encoded_project = quote(project, safe='')
    encoded_package = quote(package, safe='')
    list_url = f"{obs_url}/source/{encoded_project}/{encoded_package}"
    
    try:
        response = requests.get(
            list_url,
            auth=HTTPBasicAuth(username, password),
            headers={"Accept": "application/xml"}
        )
        if response.status_code != 200:
            print(f"获取源文件列表失败，状态码：{response.status_code}")
            return
        
        # 2. 解析 XML 中的文件名（OBS 返回的列表格式：<directory><entry name="文件名" .../></directory>）
        root = ET.fromstring(response.text)
        # 提取所有 <entry> 标签的 name 属性（即文件名）
        filenames = [entry.get('name') for entry in root.findall('.//entry') if entry.get('name')]
        
        if not filenames:
            print(f"package {package} 下没有源文件")
            return
        
        # 3. 逐个下载文件
        print(f"发现 {len(filenames)} 个源文件，开始下载...")
        for filename in filenames:
            # 本地保存路径：local_dir/filename
            local_save_path = os.path.join(local_dir, filename)
            download_source_file(
                obs_url=obs_url,
                username=username,
                password=password,
                project=project,
                package=package,
                filename=filename,
                local_save_path=local_save_path
            )
        
        print(f"所有源文件已下载到：{local_dir}")
    
    except Exception as e:
        print(f"获取源文件列表异常：{str(e)}")


# 示例用法
if __name__ == "__main__":
    OBS_API_URL = "https://api.opensuse.org"
    OBS_USERNAME = "lalala123"
    OBS_PASSWORD = "zhaochenyu921"
    PROJECT = "home:lalala123"
    PACKAGE = "amanda"
    # 本地保存目录（自动创建）
    LOCAL_SOURCE_DIR = f"D:\\PythonCodes\\aiops_mcp\\end_to_end\\obs_data\\home_lalala123\\{PACKAGE}"
    
    # 下载所有源文件
    download_all_source_files(
        obs_url=OBS_API_URL,
        username=OBS_USERNAME,
        password=OBS_PASSWORD,
        project=PROJECT,
        package=PACKAGE,
        local_dir=LOCAL_SOURCE_DIR
    )