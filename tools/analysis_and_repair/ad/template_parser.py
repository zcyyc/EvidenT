import os
import re
import json
from tqdm import tqdm
from drain3 import TemplateMiner
from drain3.file_persistence import FilePersistence

STRUCTURED_DIR = "structured_logs"
TEMPLATE_OUTPUT_DIR = "parsed_templates_drain"
os.makedirs(TEMPLATE_OUTPUT_DIR, exist_ok=True)

persistence = FilePersistence("drain3_state.bin")
template_miner = TemplateMiner(persistence)


def custom_preprocess(log_line: str) -> str:
    """
    preprocess the log line
    Args:
        log_line: str, the log line
    Returns:
        processed_line: str, the processed log line
    """
    line = log_line.strip()

    # replace the package name-version + 5 or more consecutive # as a whole with <package>-<version><string>
    line = re.sub(
        r"([a-zA-Z0-9_.+-]+-[0-9][a-zA-Z0-9+._~]*)\s*#{5,}",
        r"<package>-<version><string>",
        line,
    )

    # pure special character lines are replaced with <string>
    if re.fullmatch(r"[#=\-~*<>\\\/|]{4,}", line):
        return "<string>"

    # other replacement rules
    line = re.sub(r"\[\d+/\d+\]", "[<progress>]", line)
    line = re.sub(r"/[-\w./]+", "<path>", line)
    line = re.sub(
        r"\S+\.(tar\.gz|zip|deb|rpm|so|log|py|java|sh|txt|conf)", "<file>", line
    )
    line = re.sub(r"\b\d+\.\d+\.\d+\.\d+\b", "<ip>", line)
    line = re.sub(r":\d{2,5}\b", ":<port>", line)
    line = re.sub(
        r"\b([a-zA-Z0-9_.+-]+)-([0-9][a-zA-Z0-9+._~]*)\b", r"<package>-<version>", line
    )
    line = re.sub(r"\b\d+\b", "<num>", line)

    return line


def postprocess_template(template: str) -> str:
    """
    postprocess the template
    Args:
        template: str, the template
    Returns:
        processed_template: str, the processed template
    """

    # replace 5 or more consecutive # characters in the template with <string>
    template = re.sub(r"#{5,}", "<string>", template)
    return template


def process_single_file_drain(input_file: str, structured_dir: str, template_output_dir: str):
    """
    process the single file with drain3
    Args:
        input_file: str, the input file
        structured_dir: str, the structured dir
        template_output_dir: str, the template output dir
    Returns:
        None
    """
    os.makedirs(template_output_dir, exist_ok=True)
    input_path = os.path.join(structured_dir, input_file)
    output_path = os.path.join(template_output_dir, input_file)

    with open(input_path, "r") as f:
        log_blocks = json.load(f)

    parsed_blocks = []

    for block in log_blocks:
        parsed_entries = []

        for entry in block.get("log_entries", []):
            raw_line = entry["log_content"]
            processed_line = custom_preprocess(raw_line)

            result = template_miner.add_log_message(processed_line)
            template = result["template_mined"] if result else processed_line

            refined_template = postprocess_template(template)

            parsed_entries.append(
                {
                    "line": entry["line"],
                    "log_content": raw_line,
                    "log_event_template": refined_template,
                }
            )

        parsed_blocks.append(
            {
                "meta_info": block.get("meta_info", {}),
                "parsed_entries": parsed_entries,
            }
        )

    with open(output_path, "w") as f:
        json.dump(parsed_blocks, f, indent=2, ensure_ascii=False)