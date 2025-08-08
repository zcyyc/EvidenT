import os
import json
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForCausalLM
os.environ["CUDA_VISIBLE_DEVICES"] = "3,4,5"
import torch

# === 配置路径 ===
STRUCTURED_LOG_DIR = "parsed_templates_all"  # 输入目录：已结构化+模板提取完成的日志
ANOMALY_OUTPUT_DIR = "anomaly_detection_results"  # 输出目录：增加了"anomalous"字段
MODEL_PATH = "/home/chenshiqi/huangzeshun/MCP/Pretrained_model/DeepSeek-R1-Distill-Qwen-7B"

os.makedirs(ANOMALY_OUTPUT_DIR, exist_ok=True)

# === 加载本地模型 ===
print("Loading DeepSeek model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)
print("Model loaded successfully.")

def build_lad_prompt(log_lines: list[str], templates: list[str]) -> str:
    """Build prompt for anomaly detection, emphasizing careful line-by-line error analysis with keyword cues."""
    log_chunk_content = "\n".join(log_lines[-30:])  # Use last 30 lines for better context coverage
    template_examples = "\n".join(f"- {tpl}" for tpl in templates[:5])  # Up to 5 template examples

    return f"""
You are an expert log analyst specializing in build and CI logs. Your task is to carefully examine the following log chunk and determine whether it should be classified as anomalous (i.e., contains errors causing build failure).

Instructions:
- Carefully review every single log line and its corresponding log event template.
- If **any single line** in the chunk contains **clear error indicators** or failure messages, you must mark the entire chunk as anomalous.
- Common error indicators include (but are not limited to) keywords such as:
  "error", "failed", "exception", "traceback", "not found", "missing", "denied", "fatal", "segmentation fault",
  "build failure", "compilation terminated", "bad exit status", "core dumped", "unable to", "could not",
  "dependency conflict", "test failure", "runtime error"
- Ignore lines that only show warnings (e.g., containing "warn" or "deprecation") or normal informational messages (e.g., "chmod", "mv", "cd", progress updates).
- If unsure, lean towards marking as anomalous (better to have false positives than false negatives).

Below are some examples of common log event templates in this chunk to help you understand the log format:

{template_examples}

### Log Chunk to Analyze:
{log_chunk_content}

Please respond with exactly one of the following lines ONLY:
- answer: True   # The log chunk contains critical errors and is anomalous
- answer: False  # The log chunk does not contain critical errors and is normal
""".strip()



# === 使用LLM判断block是否异常 ===
def detect_anomaly_with_llm(log_lines: list[str], templates: list[str]) -> bool:
    """使用LLM分析日志块是否包含导致构建失败的关键错误"""
    prompt = build_lad_prompt(log_lines, templates)
    
    try:
        # Tokenize并准备模型输入
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        
        # 生成响应
        outputs = model.generate(
            **inputs,
            max_new_tokens=20,    # 限制输出长度
            temperature=0.3,      # 平衡创造性和准确性
            top_p=0.9,            # 核采样提高相关性
            do_sample=True,       # 启用采样
            pad_token_id=tokenizer.eos_token_id
        )
        
        # 解码响应
        full_response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        response = full_response.replace(prompt, "").strip()  # 提取模型新增内容
        
        # 调试输出
        if os.getenv("DEBUG_LLM") == "1":
            print("=" * 80)
            print("### PROMPT:")
            print(prompt)
            print("### RESPONSE:")
            print(response)
            print("=" * 80)
        
        # 精确匹配输出格式
        if "answer: True" in response:
            return True
        return False

    except Exception as e:
        print(f"[LLM Error] {str(e)[:200]}...")
        return False  # 出错时默认返回非异常

# === 处理单个结构化日志文件 ===
def process_file(filename: str):
    """处理单个JSON日志文件，添加异常检测结果"""
    input_path = os.path.join(STRUCTURED_LOG_DIR, filename)
    output_path = os.path.join(ANOMALY_OUTPUT_DIR, filename)
    
    if not os.path.exists(input_path):
        print(f"File not found: {input_path}")
        return

    with open(input_path, "r") as f:
        try:
            structured_blocks = json.load(f)
        except json.JSONDecodeError as e:
            print(f"JSON decode error in {filename}: {e}")
            return

    updated_blocks = []
    
    for block in tqdm(structured_blocks, desc=f"Processing {filename}", leave=False):
        parsed_entries = block.get("parsed_entries", [])
        
        # 提取日志内容和模板
        log_lines = [entry["log_content"] for entry in parsed_entries]
        templates = [entry.get("log_event_template", "") for entry in parsed_entries]
        
        # 使用LLM检测异常
        is_anomalous = detect_anomaly_with_llm(log_lines, templates)
        
        # 构造输出结构
        updated_block = {
            "meta_info": block.get("meta_info", {}),
            "parsed_entries": parsed_entries,
            "anomalous": is_anomalous
        }
        updated_blocks.append(updated_block)
    
    # 保存结果
    with open(output_path, "w") as f:
        json.dump(updated_blocks, f, indent=2, ensure_ascii=False)

# === 主流程 ===
def main():
    """主处理流程"""
    # 获取所有JSON文件
    files = [f for f in os.listdir(STRUCTURED_LOG_DIR) if f.endswith(".json")]
    print(f"Found {len(files)} log files for processing")
    
    # 处理每个文件
    for f in tqdm(files, desc="Processing logs"):
        try:
            process_file(f)
        except Exception as e:
            print(f"[ERROR] Failed to process {f}: {str(e)[:200]}")
    
    print("Anomaly detection completed. Results saved to:", ANOMALY_OUTPUT_DIR)

if __name__ == "__main__":
    main()