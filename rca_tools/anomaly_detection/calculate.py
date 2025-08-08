import os
import json
from pathlib import Path

# === CONFIG ===
RAW_LOG_DIR = "logs_all"
STRUCTURED_LOG_DIR = "structured_logs_all"

def count_raw_lines(file_path):
    with open(file_path, "r", errors="ignore") as f:
        return sum(1 for _ in f)

def count_structured_lines(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        blocks = json.load(f)
        return sum(len(block["log_entries"]) for block in blocks)

def calculate_compression_rate():
    files = [f for f in os.listdir(RAW_LOG_DIR) if f.endswith(".txt")]
    total_raw = 0
    total_structured = 0

    print(f"{'Package':30s} | {'Raw':>6s} | {'Structured':>10s} | {'Compression':>10s}")
    print("-" * 65)

    for file in sorted(files):
        pkg = Path(file).stem
        raw_path = os.path.join(RAW_LOG_DIR, file)
        json_path = os.path.join(STRUCTURED_LOG_DIR, f"{pkg}.json")

        if not os.path.exists(json_path):
            print(f"{pkg:30s} | {'N/A':>6s} | {'N/A':>10s} | {'MISSING':>10s}")
            continue

        raw_lines = count_raw_lines(raw_path)
        structured_lines = count_structured_lines(json_path)

        total_raw += raw_lines
        total_structured += structured_lines

        ratio = 100 * structured_lines / raw_lines if raw_lines > 0 else 0
        print(f"{pkg:30s} | {raw_lines:6d} | {structured_lines:10d} | {ratio:9.2f}%")

    print("-" * 65)
    total_ratio = 100 * total_structured / total_raw if total_raw > 0 else 0
    print(f"{'TOTAL':30s} | {total_raw:6d} | {total_structured:10d} | {total_ratio:9.2f}%")

if __name__ == "__main__":
    calculate_compression_rate()
