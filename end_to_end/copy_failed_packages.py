import re
from bs4 import BeautifulSoup
import requests
from requests.auth import HTTPBasicAuth
import json
import os
from tqdm import tqdm
from xml.etree import ElementTree
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OBSCollector:
    def __init__(self, api_url, username, password, output_dir='obs_data'):
        self.api_url = api_url
        self.output_dir = output_dir
        self.auth = HTTPBasicAuth(username, password)
        os.makedirs(output_dir, exist_ok=True)
        
    def get_failed_builds(self, project, package):
        """获取指定项目和包的所有失败构建"""
        try:
            logger.info(f"正在获取项目 {project} 中包 {package} 的构建结果...")
            url = f"{self.api_url}/build/{project}/_result?package={package}"
            response = requests.get(url, 
                                    auth=self.auth)
            response.raise_for_status()
            
            # 解析XML响应
            root = ElementTree.fromstring(response.text)
            
            failed_builds = []
            for result in root.findall('.//result'):
                repo = result.get('repository')
                arch = result.get('arch')
                
                # 查找对应包的状态（注意：这里要遍历所有status标签）
                for status in result.findall('.//status'):
                    if status.get('package') == package and status.get('code') == 'failed':
                        build_info = {
                            'buildid': result.get('id'),  # 使用result的id作为buildid
                            'repository': repo,
                            'arch': arch,
                            'state': status.get('code'),  # 使用status的code作为实际状态
                            'package': package
                        }
                        failed_builds.append(build_info)
            
            logger.info(f"找到 {len(failed_builds)} 个失败的构建")
            return failed_builds
        except Exception as e:
            logger.error(f"获取构建结果失败: {str(e)}")
            return []
    
    def branch_package(self,
        source_project: str,
        source_package: str,
        target_project: str,
        target_package: str
    ) -> None:
        """
        将一个包从源项目分支到目标项目
        
        参数:
            source_project: 源项目名称
            source_package: 源包名称
            target_project: 目标项目名称
            target_package: 目标包名称
        """
        # 构建API端点URL
        url = f"{self.api_url}/source"
        
        # 设置请求参数
        params = {
            "cmd": "branch",
            "project": source_project,
            "package": source_package,
            "target_project": target_project,
            "target_package": target_package
        }
        
        # 发送POST请求
        response = requests.post(
            url,
            params=params,
            auth=self.auth,
            headers={"Accept": "application/xml; charset=utf-8"}
        )
        
        # 处理响应
        if response.status_code in (200, 201):
            print(f"包 '{source_package}' 已成功分支到 '{target_project}/{target_package}'")
        else:
            print(f"分支失败！状态码: {response.status_code}")
            print(f"错误信息: {response.text}")


def package_name_from_url(url):
    """从OBS源包URL中提取包名"""
    # 发送请求获取页面内容
    response = requests.get(url)
    response.raise_for_status()  # 检查请求是否成功

    # 解析HTML
    soup = BeautifulSoup(response.text, "html.parser")
    tbody = soup.find("tbody")
    if not tbody:
        raise ValueError("未找到tbody标签")

    packagenames_str = tbody.get("data-packagenames").replace("&quot;", "\"")
    package_list = json.loads(packagenames_str)

    # 去重（部分包可能重复出现）
    package_list = list(set(package_list))
    return package_list


if __name__ == "__main__":
    # 配置参数
    api_url = "https://api.opensuse.org"
    # project = 'openSUSE:Factory:ARM' # 320 failures
    # project = 'openSUSE:Factory:zSystems'
    # project = 'openSUSE:Factory:PowerPC'
    # project = 'openSUSE:Factory:RISCV'
    project = 'openSUSE:Factory'  # 所有架构的工厂项目


    obs_username = "lalala123"
    obs_password = "zhaochenyu921"
    target_project = "home:lalala123"

    get_package_list_url = f"https://build.opensuse.org/project/monitor/{project}?blocked=0&building=0&dispatching=0&finished=0&scheduled=0&signing=0&succeeded=0"
    package_list = package_name_from_url(get_package_list_url)
    logger.info(f"从 {get_package_list_url} 获取到 {len(package_list)} 个包名")
    
    for package in tqdm(package_list, total=len(package_list), desc="处理包"):
        safe_project = re.sub(r'[\\/:*?"<>|]', '_', project)
        safe_package = re.sub(r'[\\/:*?"<>|]', '_', package)
        # 输出目录
        output_dir = f'obs_data/{safe_project}/{safe_package}'

        limit = None  # 设置为None表示处理所有失败构建，或设置为数字限制处理数量
        collector = OBSCollector(api_url=api_url, username=obs_username, password=obs_password, output_dir=output_dir)
        failed_builds = collector.get_failed_builds(project, package)
        failed_builds = failed_builds[:10]  # 限制处理前10个失败构建

        if failed_builds:
            collector.branch_package(
                source_project=project,
                source_package=safe_package,
                target_project=target_project,
                target_package=safe_package
            )
            logger.info(f"所有数据已下载到 {output_dir} 目录")
        else:
            logger.info("没有找到失败的构建")