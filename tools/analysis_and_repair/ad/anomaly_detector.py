import os
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv(".env")

# Reuse a single OpenAI client across calls instead of creating one per request.
_client_lock = threading.Lock()
_client = None


def _get_client() -> OpenAI:
    global _client
    with _client_lock:
        if _client is None:
            _client = OpenAI(
                api_key=os.getenv("DASHSCOPE_API_KEY")
                or os.getenv("API_KEY")
                or os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("DASHSCOPE_API_BASE_URL")
                or os.getenv("API_BASE")
                or os.getenv("OPENAI_API_BASE_URL")
                or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        return _client


def build_lad_prompt(log_lines: list[str], templates: list[str]) -> str:
    """Build prompt for anomaly detection, emphasizing careful line-by-line error analysis with keyword cues."""
    log_chunk_content = "\n".join(
        log_lines[-30:]
    )
    template_examples = "\n".join(
        f"- {tpl}" for tpl in templates[:5]
    )

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


def detect_anomaly_with_llm(log_lines: list[str], templates: list[str]) -> bool:
    """使用LLM分析日志块是否包含导致构建失败的关键错误"""
    prompt = build_lad_prompt(log_lines, templates)

    try:
        client = _get_client()
        response = (
            client.chat.completions.create(
                model=os.getenv("ANOMALY_LLM_MODEL")
                or os.getenv("LLM_MODEL")
                or "qwen-plus-latest",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ]
            )
            .choices[0]
            .message.content
        )
        response = response.strip()

        if os.getenv("DEBUG_LLM") == "1":
            print("=" * 80)
            print("### PROMPT:")
            print(prompt)
            print("### RESPONSE:")
            print(response)
            print("=" * 80)

        # match output format
        if "answer: True" in response:
            return True
        return False

    except Exception as e:
        print(f"[LLM Error] {str(e)[:200]}...")
        return False


def process_file(filename: str, input_path, output_path):
    """
    process a single JSON log file and add anomaly detection results
    Args:
        filename: str, the name of the file to process
        input_path: str, the path to the input directory
        output_path: str, the path to the output directory
    Returns:
        updated_blocks: list, the updated blocks with anomaly detection results
    """
    os.makedirs(output_path, exist_ok=True)
    input_path = os.path.join(input_path, filename)
    output_path = os.path.join(output_path, filename)

    with open(input_path, "r") as f:
        structured_blocks = json.load(f)

    def _detect(block):
        parsed_entries = block.get("parsed_entries", [])
        log_lines = [entry["log_content"] for entry in parsed_entries]
        templates = [entry.get("log_event_template", "") for entry in parsed_entries]
        return detect_anomaly_with_llm(log_lines, templates)

    # Run per-block LLM anomaly checks concurrently; results keep block order.
    # Kept interruptible: on Ctrl+C / errors, queued tasks are cancelled instead
    # of draining the whole queue before shutdown.
    max_workers = max(1, int(os.getenv("EVIDENT_LAD_CONCURRENCY", "4")))
    pool = ThreadPoolExecutor(max_workers=max_workers)
    try:
        flags = list(
            tqdm(
                pool.map(_detect, structured_blocks),
                total=len(structured_blocks),
                desc=f"Processing {filename}",
                leave=False,
            )
        )
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)

    updated_blocks = []
    for block, is_anomalous in zip(structured_blocks, flags):
        if is_anomalous:
            parsed_entries = block.get("parsed_entries", [])
            updated_blocks.append(
                {
                    "anomalous_parts": [
                        "\n" + entry["log_content"] + "\n" for entry in parsed_entries
                    ],
                }
            )

    # save the results
    with open(output_path, "w") as f:
        json.dump(updated_blocks, f, indent=2, ensure_ascii=False)

    return updated_blocks
