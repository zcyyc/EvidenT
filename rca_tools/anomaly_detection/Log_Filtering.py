import os
import re
import json
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict

# === CONFIG ===
ERROR_CONTEXT_RADIUS = 10
MAX_CHUNK_LEN = 10
INPUT_DIR = "logs_all"
MAX_REPEAT_LINES = 3

# === 模式定义 ===
class LogPatterns:
    ERROR = re.compile(
        r'(error|fatal|failed|undefined reference|cannot find|missing|not found|expected|'
        r'error: |undefined symbol|unresolved|CMake Error|make: \*\*\*)',
        re.IGNORECASE
    )
    
    STAGE = {
        'prep': re.compile(r'%prep|starting prep|prep phase', re.I),
        'build': re.compile(r'%build|running build|build phase', re.I),
        'install': re.compile(r'%install|make install|installing', re.I),
        'check': re.compile(r'%check|running tests|check phase', re.I)
    }

    LONG_PATHS = re.compile(r'/([^/\s]+/){5,}[^/\s]+')  


def preprocess_log(lines):
    processed = []
    last_line = None
    repeat_count = 0
    
    for idx, line in enumerate(lines):
        line = line.strip()
        
        # 1. 去除连续重复行
        if line == last_line:
            repeat_count += 1
            if repeat_count >= MAX_REPEAT_LINES:
                continue
        else:
            repeat_count = 0
        
        # 2. 缩短冗长路径
        line = LogPatterns.LONG_PATHS.sub('/.../path/.../', line)
        processed.append((idx + 1, line))
        last_line = line
    
    return processed

# === 阶段检测 ===
def detect_stage(line_content):
    lower = line_content.lower()
    for stage, pattern in LogPatterns.STAGE.items():
        if pattern.search(lower):
            return stage
    return None  # 不更新阶段

# === 动态分块 ===
def create_chunks(block, chunk_size=MAX_CHUNK_LEN, overlap=2):
    """创建重叠分块"""
    for i in range(0, len(block), chunk_size - overlap):
        yield block[i:i + chunk_size]

# === 主处理函数 ===
def process_log_file(filepath, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    package_name = Path(filepath).stem
    
    with open(filepath, 'r', errors='ignore') as f:
        raw_lines = f.readlines()
    
    # 1. 预处理
    preprocessed = preprocess_log(raw_lines)
    
    # 2. 阶段分区
    stage_blocks = defaultdict(list)
    current_stage = 'other'
    
    for line_no, content in preprocessed:
        new_stage = detect_stage(content)
        if new_stage:
            current_stage = new_stage
        stage_blocks[current_stage].append((line_no, content))
    
    # 3. 提取关键块
    final_blocks = []
    
    for stage, lines in stage_blocks.items():
        if stage == 'other' and not any(LogPatterns.ERROR.search(c) for _, c in lines):
            continue
        
        # 找出错误行及其上下文
        error_indices = set()
        for i, (line_no, content) in enumerate(lines):
            if LogPatterns.ERROR.search(content):
                start = max(0, i - ERROR_CONTEXT_RADIUS)
                end = min(len(lines), i + ERROR_CONTEXT_RADIUS + 1)
                error_indices.update(range(start, end))
        
        # 合并相邻区域
        sorted_indices = sorted(error_indices)
        blocks = []
        if sorted_indices:
            current_block = [lines[sorted_indices[0]]]
            for idx in sorted_indices[1:]:
                if idx - current_block[-1][0] > 2:  # 非连续行
                    blocks.append(current_block)
                    current_block = [lines[idx]]
                else:
                    current_block.append(lines[idx])
            blocks.append(current_block)
        
        # 对每个块进行分块处理
        for i, block in enumerate(blocks):
            for chunk in create_chunks(block):
                final_blocks.append({
                    "meta_info": {
                        "log_block_id": f"{package_name}-{stage}-{i}",
                        "stage": stage
                    },
                    "log_entries": [
                        {"line": line_no, "log_content": content}
                        for line_no, content in chunk
                    ]
                })
    
    # 4. 保存结果
    out_path = os.path.join(output_dir, f"{package_name}.json")
    with open(out_path, "w") as f:
        json.dump(final_blocks, f, indent=2)