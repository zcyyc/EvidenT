import re
import os
import json
from typing import List, Dict, Set

class SpecDependencyExtractor:
    def __init__(self):
        # 正则表达式模式定义
        self.install_pattern = re.compile(r'\[.*?\] installing ([^\s-]+-[^\s]+)')
        self.error_pattern = re.compile(r'No module named \'([^\']+)\'|Failed to find package ([^\s]+)')
        self.java_pattern = re.compile(r'java-(\d+\.\d+\.\d+)-openjdk(-devel)?')
        self.mvn_pattern = re.compile(r'mvn_file\.py|javapackages\.maven')
        
        # 已知依赖映射（用于推断缺失依赖）
        self.dependency_mapping = {
            'javapackages': 'javapackages-tools',
            'libxml2': 'libxml2-devel',
            'libxslt': 'libxslt-devel',
            'gcc': 'gcc',
            'gcc-c++': 'gcc-c++',
            'rpmbuild': 'rpm-build'
        }
    
    def extract_from_log(self, log_path: str) -> Dict[str, Set[str]]:
        """从日志文件中提取依赖项"""
        if not os.path.exists(log_path):
            raise FileNotFoundError(f"日志文件 {log_path} 不存在")
        
        installed_packages = set()
        error_dependencies = set()
        inferred_dependencies = set()
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                # 提取安装的包
                install_match = self.install_pattern.search(line)
                if install_match:
                    package = install_match.group(1).split('-')[0]  # 提取包名前缀
                    installed_packages.add(package)
                
                # 提取错误中的依赖
                error_match = self.error_pattern.search(line)
                if error_match:
                    dep = error_match.group(1) or error_match.group(2)
                    if dep:
                        error_dependencies.add(dep)
                
                # 推断Java相关依赖
                if 'openjdk' in line and 'installing' in line:
                    java_match = self.java_pattern.search(line)
                    if java_match:
                        version = java_match.group(1)
                        is_devel = java_match.group(2)
                        inferred_dependencies.add(f"java-{version}-openjdk{'_devel' if is_devel else ''}")
                
                # 推断Maven工具依赖
                if self.mvn_pattern.search(line):
                    inferred_dependencies.add("javapackages-tools")
        
        # 合并依赖项（错误提示优先，其次推断依赖）
        final_dependencies = error_dependencies.copy()
        for dep in inferred_dependencies:
            final_dependencies.add(dep)
        
        # 应用依赖映射（转换为RPM规范依赖）
        spec_dependencies = set()
        for dep in final_dependencies:
            spec_dependencies.add(self.dependency_mapping.get(dep, dep))
        
        return {
            "installed_packages": installed_packages,
            "error_dependencies": error_dependencies,
            "spec_dependencies": spec_dependencies
        }
    
    def format_result(self, result: Dict[str, Set[str]]) -> str:
        """格式化输出依赖项结果"""
        output = "【spec依赖项分析结果】\n\n"
        
        output += "1. 直接安装的包:\n"
        for pkg in sorted(result["installed_packages"]):
            output += f"   - {pkg}\n"
        
        output += "\n2. 错误提示的缺失依赖:\n"
        for dep in sorted(result["error_dependencies"]):
            output += f"   - {dep}\n"
        
        output += "\n3. spec文件建议添加的依赖:\n"
        for dep in sorted(result["spec_dependencies"]):
            output += f"   - BuildRequires: {dep}\n"
        
        output += "\n【推断依据】\n"
        output += " - 错误提示中的缺失模块已转换为RPM依赖\n"
        output += " - Java开发环境自动推断添加-devel后缀\n"
        output += " - Maven工具依赖自动映射为javapackages-tools"
        
        return output
    
    def save_result_to_json(self, result: Dict[str, Set[str]], output_path: str) -> None:
        """将结果保存为JSON文件"""
        # 转换集合为列表，使其可JSON序列化
        serializable_result = {
            key: list(value) if isinstance(value, set) else value
            for key, value in result.items()
        }
        
        # 保存到JSON文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_result, f, ensure_ascii=False, indent=2)
        
        print(f"结果已保存至: {output_path}")


# 使用示例
def demo_spec_file_parser(log_text: str):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = f"{base_dir}/Build_error_logs_data-master/log/{log_text}.txt"  # 替换为实际日志路径
    output_json_path = f"{log_text}_spec_result.json"  # 输出JSON文件路径

    extractor = SpecDependencyExtractor()
    
    try:
        result = extractor.extract_from_log(log_path)
        print(extractor.format_result(result))
        
        # 保存结果为JSON文件
        extractor.save_result_to_json(result, output_json_path)
        
    except Exception as e:
        print(f"依赖提取失败: {str(e)}")