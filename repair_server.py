import json
import os
from mcp.server.fastmcp import FastMCP
import pandas as pd
import mcp.types as types
from auto_repair.agent_less_tools.get_repo_structure import get_project_structure_from_local
mcp = FastMCP("RepairServer")

@mcp.prompt()
def get_repair_prompt(package_name, file_name) -> types.GetPromptResult:
    """Call the tools to analyze the log line content and return the result."""

    with open("utils/prompts/repair_prompt.txt", encoding="utf-8") as f:
        prompt = f.read()
        prompt = prompt.format(
            package_name=package_name,
            file_name=file_name
        )
    return [
            {
                "role": "user",
                "content": f"{prompt}"
            }
        ]


@mcp.tool()
def get_structure_of_files(package_name) -> dict:
    """Retrieve the architecture diagram of the entire project."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    package_path = os.path.join(base_dir, "end_to_end/obs_data/home_lalala123", package_name)
    return get_project_structure_from_local(package_path)


@mcp.tool()
def get_failure_content(file_name) -> str:
    """Retrieve the content of a specific information based on the provided file path."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_file = os.path.join(base_dir, ".specstory/history/", file_name)

    content = []
    in_assistant_section = False
    with open(root_file, 'r', encoding='utf-8') as file:
        for line in file:
            # # 检测是否进入 Assistant 部分
            # if "**Assistant**" in line:
            #     in_assistant_section = True
            #     continue  # 跳过标签行本身
            
            # # 收集 Assistant 部分的内容
            # if in_assistant_section:
            #     content.append(line.strip())
            content.append(line.strip())

    content = [line for line in content if line]
    predicts_result = "\n".join(content)
    return predicts_result


# Start the server if this file is run directly
if __name__ == "__main__":
    mcp.run(transport='stdio')
