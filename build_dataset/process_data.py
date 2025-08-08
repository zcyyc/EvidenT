import pandas as pd
import pathlib
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
import json
import concurrent.futures
from typing import List, Dict
import threading
import time

# 线程锁，确保共享数据修改安全
lock = threading.Lock()
# 全局计数器：记录任务进度和结果
counters = {
    "total": 0,       # 总任务数
    "completed": 0,   # 已完成任务数
    "success": 0,     # 成功任务数
    "failed": 0       # 失败任务数
}


def get_package_file_list(
    obs_api_url, obs_username, obs_password, project, package, rev=None, srcmd5=None
):
    """
    获取指定package下的文件列表
    :param project: 项目名（如openSUSE:Factory）
    :param package: 包名（如halloy）
    :param rev: 版本号参数（可选，如9）
    :param srcmd5: 源码MD5参数（可选）
    :return: 文件列表（字典列表，包含文件名、大小等信息）
    """
    # 构建请求URL
    url = f"{obs_api_url}/source/{project}/{package}"

    # 拼接查询参数（rev和srcmd5）
    params = {}
    if rev is not None:
        params["rev"] = rev
    if srcmd5 is not None:
        params["srcmd5"] = srcmd5

    # 设置请求头（OBS API需指定XML格式）
    headers = {"Accept": "application/xml; charset=utf-8"}

    try:
        # 发送带认证的GET请求
        response = requests.get(
            url,
            auth=HTTPBasicAuth(obs_username, obs_password),
            params=params,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()  # 触发HTTP错误（如401认证失败、404不存在）
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {str(e)}")
        return []

    # 解析XML响应（OBS API返回XML格式，而非JSON）
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        print("XML解析失败，可能是响应格式错误")
        return []

    # 提取文件列表（XML中<entry>标签对应文件）
    file_list = []
    for entry in root.findall(".//entry"):
        # 从XML标签中提取文件名、大小、类型等信息
        file_name = entry.attrib["name"]
        file_size = entry.attrib["size"]

        file_list.append(
            {
                "name": file_name,
                "size": file_size,
            }
        )

    return file_list


def compare_file_changes(prev_files, curr_files):
    """
    比较两个文件列表的差异（同时检查文件名和大小）
    prev_files/curr_files 格式：[{name: str, size: str/int}, ...]
    返回差异描述字符串
    """
    # 转换为 {文件名: 大小} 的字典，便于快速查找
    prev_dict = {f["name"]: f["size"] for f in prev_files}
    curr_dict = {f["name"]: f["size"] for f in curr_files}

    # 分类差异类型
    added = []  # 新增文件（当前有，之前无）
    removed = []  # 删除文件（之前有，当前无）
    modified = []  # 修改文件（名称相同，大小不同）

    # 检查新增和修改的文件
    for name, curr_size in curr_dict.items():
        if name not in prev_dict:
            added.append(name)
        else:
            prev_size = prev_dict[name]
            if str(prev_size) != str(curr_size):  # 兼容字符串或数字类型的大小
                modified.append(f"{name}（大小变化: {prev_size} → {curr_size}）")

    # 检查删除的文件
    for name in prev_dict:
        if name not in curr_dict:
            removed.append(name)
    
    # 若全是补丁文件，则将新增合并到修改部分（视为对原文件的修改）
    if added:
        # 判断所有新增文件是否均以.patch或.diff结尾
        all_patches = all(
            name.endswith(('.patch', '.diff')) 
            for name in added
        )
        if all_patches:
            # 将新增的补丁文件合并到修改列表
            modified.extend([f"{name}（新增补丁文件）" for name in added])
            added = []  # 清空新增列表（视为无新增）

    # 构建差异描述
    total_diff = len(added) + len(removed) + len(modified)
    if total_diff == 0:
        return "0file diff"

    diff_info = []
    if added:
        diff_info.append(f"新增: {', '.join(added)}")
    if removed:
        diff_info.append(f"删除: {', '.join(removed)}")
    if modified:
        diff_info.append(f"修改: {', '.join(modified)}")

    return f"{total_diff}file diff: {'; '.join(diff_info)}"


def process_package(
    obs_api_url,
    obs_username,
    obs_password,
    package: str,
    df_pkg: pd.DataFrame,
    groups: Dict[str, List[str]],
    reasons: Dict[str, List[Dict[str, str]]],
) -> None:
    """处理单个包的分析逻辑，线程安全"""
    global counters
    success = False
    
    try:
        status_history = [s.lower() for s in df_pkg["code"].tolist()]
        reason_history = df_pkg["reason"].tolist()
        build_records = df_pkg.to_dict("records")

        # 处理状态转换分组（线程安全写入）
        if len(status_history) >= 2:
            first_status = status_history[0]
            last_status = status_history[-1]
            with lock:
                if first_status == "succeeded" and last_status == "failed":
                    groups["s-f"].append(package)
                elif first_status == "failed" and last_status == "succeeded":
                    groups["f-s"].append(package)

        # 处理文件差异和原因统计
        diff_desc = "0file diff"
        if len(build_records) >= 2:
            prev_build = build_records[-2]
            curr_build = build_records[-1]

            prev_files = get_package_file_list(
                obs_api_url,
                obs_username,
                obs_password,
                prev_build["project"],
                prev_build["package"],
                prev_build["rev"],
                prev_build["srcmd5"],
            )
            curr_files = get_package_file_list(
                obs_api_url,
                obs_username,
                obs_password,
                curr_build["project"],
                curr_build["package"],
                curr_build["rev"],
                curr_build["srcmd5"],
            )

            diff_desc = compare_file_changes(prev_files, curr_files)
        elif len(build_records) == 1:
            diff_desc = "0file diff (仅1次构建)"

        # 线程安全写入原因统计
        final_reason = reason_history[-1] if reason_history else "未知原因"
        with lock:
            if final_reason not in reasons:
                reasons[final_reason] = []
            reasons[final_reason].append({package: diff_desc})
        success = True
    except Exception as e:
        with lock:
            print(f"处理包 {package} 失败: {str(e)}")
    
    finally:
        with lock:
            counters["completed"] += 1
            counters["success" if success else "failed"] += 1
            # 打印进度（每完成10个任务或最后一个任务时）
            if counters["completed"] % 10 == 0 or counters["completed"] == counters["total"]:
                print(f"进度: {counters['completed']}/{counters['total']} 包处理完成 "
                      f"(成功: {counters['success']}, 失败: {counters['failed']})")


def analyze_builds(obs_api_url, obs_username, obs_password, data_file, max_workers=10):
    """
    分析构建数据：
    - groups: 记录状态转换（s-f: 先成功后失败；f-s: 先失败后成功）
    - reasons: 按最终失败/成功原因，统计每个包的文件差异
    """
    global counters

    # 读取并预处理数据
    df = data_file
    df["endtime"] = df["endtime"].astype(int)  # 转换为时间戳（确保可排序）
    df = df.sort_values(by=["package", "endtime"])  # 按包和时间排序

    # 初始化结果结构
    groups = {
        "s-f": [],  # 先 success 后 failed 的包
        "f-s": [],  # 先 failed 后 success 的包
    }
    reasons = {}  # {reason: [{"package_name": "diff_desc"}, ...]}

    # 获取分组后的包数据
    package_groups = list(df.groupby("package"))

    # 重置计数器和耗时记录（避免多次调用时数据残留）
    counters.update({"total": len(package_groups), "completed": 0, "success": 0, "failed": 0})

    # 使用线程池并行处理所有包
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有包处理任务
        futures = [
            executor.submit(
                process_package,
                obs_api_url,
                obs_username,
                obs_password,
                package,
                df_pkg,
                groups,
                reasons,
            )
            for package, df_pkg in package_groups
        ]

        # 等待所有任务完成
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()  # 触发可能的异常
            except Exception as e:
                print(f"处理包时发生错误: {e}")

    return groups, reasons


if __name__ == "__main__":
    obs_api_url = "https://api.opensuse.org"
    obs_username = "lalala123"  # 你的 OBS 用户名
    obs_password = "zhaochenyu921"  # 你的 OBS 密码

    data_file = pd.read_csv("parallel_build_status_full_openSUSE:Factory:RISCV_standard_riscv64.csv")
    groups, reasons = analyze_builds(obs_api_url, obs_username, obs_password, data_file)

    keep_packages = groups.get("f-s", [])
    keep_reasons = [list(item.keys())[0] for item in reasons.get("source change", [])]

    mask_pkg = data_file["package"].isin(keep_packages)
    after_data_file = data_file[mask_pkg].copy()

    mask_reason = data_file["package"].isin(keep_reasons)
    after_data_file = after_data_file[mask_reason]

    after_data_file.to_csv("after_parallel_build_status_full_openSUSE:Factory:RISCV_standard_riscv64.csv", index=False)

    # out_file = pathlib.Path(__file__).parent / "groups.json"
    # with open(out_file, "w", encoding="utf-8") as f:
    #     json.dump(groups, f, ensure_ascii=False, indent=2)

    reasons_file = pathlib.Path(__file__).parent / "reasons.json"
    with open(reasons_file, "w", encoding="utf-8") as f:
        json.dump(reasons, f, ensure_ascii=False, indent=2)
