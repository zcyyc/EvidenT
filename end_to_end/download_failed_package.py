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
    
    def download_logs_and_sources(self, project, package, failed_builds, limit=None):
        """下载失败构建的日志和源包"""
        if limit:
            failed_builds = failed_builds[:limit]
            logger.info(f"将处理前 {limit} 个失败构建")
            
        for build in tqdm(failed_builds, desc="下载中"):
            build_id = build['buildid']
            repo = build['repository']
            arch = build['arch']
            
            try:
                # 获取构建详情
                details_url = f"{self.api_url}/build/{project}/{repo}/{arch}/{package}/_status"
                response = requests.get(details_url, 
                                        auth=self.auth)
                response.raise_for_status()
                
                build_details = self._parse_xml_response(response.text)
                
                # 下载失败日志
                log_url = f"{self.api_url}/build/{project}/{repo}/{arch}/{package}/_log"
                log_path = os.path.join(self.output_dir, f"obs_failed_log_{build_id}_{repo}_{arch}.txt")
                self._download_file(log_url, log_path)
                
                # 获取源包信息
                # source_meta_url = f"{self.api_url}/source/{project}/{package}/_meta?meta=1&view=blame"
                package_name = package.split(':')[0]  # 只取包名部分
                file_list_url = f"{self.api_url}/source/{project}/{package_name}"

                source_response = requests.get(file_list_url,
                                               auth=self.auth)
                source_response.raise_for_status()
                
                # 解析源包信息
                source_root = ElementTree.fromstring(source_response.text)
                file_names = [entry.get("name") for entry in source_root.findall(".//entry")]

                # 下载源包
                for file_name in file_names:
                    file_url = f"{self.api_url}/source/{project}/{package_name}/{file_name}"
                    response = requests.get(file_url, auth=self.auth)
                    response.raise_for_status()
                    
                    # 保存文件到本地
                    file_path = os.path.join(self.output_dir, file_name)
                    with open(file_path, "wb") as f:
                        f.write(response.content)
                    print(f"下载完成：{file_name}")
                
                # 保存构建元数据
                meta_path = os.path.join(self.output_dir, f"obs_meta_{build_id}_{repo}_{arch}.json")
                with open(meta_path, 'w') as f:
                    json.dump(build_details, f, indent=2)
                    
            except Exception as e:
                logger.error(f"处理构建 {build_id} 失败: {str(e)}")
    
    def _download_file(self, url, path):
        """下载文件并处理异常"""
        try:
            response = requests.get(url, stream=True, timeout=30, auth=self.auth)
            response.raise_for_status()
            
            with open(path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            logger.debug(f"下载成功: {path}")
        except requests.exceptions.RequestException as e:
            logger.error(f"下载失败: {url}, 错误: {str(e)}")

    def _parse_xml_response(self, xml_text):
        """将XML响应转换为字典结构"""
        root = ElementTree.fromstring(xml_text)
        return self._xml_to_dict(root)
    
    def _xml_to_dict(self, element):
        """递归将XML元素转换为字典"""
        result = {}
        if element.attrib:
            result['@attributes'] = element.attrib
            
        children = list(element)
        if children:
            # 处理子元素
            for child in children:
                child_name = child.tag
                child_dict = self._xml_to_dict(child)
                
                if child_name in result:
                    # 多个相同标签的情况，转为列表
                    if not isinstance(result[child_name], list):
                        result[child_name] = [result[child_name]]
                    result[child_name].append(child_dict)
                else:
                    result[child_name] = child_dict
        else:
            # 没有子元素，直接使用文本内容
            if element.text:
                result['#text'] = element.text.strip()
                
        return result
    

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
    project = 'home:lalala123'

    obs_username = "lalala123"
    obs_password = "zhaochenyu921"

    get_package_list_url = f"https://build.opensuse.org/project/monitor/{project}?blocked=0&building=0&dispatching=0&finished=0&scheduled=0&signing=0&succeeded=0"
    package_list = package_name_from_url(get_package_list_url)
    logger.info(f"从 {get_package_list_url} 获取到 {len(package_list)} 个包名")
    
    # for package in tqdm(package_list, total=len(package_list), desc="处理包"):
    #     safe_project = re.sub(r'[\\/:*?"<>|]', '_', project)
    #     safe_package = re.sub(r'[\\/:*?"<>|]', '_', package)
    #     # 输出目录
    #     output_dir = f'obs_data/{safe_project}/{safe_package}'

    #     limit = None  # 设置为None表示处理所有失败构建，或设置为数字限制处理数量
    #     collector = OBSCollector(api_url=api_url, username=obs_username, password=obs_password, output_dir=output_dir)
    #     failed_builds = collector.get_failed_builds(project, package)
    #     failed_builds = failed_builds[:10]  # 限制处理前10个失败构建

    #     if failed_builds:
    #         collector.download_logs_and_sources(project, package, failed_builds, limit)
    #         logger.info(f"所有数据已下载到 {output_dir} 目录")
    #     else:
    #         logger.info("没有找到失败的构建")
    package = "amanda"
    safe_project = re.sub(r'[\\/:*?"<>|]', '_', project)
    safe_package = re.sub(r'[\\/:*?"<>|]', '_', package)
    # 输出目录
    output_dir = f'obs_data/{safe_project}/{safe_package}'

    limit = None  # 设置为None表示处理所有失败构建，或设置为数字限制处理数量
    collector = OBSCollector(api_url=api_url, username=obs_username, password=obs_password, output_dir=output_dir)
    failed_builds = collector.get_failed_builds(project, package)
    failed_builds = failed_builds[:10]  # 限制处理前10个失败构建

    if failed_builds:
        collector.download_logs_and_sources(project, package, failed_builds, limit)
        logger.info(f"所有数据已下载到 {output_dir} 目录")
    else:
        logger.info("没有找到失败的构建")
