import asyncio
import os
import json
from typing import Optional, List, Dict, Set, Tuple
from contextlib import AsyncExitStack
from openai import OpenAI
from dotenv import load_dotenv
import traceback
import time
import shutil
import pandas as pd
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters

load_dotenv(".env")


class AutoRepairClient:
    def __init__(self, max_concurrent: int = 1, max_retries: int = 2):
        """Initialize the auto-repair client for end-to-end build failure diagnosis and repair workflow"""
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.client = OpenAI(
            # api_key=os.getenv("CHATANYWHERE_API_KEY"),
            # base_url="https://api.chatanywhere.tech/v1",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        
        # Path configuration
        self.base_dir = "/Users/zcy/Codes/PythonCodes/aiops_mcp/CodeDataset/obs_data/home_lalala123_RISCV"
        self.pre_analysis = "/Users/zcy/Codes/PythonCodes/aiops_mcp/CodeDataset/home_lalala123_RISCV_failure_log_classification.csv"
        self.pre_analysis_df = pd.read_csv(self.pre_analysis)
        
        # Unified directories
        self.log_dir = "auto_repair_log_files"
        self.result_dir = "auto_repair_results"
        self.temp_work_dir = "temp_workspace"
        
        # Create necessary directories
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.result_dir, exist_ok=True)
        os.makedirs(self.temp_work_dir, exist_ok=True)
        
        # Concurrency and retry parameters
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_retries = max_retries
        self.is_session_active = False
        
        # Tracking sets
        self.completed_packages: Set[str] = set()
        self.failed_packages: Set[str] = set()
        
        # Server configuration
        self.server_script = "merge_server.py"
        
        # New: Track file modification history
        self.modification_history: Dict[str, List[Dict]] = {}

    def log_step(self, package_name: Optional[str], message: str):
        """Log processing steps to appropriate log files"""
        if not package_name:
            log_file = os.path.join(self.log_dir, "global_log.txt")
        else:
            log_file = os.path.join(self.log_dir, f"{package_name}_aiops.log")
            
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    async def connect_to_server(self, retry_count: int = 0):
        """Connect to the merge server with retry mechanism"""
        log_msg = f"Connecting to merge server (attempt {retry_count + 1})..."
        print(log_msg)
        self.log_step(None, log_msg)
        
        server_params = StdioServerParameters(
            command="uv", 
            args=["run", self.server_script], env=None
        )

        try:
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            stdio, write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )

            await self.session.initialize()
            self.is_session_active = True
            log_msg = "Successfully connected to merge server"
            print(log_msg)
            self.log_step(None, log_msg)
            return True
        except Exception as e:
            log_msg = f"Failed to connect to merge server: {str(e)}"
            print(log_msg)
            self.log_step(None, log_msg)
            
            # Retry logic
            if retry_count < self.max_retries:
                log_msg = f"Connection failed, retrying... ({self.max_retries - retry_count} attempts remaining)"
                print(log_msg)
                self.log_step(None, log_msg)
                await asyncio.sleep(5)
                return await self.connect_to_server(retry_count + 1)
            return False

    async def _process_package_with_retry(self, package: str, idx: int, total: int, retry: int = 0):
        """Package processing method with retry mechanism"""
        try:
            await self._process_package_wrapper(package, idx, total)
            # Update tracking sets
            self.completed_packages.add(package)
            if package in self.failed_packages:
                self.failed_packages.remove(package)
        except Exception:
            if retry < self.max_retries:
                log_msg = f"Failed to process {package}, retrying... (attempt {retry + 1}/{self.max_retries})"
                print(log_msg)
                self.log_step(package, log_msg)
                # Exponential backoff
                await asyncio.sleep(2 ** retry)
                await self._process_package_with_retry(package, idx, total, retry + 1)
            else:
                log_msg = f"After {self.max_retries} attempts, {package} processing failed - marked as failed"
                print(log_msg)
                self.log_step(package, log_msg)
                self.failed_packages.add(package)

    async def _process_package_wrapper(self, package: str, idx: int, total: int):
        """Package processing wrapper with session management"""
        async with self.semaphore:
            # Check session status, attempt reconnection if closed
            if not self.is_session_active:
                log_msg = f"Session closed, attempting reconnection to process package: {package}"
                print(log_msg)
                self.log_step(package, log_msg)
                
                # Attempt reconnection to merge server
                if not await self.connect_to_server():
                    log_msg = f"Failed to reconnect to merge server, skipping package: {package}"
                    print(log_msg)
                    self.log_step(package, log_msg)
                    raise Exception("Unable to reconnect to server")

            log_msg = f"\n=== Processing progress: {idx}/{total} (current package: {package}) ==="
            print(log_msg)
            self.log_step(None, log_msg)
            
            try:
                await self.process_package(package)
            except Exception as e:
                error_msg = f"Failed to process package {package}: {str(e)}"
                print(error_msg)
                self.log_step(package, error_msg)
                traceback.print_exc()
                self.log_step(package, f"Error details: {traceback.format_exc()}")
                error_file = os.path.join(self.result_dir, f"{package}_error.txt")
                with open(error_file, "w", encoding="utf-8") as f:
                    f.write(f"Failed to process package {package}: {str(e)}\n")
                    f.write(traceback.format_exc())
                raise  # Re-throw exception to trigger retry

    async def process_package(self, package_name: str) -> str:
        """End-to-end processing: detect issues and repair them in one workflow"""
        # Initialize package processing environment
        package_temp_dir, package_path, result_file = self._init_package_environment(package_name)
        if not package_path:
            return f"Initialization failed: cannot find original path for package {package_name}"

        # Load system prompt
        formatted_prompt = self._load_system_prompt(package_name, result_file, package_temp_dir)
        
        # Initialize messages and tools
        messages = self._init_messages(package_name, package_path, formatted_prompt)
        available_tools = await self._get_available_tools(package_name)
        if not available_tools:
            return "Tool acquisition failed: cannot get tool list from merge server"

        # Initialize history
        self.modification_history[package_name] = []
        tool_call_history: List[Tuple[str, str]] = []
        max_repeat_calls = 5  # Prevent tool call loops

        # Build retry loop
        max_build_attempts = 3
        build_attempt = 0
        final_response = ""
        build_success = False

        while build_attempt < max_build_attempts and not build_success:
            build_attempt += 1
            self.log_step(package_name, f"\n=== Build attempt {build_attempt}/{max_build_attempts} ===")
            
            # Update prompt with modification history
            messages = self._update_prompt_with_history(
                messages, formatted_prompt, package_name, package_path, build_attempt
            )

            # Call model for analysis and repair
            try:
                response = self.client.chat.completions.create(
                    model="qwen-max-0125", 
                    messages=messages, 
                    tools=available_tools
                )
            except Exception as e:
                error_msg = f"Model call failed: {str(e)}"
                print(f"ERROR: {error_msg}")
                self.log_step(package_name, f"Error: {error_msg}")
                continue

            content = response.choices[0]
            tool_call_count = 0
            current_build_success = False

            # Process tool calls
            while (not current_build_success) and (content.finish_reason == "tool_calls" and tool_call_count <= 30):
                if not self.is_session_active:
                    log_msg = "Session closed, terminating tool call loop"
                    print(log_msg)
                    self.log_step(package_name, log_msg)
                    break

                tool_call_count += 1
                log_msg = f"\n=== Tool call round {tool_call_count} ==="
                print(log_msg)
                self.log_step(package_name, log_msg)

                # Process all tool calls in the response
                for tool_call in content.message.tool_calls:
                    result_content = await self._process_single_tool_call(
                        tool_call, package_name, package_path, tool_call_history, max_repeat_calls
                    )

                    # Check if this is build result check
                    if tool_call.function.name == "check_build_result":
                        current_build_success = self._parse_build_result(
                            result_content, package_name
                        )

                    # Update message history with tool response
                    messages = self._update_messages_with_tool_response(
                        messages, content, tool_call, result_content
                    )

                # Break if session closed
                if not self.is_session_active:
                    break

                # Continue model interaction
                response, content = await self._continue_model_interaction(
                    messages, available_tools, package_name
                )

            # Check build status and prepare for next attempt if needed
            build_success, final_response = self._handle_build_attempt_result(
                current_build_success, build_attempt, max_build_attempts,
                content, package_name, messages
            )

        # Save final result
        self._save_final_result(package_name, result_file, final_response)
        return final_response

    def _init_package_environment(self, package_name: str) -> Tuple[str, str, str]:
        """Initialize temporary directory and copy package files"""
        package_temp_dir = os.path.join(self.temp_work_dir, package_name)
        os.makedirs(package_temp_dir, exist_ok=True)
        
        # Copy original package to temp directory
        original_package_path = os.path.join(self.base_dir, package_name)
        if not os.path.exists(original_package_path):
            return "", "", ""

        for item in os.listdir(original_package_path):
            src = os.path.join(original_package_path, item)
            dst = os.path.join(package_temp_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        
        log_msg = f"Copied original code to temporary directory: {package_temp_dir}"
        print(log_msg)
        self.log_step(package_name, log_msg)

        result_file = os.path.join(self.result_dir, f"{package_name}_result.txt")
        return package_temp_dir, package_temp_dir, result_file

    def _load_system_prompt(self, package_name: str, result_file: str, temp_dir: str) -> str:
        """Load and format the system prompt"""
        with open("utils/prompts/merged_prompt.txt", "r") as f:
            system_prompt = f.read()
        
        return system_prompt.format(
            package_name=package_name,
            file_name=result_file,
            temp_dir=temp_dir
        )

    def _init_messages(self, package_name: str, package_path: str, formatted_prompt: str) -> List[Dict]:
        """Initialize message history"""
        return [
            {"role": "system", "content": formatted_prompt},
            {
                "role": "user",
                "content": f"Please analyze and repair package {package_name} in the work directory: {package_path}. "
                           f"All modifications must be done in the temporary directory. "
                           f"If build fails after upload to OBS, continue fixing until successful or max retries reached."
            },
        ]

    async def _get_available_tools(self, package_name: str) -> List[Dict]:
        """Get available tools from merge server"""
        try:
            response = await self.session.list_tools()
            return [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                    },
                }
                for tool in response.tools
            ]
        except Exception as e:
            error_msg = f"Failed to list tools from merge server: {str(e)}"
            print(f"ERROR: {error_msg}")
            self.log_step(package_name, f"Error: {error_msg}")
            return []

    def _update_prompt_with_history(self, messages: List[Dict], system_prompt: str, 
                                  package_name: str, package_path: str, build_attempt: int) -> List[Dict]:
        """Update prompt with modification history for subsequent attempts"""
        current_prompt = f"Please analyze and repair package {package_name} in: {package_path}. "
        current_prompt += "All modifications must be done in the temporary directory. "

        # Add previous modifications for retry attempts
        if build_attempt > 1:
            prev_modifications = self.modification_history.get(package_name, [])
            if prev_modifications:
                current_prompt += "\n\nPrevious modifications:\n"
                for mod in prev_modifications:
                    current_prompt += f"File: {mod['file_path']}\n"
                    current_prompt += "Changes:\n"
                    current_prompt += f"Old content:\n{mod['old_content'][:500]}...\n"
                    current_prompt += f"New content:\n{mod['new_content'][:500]}...\n\n"
            
            current_prompt += f"After {build_attempt - 1} attempts, build still failed. "
            current_prompt += "Analyze previous modifications and failures, then provide new repair plan."

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": current_prompt},
        ]

    async def _process_single_tool_call(self, tool_call, package_name: str, package_path: str, tool_call_history: List, max_repeat_calls: int) -> str:
        """Process a single tool call with caching and history tracking"""
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)
        args_key = json.dumps(tool_args, sort_keys=True)
        call_key = (tool_name, args_key)

        # Check for repeated calls
        repeat_count = tool_call_history.count(call_key)
        if repeat_count >= max_repeat_calls:
            log_msg = f"Detected repeated tool call {tool_name} more than {max_repeat_calls} times - terminating"
            print(log_msg)
            self.log_step(package_name, log_msg)
            return f"Tool call {tool_name} terminated: excessive repetitions"

        log_msg = f"Calling merge server tool: {tool_name}"
        print(log_msg)
        self.log_step(package_name, log_msg)
        log_msg = f"Tool arguments: {json.dumps(tool_args, indent=2)}"
        print(log_msg)
        self.log_step(package_name, log_msg)

        # Auto-populate path parameters for analysis tools
        if tool_name in ["log_anomaly_detection_tool", "spec_directive_tool", "extract_error_stack"]:
            tool_args["input_dir"] = package_path

        # Handle file modification tracking
        if tool_name == "modify_file_tool":
            self._track_file_modification(tool_args, package_path, package_name)

        # Execute tool call with caching
        try:
            # Execute tool call with timeout
            result = await asyncio.wait_for(
                self.session.call_tool(tool_name, tool_args),
                timeout=600  # 10 minute timeout
            )

            result_content = ""
            if result.content:
                if isinstance(result.content, list):
                    for result_item in result.content:
                        result_content += result_item.text
                else:
                    result_content = result.content
            else:
                result_content = "No return result"
            
            log_msg = f"Tool return: {result_content[:1000]}..."
            print(log_msg)
            self.log_step(package_name, log_msg)

            tool_call_history.append(call_key)
            return result_content

        except asyncio.TimeoutError:
            error_msg = f"Tool {tool_name} call timed out"
            self.log_step(package_name, error_msg)
            return f"Error: {error_msg}"
        except Exception as e:
            error_msg = f"Tool {tool_name} call failed: {str(e)}"
            self.log_step(package_name, error_msg)
            traceback.print_exc()
            # Mark session inactive on connection issues
            if "session" in str(e).lower() or "connection" in str(e).lower():
                self.is_session_active = False
            return f"Error: {error_msg}"

    def _track_file_modification(self, tool_args: Dict, package_path: str, package_name: str):
        """Track file modifications in history"""
        new_content = tool_args.get("new_content", "")
        if not new_content.strip():
            log_msg = "Invalid modification: new_content is empty"
            print(log_msg)
            self.log_step(package_name, log_msg)
            return

        # Get old content for history
        file_path = tool_args.get("file_path")
        full_path = os.path.join(package_path, file_path)
        old_content = ""
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                old_content = f.read()

        # Save modification history
        self.modification_history[package_name].append({
            "file_path": file_path,
            "old_content": old_content,
            "new_content": new_content.strip(),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        # Clean up content for processing
        tool_args["new_content"] = new_content.strip()
        preview = new_content[:200] + ("..." if len(new_content) > 200 else "")
        log_msg = f"Valid modification received. Preview: {preview}"
        print(log_msg)
        self.log_step(package_name, log_msg)

    def _parse_build_result(self, result_content: str, package_name: str) -> bool:
        """Parse build result to determine success status"""
        try:
            status = result_content.split(': ')[-1]
            if "success" in status.lower():
                self.log_step(package_name, "Build succeeded!")
                return True
            else:
                self.log_step(package_name, f"Build failed: {status}")
                return False
        except IndexError:
            self.log_step(package_name, "Could not parse build result - treating as failure")
            return False

    def _update_messages_with_tool_response(self, messages: List[Dict], content, 
                                          tool_call, result_content: str) -> List[Dict]:
        """Update message history with tool response"""
        messages.append({
            "role": "assistant",
            "content": content.message.content,
            "tool_calls": [tc.model_dump() for tc in content.message.tool_calls]
        })
        messages.append({
            "role": "tool",
            "content": result_content,
            "tool_call_id": tool_call.id,
        })
        return messages

    async def _continue_model_interaction(self, messages: List[Dict], tools: List[Dict], 
                                         package_name: str) -> Tuple:
        """Continue interaction with model after tool calls"""
        try:
            self.log_step(package_name, "Continuing model call to process tool results")
            response = self.client.chat.completions.create(
                model="qwen-max-0125",
                messages=messages,
                tools=tools,
            )
            return response, response.choices[0]
        except Exception as e:
            error_msg = f"Failed to call model: {str(e)}"
            print(error_msg)
            self.log_step(package_name, error_msg)
            return None, None

    def _handle_build_attempt_result(self, current_success: bool, attempt: int, max_attempts: int,
                                    content, package_name: str, messages: List[Dict]) -> Tuple[bool, str]:
        """Handle build attempt result and prepare for next iteration"""
        if current_success:
            final_response = f"Build succeeded after {attempt} attempts!\n{content.message.content or ''}"
            self.log_step(package_name, final_response)
            return True, final_response
        else:
            if attempt < max_attempts:
                self.log_step(package_name, f"Build failed after {attempt} attempts - preparing next attempt")
                messages.append({
                    "role": "user",
                    "content": f"Build failed after {attempt} attempts. "
                               "Analyze the failure reasons and provide further repairs, then retry."
                })
                return False, f"Build attempt {attempt} failed"
            else:
                final_response = f"Max build attempts ({max_attempts}) reached without success.\n"
                final_response += f"Final result: {content.message.content or ''}"
                self.log_step(package_name, final_response)
                return False, final_response

    def _save_final_result(self, package_name: str, result_file: str, content: str):
        """Save final processing result to file"""
        with open(result_file, "w", encoding="utf-8") as f:
            f.write(content)
        self.log_step(package_name, f"Final result saved to: {result_file}")

    async def process_all_packages(self):
        """Process all packages found in the base directory"""
        # Get list of packages (directories in base_dir)
        if not os.path.exists(self.base_dir):
            log_msg = f"Base directory not found: {self.base_dir}"
            print(log_msg)
            self.log_step(None, log_msg)
            return

        packages = [
            item
            for item in os.listdir(self.base_dir) if item.startswith("failed")
            if os.path.isdir(os.path.join(self.base_dir, item))
               and f"{item}_repair.txt" not in os.listdir(self.result_dir)
        ]

        packages = packages[:50]
        print(packages)

        if not packages:
            log_msg = f"No packages found in base directory: {self.base_dir}"
            print(log_msg)
            self.log_step(None, log_msg)
            return

        total_packages = len(packages)
        log_msg = f"Found {total_packages} packages to process"
        print(log_msg)
        self.log_step(None, log_msg)

        # Process packages with concurrency control
        tasks = []
        for idx, package in enumerate(packages, 1):
            if package in self.completed_packages:
                log_msg = f"Skipping already completed package: {package}"
                print(log_msg)
                self.log_step(None, log_msg)
                continue
                
            task = asyncio.create_task(
                self._process_package_with_retry(package, idx, total_packages)
            )
            tasks.append(task)

        # Wait for all tasks to complete
        await asyncio.gather(*tasks)

    async def cleanup(self):
        """Clean up resources and sessions"""
        log_msg = "Performing cleanup..."
        print(log_msg)
        self.log_step(None, log_msg)

        # Close the exit stack to clean up resources
        try:
            await self.exit_stack.aclose()
        except Exception as e:
            log_msg = f"Error during cleanup: {str(e)}"
            print(log_msg)
            self.log_step(None, log_msg)

        self.is_session_active = False
        self.session = None

        log_msg = "Cleanup completed"
        print(log_msg)
        self.log_step(None, log_msg)


async def main():
    client = AutoRepairClient(max_concurrent=1, max_retries=2)
    try:
        # Connect to merged server
        if not await client.connect_to_server():
            log_msg = "Failed to connect to merged server, program exiting."
            print(log_msg)
            client.log_step(None, log_msg)
            return
            
        await client.process_all_packages()
        log_msg = "\nAll package processing completed using merged server."
        print(log_msg)
        client.log_step(None, log_msg)
    except Exception as e:
        log_msg = f"Main program execution error: {str(e)}"
        print(log_msg)
        client.log_step(None, log_msg)
        traceback.print_exc()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
    