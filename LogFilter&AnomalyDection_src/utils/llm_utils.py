from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

# === 模型路径（根据你的本地部署路径修改）===
MODEL_PATH = "/home/chenshiqi/huangzeshun/MCP/Pretrained_model/DeepSeek-R1-Distill-Qwen-7B"

# === 初始化模型和分词器 ===
print("Loading DeepSeek model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    device_map="auto"
)
print("Model loaded successfully.")

# === 构造 prompt ===
def build_extract_template_prompt(log_line: str) -> str:
    return f"""
You are an expert in software package build log data processing, responsible for extracting log event templates from log content.
In simple terms, extracting log event templates from log content involves analyzing log structures and patterns to abstract general event templates, replacing variables with placeholders, and achieving standardized log representation to facilitate subsequent anomaly detection and root cause analysis. Below are several examples:
Example 1:
log_line_content: 'Running task 0.0 in stage 0.0 (TID 0)'
log_event_template: 'Running task <*> in stage <*> (TID <*>)'
Example 2:
log_line_content: 'libtoolize: copying file \'m4/libtool.m4\''
log_event_template: 'libtoolize: copying file \'<*>\''
Example 3:
log_line_content: 'checking for riscv64-openEuler-linux-gnu-gcc... no'
log_event_template: 'checking for <*> ... no'
Now, please extract the log event template from the following log content and return it in the format "log_event_template: ", with no additional content.
Log content:
{log_line}
""".strip()

# === 调用模型生成模板 ===
def extract_event_template(log_line: str) -> str:
    prompt = build_extract_template_prompt(log_line)
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    outputs = model.generate(
        **inputs,
        max_new_tokens=64,
        temperature=0.0,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id
    )
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # 只提取包含 "log_event_template:" 的行
    for line in response.splitlines():
        if line.lower().strip().startswith("log_event_template"):
            return line.split(":", 1)[-1].strip()
    return ""
