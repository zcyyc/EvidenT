import os
import pathlib
from tqdm import tqdm
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ad.Log_Filtering import process_log_file
from ad.anomaly_detector import process_file
from ad.template_parser import process_single_file_drain
import yaml


class RunAnomalyDetection:
    """
    Main class for running anomaly detection
    """
    def __init__(self, input_dir):
        self.input_dir = input_dir
        self.package_name = pathlib.Path(input_dir).name
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_path = os.path.join(self.base_dir, "config/paths.yaml")
        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.structure_dir = self.config["paths"]["structure_dir"]
        self.parsed_templates_dir = self.config["paths"]["parsed_templates_dir"]
        self.anomaly_res_dir = self.config["paths"]["anomaly_res_dir"]

        os.makedirs(self.structure_dir, exist_ok=True)
        os.makedirs(self.parsed_templates_dir, exist_ok=True)
        os.makedirs(self.anomaly_res_dir, exist_ok=True)

    def batch_process(self):
        """
        batch processing of log files
        """
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
                file_path = os.path.join(data_dir, filename)
                process_log_file(file_path, output_subdir)
            except Exception as e:
                print(f"Error processing {filename}: {e}")

    def extract_log_templates(self):
        """
        extract log templates
        """
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

    def run_anomaly_detection(self):
        """
        run anomaly detection
        """
        current_package_dir = (
            pathlib.Path(self.parsed_templates_dir) / self.package_name
        )
        if not current_package_dir.exists() or not current_package_dir.is_dir():
            print(f"Parsed templates for {self.package_name} not found")
            return
        files = [f for f in os.listdir(current_package_dir) if f.endswith(".json")]
        if not files:
            print(f"No JSON files found in {current_package_dir}")
            return

        try:
            res = process_file(
                files[0],
                current_package_dir,
                os.path.join(self.anomaly_res_dir, self.package_name),
            )
            print(len(res))
            return res
        except Exception as e:
            print(f"[ERROR] Failed to process {files[0]}: {str(e)[:200]}")
