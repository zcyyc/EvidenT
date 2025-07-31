import os
import pathlib
from tqdm import tqdm
import pandas as pd

from mcts.tools.anomaly_detection.Log_Filtering import process_log_file
from mcts.tools.anomaly_detection.anomaly_detector import process_file
from mcts.tools.anomaly_detection.template_parser import process_single_file_drain

# from Log_Filtering import process_log_file
# from anomaly_detector import process_file
# from template_parser import process_single_file_drain

class RunAnomalyDetection:
    def __init__(self, input_dir):
        self.input_dir = input_dir
        self.structure_dir = "structured_logs_all"
        self.parsed_templates_dir = "parsed_templates_drain"
        self.anomaly_res_dir = "anomaly_detection_results"
        os.makedirs(self.structure_dir, exist_ok=True)
        os.makedirs(self.parsed_templates_dir, exist_ok=True)
        os.makedirs(self.anomaly_res_dir, exist_ok=True)

    # 批量提取日志文件
    def batch_process(self):
        data_dir = pathlib.Path(self.input_dir)
        if data_dir.is_dir():
            print(f"Processing directory: {data_dir}")
            files = [f for f in os.listdir(data_dir) if f.endswith((".log", ".txt"))]
            for filename in tqdm(files, desc="Processing Logs"):
                print("filename:", filename)
                process_log_file(os.path.join(data_dir, filename), os.path.join(self.structure_dir, data_dir.name))

    # 提取日志模板
    def extract_log_templates(self):
        for package in pathlib.Path(self.structure_dir).iterdir():
            if package.is_dir():
                files = [f for f in os.listdir(package) if f.endswith(".json")]
                for file in tqdm(files, desc="Drain extracting with preprocessing"):
                    try:
                        process_single_file_drain(file, package, os.path.join(self.parsed_templates_dir, package.name))
                    except Exception as e:
                        print(f"Error processing {file}: {e}")
        print(f"Drain3 processing done. Output saved in {self.parsed_templates_dir}/")


    # 执行异常检测
    def run_anomaly_detection(self):
        # 获取所有JSON文件
        for package in pathlib.Path(self.parsed_templates_dir).iterdir():
            if package.is_dir():
                print(f"Processing package: {package.name}")
                files = [f for f in os.listdir(package) if f.endswith(".json")]
                if not files:
                    print(f"No JSON files found in {package.name}")
                    continue

                # 处理每个文件
                for f in tqdm(files, desc="Processing logs"):
                    try:
                        res = process_file(f, package, os.path.join(self.anomaly_res_dir, package.name))
                        return res
                    except Exception as e:
                        print(f"[ERROR] Failed to process {f}: {str(e)[:200]}")


# def log_anomaly_detection_tool(input_dir: str) -> pd.DataFrame:
#     """Detect anomalies in the log file and return structured results."""
#     anomaly_detector = RunAnomalyDetection(input_dir=input_dir)
#     anomaly_detector.batch_process()
#     anomaly_detector.extract_log_templates()
#     print(anomaly_detector.run_anomaly_detection())


# log_anomaly_detection_tool('D:\\PythonCodes\\aiops_mcp\\end_to_end\\obs_data\\home_lalala123\\perl-Verilog-Perl')