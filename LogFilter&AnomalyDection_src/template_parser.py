import os
import re
import json
import hashlib
from pathlib import Path
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

# === 配置参数 ===
STRUCTURED_DIR = "structured_logs_all"
TEMPLATE_OUTPUT_DIR = "parsed_templates_all"
CACHE_FILE = "template_cache.json"
MODEL_PATH = "/home/chenshiqi/huangzeshun/MCP/Pretrained_model/DeepSeek-R1-Distill-Qwen-7B"
os.makedirs(TEMPLATE_OUTPUT_DIR, exist_ok=True)

# === 日志模板规则 ===
class TemplateRules:
    @staticmethod
    def preprocess(log_line: str, stage: str) -> str:
        log_line = log_line.strip()
        if stage == "install":
            log_line = re.sub(r"\[\d+/\d+\]", "[<progress>]", log_line)
            log_line = re.sub(r"\b(preinstalling|postinstalling|installing|removing|downloading)\b\s+(\S+)", "<action> <package>", log_line)
        if "error" in log_line.lower():
            log_line = re.sub(r"(error|failed)\s*:\s*.+", "<error_type>: <message>", log_line, flags=re.I)
        if "File" in log_line and "line" in log_line and "in" in log_line:
            log_line = re.sub(r'File ".*?", line \d+, in .*', 'File "<*>", line <*>, in <*>', log_line)

        if log_line.startswith("from ") and "import" in log_line:
            log_line = re.sub(r'from .*? import .*', 'from <*> import (<*>)', log_line)

        if "ModuleNotFoundError" in log_line:
            log_line = "<error_type>: <message>"

        if "exit status" in log_line:
            log_line = re.sub(r'(error|ERROR|Error)?:? Bad exit status from .*? \(%(.*?)\)', r'<error_type>: Bad exit status from <*> (%<stage>)', log_line)

        if re.match(r'.* failed ".*" at .*', log_line):
            log_line = '<worker> failed "<action> <file>" at <timestamp>'
                
        return log_line

    @staticmethod
    def postprocess(template: str) -> str:
        template = template.strip()
        template = template.replace("log_event_template:", "").strip()
        if template.startswith(("'", '"')) and template.endswith(("'", '"')):
            template = template[1:-1].strip()
        template = re.sub(r'(<\w+>)( \1)+', r'\1', template)
        template = re.sub(r'<[^>]*$', '', template)
        return template

    @staticmethod
    def validate(template: str) -> bool:
        return (
            template and
            5 < len(template) < 200 and
            template.count('<') <= 10 and
            '<*>' in template or re.search(r'<\w+>', template)
        )

# === 加载模型 ===
print("Loading DeepSeek model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    device_map="auto"
)
print("Model loaded successfully.")

# === 缓存和工具函数 ===
def hash_log_line(line: str, stage: str = "") -> str:
    return hashlib.md5(f"{stage}||{line.strip()}".encode()).hexdigest()

def load_template_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_template_cache(cache: dict):
    tmp_file = CACHE_FILE + ".tmp"
    with open(tmp_file, 'w') as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp_file, CACHE_FILE)

def build_extract_prompt(log_line: str) -> str:
    return f"""
You are an expert in software package build log data processing, responsible for extracting log 
event templates from log content. 

In simple terms, extracting log event templates from log content involves analyzing log structures 
and patterns to abstract general event templates, replacing variables with placeholders, and 
achieving standardized log representation to facilitate subsequent anomaly detection and root 
cause analysis. Below are several examples: 

Example 1: 
log_line_content: 'Running task 0.0 in stage 0.0 (TID 0)' 
log_event_template: 'Running task <*> in stage <*> (TID <*>)' 

Example 2: 
log_line_content: 'libtoolize: copying file 'm4/libtool.m4'' 
log_event_template: 'libtoolize: copying file '<*>' 

Example 3: 
log_line_content: 'checking for riscv64-openEuler-linux-gnu-gcc... no' 
log_event_template: 'checking for <*>... no' 

Now, please extract the log event template from the following log content and return it in the 
format "log_event_template: ", with no additional content. 

Log content: 
{log_line}
""".strip()


def extract_with_llm(log_line: str, max_retry: int = 2) -> str:
    prompt = build_extract_prompt(log_line)
    for _ in range(max_retry):
        try:
            inputs = tokenizer(prompt, return_tensors="pt")
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
            outputs = model.generate(
                **inputs,
                max_new_tokens=128,
                temperature=0.1,
                do_sample=False
            )
            response = tokenizer.decode(outputs[0], skip_special_tokens=True)
            if lines := response.strip().splitlines():
                template = lines[-1].strip()
                return TemplateRules.postprocess(template)
        except Exception as e:
            print(f"Generation failed: {str(e)}")
            continue
    return log_line

def process_single_file(input_file: str, global_cache: dict) -> dict:
    local_cache = {}
    input_path = os.path.join(STRUCTURED_DIR, input_file)
    with open(input_path, 'r') as f:
        log_blocks = json.load(f)

    parsed_blocks = []

    for block in log_blocks:
        parsed_entries = []
        stage = block.get("meta_info", {}).get("stage", "unknown")

        for entry in block["log_entries"]:
            raw_line = entry["log_content"]
            line_hash = hash_log_line(raw_line, stage)

            if line_hash in global_cache:
                template = global_cache[line_hash]
            elif line_hash in local_cache:
                template = local_cache[line_hash]
            else:
                processed_line = TemplateRules.preprocess(raw_line, stage)
                template = extract_with_llm(processed_line)

                if not TemplateRules.validate(template):
                    with open("invalid_templates.log", "a") as f:
                        f.write(json.dumps({
                            "file": input_file,
                            "line": entry["line"],
                            "log_content": raw_line,
                            "generated": template
                        }, ensure_ascii=False) + "\n")
                    template = processed_line

                local_cache[line_hash] = template

            parsed_entries.append({
                "line": entry["line"],
                "log_content": raw_line,
                "log_event_template": template
            })

        parsed_blocks.append({
            "meta_info": block["meta_info"],
            "parsed_entries": parsed_entries
        })

    output_path = os.path.join(TEMPLATE_OUTPUT_DIR, input_file)
    with open(output_path, 'w') as f:
        json.dump(parsed_blocks, f, indent=2, ensure_ascii=False)

    return local_cache

def main():
    global_cache = load_template_cache()
    processed_files = 0

    files = [f for f in os.listdir(STRUCTURED_DIR) if f.endswith(".json")]
    for file in tqdm(files, desc="Processing logs"):
        try:
            new_cache = process_single_file(file, global_cache)
            global_cache.update(new_cache)
            processed_files += 1
            if processed_files % 10 == 0:
                save_template_cache(global_cache)
        except Exception as e:
            print(f"Error processing {file}: {str(e)}")

    save_template_cache(global_cache)
    print(f"Done. Processed {processed_files}/{len(files)} files.")

if __name__ == "__main__":
    main()
