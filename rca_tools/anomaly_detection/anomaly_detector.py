import os
import json
from openai import OpenAI
from tqdm import tqdm

def build_lad_prompt(log_lines: list[str], templates: list[str]) -> str:
    """Build prompt for anomaly detection, emphasizing careful line-by-line error analysis with keyword cues."""
    log_chunk_content = "\n".join(
        log_lines[-30:]
    )  # Use last 30 lines for better context coverage
    template_examples = "\n".join(
        f"- {tpl}" for tpl in templates[:5]
    )  # Up to 5 template examples

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
        user_token = "sk-d034f0182d804ebb98fcce4bbd848ab0"
        client = OpenAI(
            # defaults to os.environ.get("OPENAI_API_KEY")
            api_key=user_token,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        response = (
            client.chat.completions.create(
                model="qwen-plus",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=20,  # 限制输出长度
                temperature=0.3,  # 平衡创造性和准确性
                top_p=0.9,  # 核采样提高相关性
            )
            .choices[0]
            .message.content
        )
        response = response.strip()

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
def process_file(filename: str, input_path, output_path):
    """处理单个JSON日志文件，添加异常检测结果"""
    os.makedirs(output_path, exist_ok=True)
    input_path = os.path.join(input_path, filename)
    output_path = os.path.join(output_path, filename)

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
            "anomalous": is_anomalous,
        }
        updated_blocks.append(updated_block)

    # 保存结果
    with open(output_path, "w") as f:
        json.dump(updated_blocks, f, indent=2, ensure_ascii=False)

    return updated_blocks