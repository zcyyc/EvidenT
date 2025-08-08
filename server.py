import json
import os
from mcp.server.fastmcp import FastMCP
import pandas as pd
import mcp.types as types
from mcts.tools.arch_know_search import demo_architecture_knowledge_retriever
from mcts.tools.context_log_retrieve import demo_log_block_retriever
from mcts.tools.historical_case import demo_historical_case_retriever
from mcts.tools.spec_directive import demo_spec_file_parser
from utils.log_tool_build import detect_anomalies
from utils.metrics_tool_build import detect_anomalies_component_metric, format_results, detect_anomalies_parallel, load_data
from utils.trace_tool_build import main
mcp = FastMCP("Demo")

@mcp.prompt()
def call_tools(log_content_path: str) -> types.GetPromptResult:
    """Call the tools to analyze the log line content and return the result."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_content =  json.load(open(f'{base_dir}/Build_error_logs_data-master/{log_content_path}', 'r', encoding='utf-8'))
    anomaly_logs = []
    for block in log_content:
        if block.get('anomalous') is True:
            for entry in block.get('parsed_entries', []):
                log_line = entry.get('log_event_template')
                log_line = log_line.strip()
                if log_line:
                    anomaly_logs.append(log_line)
    anomaly_logs = "\n".join(anomaly_logs)

    with open("utils/prompts/cot_prompt.txt", encoding="utf-8") as f:
        prompt = f.read()
        prompt = prompt.format(
            input=anomaly_logs
        )
    return [
            {
                "role": "user",
                "content": f"{prompt}"
            }
        ]

@mcp.prompt()
def root_cause_location(result_by_call_tools: str) -> types.GetPromptResult:
    """locate the root cause of the log line"""
    with open("utils/prompts/task.txt", encoding="utf-8") as f:
        prompt = f.read()
        prompt = prompt.format(
            error_inf=result_by_call_tools
        )
    return [
            {
                "role": "user",
                "content": f"{prompt}"
            }
        ]

    
@mcp.prompt()
def lad_template_prompt(log_chunk_content: str) -> types.GetPromptResult:
    """determine whether a log text is anomalous"""
    description = (
        f"""You are an expert in software package build log data processing, responsible for completing log 
        anomaly detection tasks. Specifically, this involves determining whether the log contains error messages (excluding warning 
        messages, only identifying errors that may cause the software build process to interrupt), which can 
        be achieved by identifying abnormal events or behaviors that deviate from normal patterns, and 
        detecting whether the log statements include error messages indicating execution errors in the 
        software system. If errors are present, return "True"; otherwise, return "False".
        Below are several examples:
        \n Example 1:
        \n log_chunk: "[ 6507s] [ERROR] -> [Help 1]\n [ 6507s] [ERROR] \n [ 6507s] [ERROR] To see the full stack trace of the errors, re-run Maven with the -e switch.\n [ 6507s] [ERROR] Re-run Maven using 
        the -X switch to enable full debug logging.\n [ 6507s] [ERROR] \n [ 6507s] [ERROR] For more 
        information about the errors and possible solutions, please read the following articles:\n [ 6507s] 
        [ERROR] [Help 1] http://cwiki.apache.org/confluence/display/MAVEN/MojoFailureException"
        \n answer: True
        \n Example 2:
        \n log_chunk: "[ 82s] [14/426] installing ncurses-libs-6.4-8.oe2309\n [ 86s] [15/426] installing 
        readline-8.2-2.oe2309\n [ 91s] [16/426] installing filesystem-3.16-5.oe2309\n [ 96s] warning: group 
        mail does not exist - using root\n [ 96s] [17/426] installing emacs-filesystem-1:29.1-1.oe2309\n 
        [ 100s] [18/426] installing libgcc-12.3.1-17.oe2309\n [ 107s] [19/426] installing 
        pcre2-10.42-6.oe2309"
        \n answer: False
        \n Now please determine whether the log contains error messages. If it does, please only return 
        "answer: True"; otherwise, return "answer: False". Do not include any additional content.
        Log content:
        {log_chunk_content}
        """
    )
    return [
            {
                "role": "user",
                "content": f"{description}"
            }
        ]
    

# @mcp.tool()
# def log_anomaly_algorithm(csv_path) -> dict:
#     """Return the text is normal or abnormal"""
#     log_data = pd.read_csv(csv_path)
#     anomalies = detect_anomalies(log_data, threshold_std=3.0)
#     anomalies = pd.DataFrame(anomalies)
#     if not anomalies.empty:
#         return anomalies
#     else:
#         return {"message": "No anomalies detected."}

@mcp.tool()
def spec_directive_tool(log_text_name) -> dict:
    """Parses spec files to return either build phase instructions or dependency declarations
    based on the provided log text name."""
    return demo_spec_file_parser(log_text_name)
    
    
@mcp.tool()
def history_case_tool(query_log) -> pd.DataFrame:
    """Retrieve the error log of the current software package build failure."""
    return demo_historical_case_retriever(query_log)

@mcp.tool()
def arch_knowledge_search_tool(log_chunk_content: str) -> dict:
    """Searches the RISC-V software build knowledge base for exact matches. 
    Returns the first paragraph if found, otherwise suggests similar entities."""
    return demo_architecture_knowledge_retriever(log_chunk_content)

@mcp.tool()
def context_log_retrieve_tool(target_id: str) -> list:
    """Retrieve the error log of the current software package build failure."""
    return demo_log_block_retriever(target_id)
    

# Start the server if this file is run directly
if __name__ == "__main__":
    mcp.run(transport='stdio')
