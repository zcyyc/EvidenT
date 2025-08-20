import os
import pathlib
from tqdm import tqdm
import pandas as pd
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import json
from ad.Log_Filtering import process_log_file
from ad.anomaly_detector import process_file
from ad.template_parser import process_single_file_drain


class RunAnomalyDetection:
    def __init__(self, input_dir, max_lines_threshold=3000):  # 添加行数阈值参数
        self.input_dir = input_dir
        self.package_name = pathlib.Path(input_dir).name
        self.max_lines_threshold = max_lines_threshold  # 最大处理行数阈值
        self.skipped_files = []  # 记录跳过的文件

        self.structure_dir = "/Users/zcy/Codes/PythonCodes/aiops_mcp/structured_logs_all"
        self.parsed_templates_dir = "/Users/zcy/Codes/PythonCodes/aiops_mcp/parsed_templates_drain"
        self.anomaly_res_dir = "/Users/zcy/Codes/PythonCodes/aiops_mcp/anomaly_detection_results"
        self.skip_record_path = os.path.join(self.anomaly_res_dir, "skipped_files.txt")  # 跳过文件记录路径
        os.makedirs(self.structure_dir, exist_ok=True)
        os.makedirs(self.parsed_templates_dir, exist_ok=True)
        os.makedirs(self.anomaly_res_dir, exist_ok=True)

    # 新增：保存跳过的文件记录
    def save_skipped_files(self):
        with open(self.skip_record_path, "a") as f:
            for file in self.skipped_files:
                f.write(f"{file}\n")
        print(f"Saved {len(self.skipped_files)} skipped files to {self.skip_record_path}")

    # 批量提取日志文件
    def batch_process(self):
        data_dir = pathlib.Path(self.input_dir)
        if not data_dir.exists():
            print(f"Error: Input directory {data_dir} does not exist.")
            return
        if not data_dir.is_dir():
            print(f"Error: {data_dir} is not a directory.")
            return

        output_subdir = os.path.join(self.structure_dir, data_dir.name)
        os.makedirs(output_subdir, exist_ok=True)

        print(f"Processing directory: {data_dir}")
        files = [f for f in os.listdir(data_dir) if f.endswith((".log", ".txt"))]
        if not files:
            print(f"No log files (.log/.txt) found in {data_dir}")
            return

        for filename in tqdm(files, desc="Processing Logs"):
            try:
                # 检查文件行数是否超过阈值
                file_path = os.path.join(data_dir, filename)
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    line_count = sum(1 for _ in f)
                
                if line_count > self.max_lines_threshold:
                    print(f"Skipping {filename} (lines: {line_count} > {self.max_lines_threshold})")
                    self.skipped_files.append(file_path)
                    continue  # 跳过处理
                
                process_log_file(
                    file_path,
                    output_subdir
                )
            except Exception as e:
                print(f"Error processing {filename}: {e}")

        # 处理完所有文件后保存跳过的记录
        if self.skipped_files:
            self.save_skipped_files()

    # 提取日志模板（保持不变）
    def extract_log_templates(self):
        current_package_dir = pathlib.Path(self.structure_dir) / self.package_name
        if not current_package_dir.exists() or not current_package_dir.is_dir():
            print(f"Package {self.package_name} not found in {self.structure_dir}")
            return
        files = [f for f in os.listdir(current_package_dir) if f.endswith(".json")]
        for file in files:
            try:
                process_single_file_drain(
                    file,
                    current_package_dir,
                    os.path.join(self.parsed_templates_dir, self.package_name),
                )
            except Exception as e:
                print(f"Error processing {file}: {e}")

    # 执行异常检测（添加对处理后JSON文件的行数检查）
    def run_anomaly_detection(self):
        current_package_dir = pathlib.Path(self.parsed_templates_dir) / self.package_name
        if not current_package_dir.exists() or not current_package_dir.is_dir():
            print(f"Parsed templates for {self.package_name} not found")
            return
        files = [f for f in os.listdir(current_package_dir) if f.endswith(".json")]
        if not files:
            print(f"No JSON files found in {current_package_dir}")
            return
            
        try:
            # 检查JSON文件中的日志条目数量
            file_path = os.path.join(current_package_dir, files[0])
            with open(file_path, "r") as f:
                structured_blocks = json.load(f)
            
            total_entries = sum(len(block.get("parsed_entries", [])) for block in structured_blocks)
            if total_entries > self.max_lines_threshold:
                print(f"Skipping anomaly detection for {files[0]} (entries: {total_entries} > {self.max_lines_threshold})")
                self.skipped_files.append(file_path)
                self.save_skipped_files()
                return None

            res = process_file(
                files[0], 
                current_package_dir, 
                os.path.join(self.anomaly_res_dir, self.package_name)
            )
            print(len(res))
            return res
        except Exception as e:
            print(f"[ERROR] Failed to process {files[0]}: {str(e)[:200]}")

    # 处理跳过文件的方法（后续可调用）
    def process_skipped_files(self):
        """处理之前跳过的文件"""
        if not os.path.exists(self.skip_record_path):
            print("No skipped files found")
            return
            
        with open(self.skip_record_path, "r") as f:
            skipped_files = [line.strip() for line in f if line.strip()]
        
        print(f"Found {len(skipped_files)} skipped files to process")
        for file_path in tqdm(skipped_files, desc="Processing skipped files"):
            # 根据文件类型处理（日志文件或JSON文件）
            if file_path.endswith((".log", ".txt")):
                output_subdir = os.path.join(self.structure_dir, self.package_name)
                process_log_file(file_path, output_subdir)
            elif file_path.endswith(".json"):
                dir_name = os.path.dirname(file_path)
                file_name = os.path.basename(file_path)
                process_file(
                    file_name,
                    dir_name,
                    os.path.join(self.anomaly_res_dir, self.package_name)
                )
        
        # 清空已处理的记录
        os.remove(self.skip_record_path)