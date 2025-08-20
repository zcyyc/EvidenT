import os
from mcp.server.fastmcp import FastMCP
import pandas as pd
from mcp_server_tools.rca_tools.anomaly_detection import RunAnomalyDetection
from mcp_server_tools.rca_tools.arch_know_search import architecture_knowledge_retriever
from mcp_server_tools.rca_tools.historical_case import historical_case_retriever
from mcp_server_tools.auto_repair.get_repo_structure import get_project_structure_from_local
from mcp_server_tools.auto_repair.check_build_res import check_main
from mcp_server_tools.auto_repair.upload_files import main_upload
import tarfile
import zipfile
import shutil
mcp = FastMCP("auto_repair_server")

@mcp.tool()
def log_anomaly_detection_tool(input_dir: str):
    """
    Detect anomalies in the log file and return structured results.
    Args:
        input_dir (str): The package path containing log files. For example, "CodeDataset/obs_data/home_lalala123_RISCV/akamai-purge".
    """
    anomaly_detector = RunAnomalyDetection(input_dir=input_dir)
    anomaly_detector.batch_process()
    anomaly_detector.extract_log_templates()
    anomalous_res = anomaly_detector.run_anomaly_detection()

    return anomalous_res

# @mcp.tool()
# def extract_error_stack(input_dir: str):
#     """
#     Extract the end stack of the error log to guide the subsequent root cause location process.
#     Args:
#         input_dir (str): The package path containing log files. For example, "CodeDataset/obs_data/home_lalala123_RISCV/akamai-purge".
#     """
#     error_log_path = os.path.join(input_dir, 'obs_log_None_standard_riscv64.txt')
#     with open(error_log_path, 'r', encoding='utf-8') as f:
#         log_content = f.read()
#     log_content = log_content[-3000:]
#     return log_content


@mcp.tool()
def spec_directive_tool(input_dir: str):
    """
    Parses spec files to return either build phase instructions or dependency declarations
    based on the provided log text name.
    Args:
        input_dir (str): The package path containing log files. For example, "CodeDataset/obs_data/home_lalala123_RISCV/akamai-purge".
    """
    log_text_name = input_dir.split('/')[-1] + '.spec'
    log_text_name = log_text_name.replace('failed_', '')

    path = os.path.join(input_dir, log_text_name)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return content

    
@mcp.tool()
def history_case_tool(query_log) -> pd.DataFrame:
    """
    Given an exception log text, retrieve the context where similar exceptions occurred in history.
    Args:
        query_log (str): The error log text to query. For example, "Error: Failed to connect to server".
    """
    return historical_case_retriever(query_log)

@mcp.tool()
def get_example_solution_tool():
    """
    Get the example solution from the log file.
    """
    soluction_cases = pd.read_csv('/Users/zcy/Codes/PythonCodes/aiops_mcp/knowledge_base/history_soluction.csv')
    return soluction_cases


@mcp.tool()
def arch_knowledge_search_tool(log_chunk_content: str) -> dict:
    """
    Given an exception log text, search the software build knowledge base for exact matches. 
    Returns the first paragraph if found, otherwise suggests similar entities.
    Args:
        log_chunk_content (str): The log chunk content to query. For example, "Error: Failed to connect to server".

    """
    return architecture_knowledge_retriever(log_chunk_content)


@mcp.tool()
def get_structure_of_files(package_path) -> dict:
    """
    Retrieve the architecture diagram of the entire project.
    Args:
        package_path (str): The path of the package.
    Returns:
        dict: The architecture diagram of the entire project.
    """
    return get_project_structure_from_local(package_path)


@mcp.tool()
def get_failure_solution(package_path: str):
    """
    Get the failure solution of the build failure.
    Args:
        package_path (str): The path of the package.
    Returns:
        str: The failure solution of the build failure.
    """
    package_name = package_path.split("/")[-1]

    try:
        root_cause_path = os.path.join("analysis_results", f"{package_name}.txt")
        if not os.path.exists(root_cause_path):
            return f"root cause file not found: {root_cause_path}"
            
        with open(root_cause_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            start_marker = "Solution: "
            start_index = content.find(start_marker)

            if start_index != -1:
                root_cause_result = content[start_index + len(start_marker):]
                return f"The failure solution is: {root_cause_result}"
            else:
                result = content[-500:]
                return f"Could not find solution in the log, here is the last 500 characters of the log: {result}"
        
    except Exception as e:
        return f"get failure solution failed: {str(e)}"


@mcp.tool()
def modify_file_tool(file_path: str, new_content: str):
    """
    Replace the entire content of a file with new content.
    Args:
        file_path (str): The path of the file to modify.
        new_content (str): The complete new content to replace the file.
    Returns:
        str: The result of the modification operation.
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return f"Error: File does not exist - {file_path}"
            
        # 直接覆盖文件内容
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        return f"Success: Replaced entire content of {file_path}\nNew content preview: {new_content[:100]}..."
        
    except Exception as e:
        return f"Modify file failed: {str(e)}"


SUPPORTED_FORMATS = {
            'tar.gz': {'extensions': ['.tar.gz', '.tgz'], 'mode': 'r:gz'},
            'tar.xz': {'extensions': ['.tar.xz', '.txz'], 'mode': 'r:xz'},
            'tar.bz2': {'extensions': ['.tar.bz2', '.tbz'], 'mode': 'r:bz2'},
            'zip': {'extensions': ['.zip'], 'mode': 'r'}
        }


def get_archive_format(file_path: str) -> tuple:
    """
    Determine the compression format of the file.
    
    Args:
        file_path: File path
        
    Returns:
        Format name and corresponding mode, if not supported then return (None, None)
    """
    for fmt, info in SUPPORTED_FORMATS.items():
        for ext in info['extensions']:
            if file_path.lower().endswith(ext):
                return (fmt, info['mode'])
    return (None, None)


@mcp.tool()
def extract_archive_tool(package_path: str):
    """
    Extract compressed files in various formats and automatically process directory and file paths.
    
    Args:
        package_path (str): Can be:
            1. The directory path containing the compressed file
            2. The path directly pointing to the compressed file (supports zip, tar.gz, tar.xz, etc.)
    """
    try:
        archive_path = None
        package_dir = None
        archive_file = None
        
        # 检查package_path是文件还是目录
        if os.path.isfile(package_path):
            # 检查是否为支持的压缩文件
            fmt, _ = get_archive_format(package_path)
            if fmt:
                archive_path = package_path
                package_dir = os.path.dirname(archive_path)
                archive_file = os.path.basename(archive_path)
            else:
                return f"Error: Unsupported archive format for '{package_path}'。Supported formats: {', '.join(SUPPORTED_FORMATS.keys())}"
        
        elif os.path.isdir(package_path):
            # 在目录中查找支持的压缩文件
            found = False
            for item in os.listdir(package_path):
                item_path = os.path.join(package_path, item)
                if os.path.isfile(item_path):
                    fmt, _ = get_archive_format(item_path)
                    if fmt:
                        archive_path = item_path
                        archive_file = item
                        package_dir = package_path
                        found = True
                        break
            
            if not found:
                return f"Error: No supported archive file found in directory '{package_path}'。Supported formats: {', '.join(SUPPORTED_FORMATS.keys())}"
        
        else:
            return f"Error: Invalid path '{package_path}'。It must be a directory or a supported archive file."
        
        # 创建解压目录
        extract_dir = os.path.join(package_dir, "extracted")
        # 确保解压目录为空
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)
        
        # 执行解压
        fmt, mode = get_archive_format(archive_path)
        if fmt in ['tar.gz', 'tar.xz', 'tar.bz2']:
            with tarfile.open(archive_path, mode) as tar:
                tar.extractall(extract_dir)
        elif fmt == 'zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
        return f"Successfully extracted {archive_file} ({fmt}) to {extract_dir}"
        
    except Exception as e:
        return f"Extraction failed: {str(e)} (path: {package_path})"


@mcp.tool()
def compress_to_archive_tool(package_path: str):
    """
    Compress the extracted directory back to the original archive format.
    
    Args:
        package_path (str): The parent directory path containing the original compressed file and the "extracted" subdirectory.
                           Example: "temp_workspace/failed_Bear" (not including "extracted")
    """
    try:
        # 参数验证
        if not package_path or not isinstance(package_path, str):
            return "Error: package_path must be a valid string path."
            
        if "extracted" in package_path:
            return f"Error: package_path should not contain 'extracted'. Correct example: {os.path.dirname(package_path) if package_path.endswith('extracted') else 'temp_workspace/pkg'}"
        
        # 构建解压目录路径
        extracted_dir = os.path.join(package_path, "extracted")
        if not os.path.exists(extracted_dir):
            return f"Error: Extracted directory '{extracted_dir}' not found. No need to compress."
            
        # 查找原始压缩文件并确定格式
        original_archive = None
        original_fmt = None
        
        for item in os.listdir(package_path):
            item_path = os.path.join(package_path, item)
            if os.path.isfile(item_path):
                fmt, _ = get_archive_format(item_path)
                if fmt:
                    original_archive = item_path
                    original_fmt = fmt
                    break
        
        if not original_archive:
            return f"Error: No supported original archive file found in directory '{package_path}'. Supported formats: {', '.join(SUPPORTED_FORMATS.keys())}"
        
        # 创建修复后的压缩包
        original_filename = os.path.basename(original_archive)
        output_archive = os.path.join(package_path, f"{original_filename}")
        
        # 删除原有修复的压缩包
        if os.path.exists(output_archive):
            os.remove(output_archive)
        
        # 根据原始格式进行压缩
        if original_fmt in ['tar.gz', 'tar.xz', 'tar.bz2']:
            mode = SUPPORTED_FORMATS[original_fmt]['mode'].replace('r', 'w')
            with tarfile.open(output_archive, mode) as tar:
                for item in os.listdir(extracted_dir):
                    item_path = os.path.join(extracted_dir, item)
                    tar.add(item_path, arcname=item)
        elif original_fmt == 'zip':
            with zipfile.ZipFile(output_archive, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                for root, _, files in os.walk(extracted_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, extracted_dir)
                        zip_ref.write(file_path, arcname)
        
        # 删除extracted目录
        shutil.rmtree(extracted_dir)

        return f"Success: Compressed to {output_archive} ({original_fmt}), temporary extracted directory has been deleted."
        
    except Exception as e:
        return f"Compression failed: {str(e)}"


@mcp.tool()
def upload_file_to_obs_tool(package_path: str):
    """
    Upload the repaired package folder to OBS to verify the repair process.
    
    Args:
        package_path (str): The parent directory path containing the original compressed file and other files like *.spec.
    """
    # 检查package_path是否是目录
    if not os.path.isdir(package_path):
        return f"Error: Invalid path '{package_path}'。It must be a directory."
    has_spec = any(
        f.endswith('.spec') 
        for f in os.listdir(package_path)
        if os.path.isfile(os.path.join(package_path, f))
    )
    if not has_spec:
        return f"Error: Directory '{package_path}' has no .spec file (required for OBS upload)."

    package_name = os.path.basename(package_path)
    try:
        obs_result = main_upload(package_name, package_path)
        # 检查上传结果是否包含错误（假设main_upload返回字符串或字典）
        if "error" in str(obs_result).lower():
            return f"Upload failed: {obs_result}"
        return f"Upload successful. OBS result: {obs_result}"
    except Exception as e:
        return f"Error during upload: {str(e)}"
    

@mcp.tool()
def check_build_result(input_dir:str, package_name: str):
    """
    Check the build result in OBS.
    
    Args:
        input_dir (str): The path of the directory to check.
        package_name (str): The name of the package to check.
    """
    try:
        obs_result = check_main(input_dir, package_name)
        return f"Build result check successful. OBS result: {obs_result}"
    except Exception as e:
        return f"Error during build result check: {str(e)}"

# Start the server if this file is run directly
if __name__ == "__main__":
    mcp.run(transport='stdio')
