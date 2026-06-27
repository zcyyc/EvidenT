import asyncio
import os
import json
import time
import traceback
from typing import Dict, List, Optional, Tuple
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from openai import OpenAI
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters
from config_utils import get_path, get_validator_backend, load_config

load_dotenv(".env")


def make_args_key(tool_name: str, tool_args: dict) -> str:
    """
    Generate a stable string key:
        - Include the tool name to avoid conflicts between different tools using the same parameter
        - Use sort_keys with compact delimiters to ensure stability
    """
    return f"{tool_name}::{json.dumps(tool_args, sort_keys=True, ensure_ascii=False, separators=(',', ':'))}"


class AutoRepairClient:
    """
    Lightweight Client:
        - Connects to the MCP Server
        - Sequentially retrieves packages and repairs them one by one (no parallelism)
        - Calls the history/cache/anti-duplication tools maintained by the server
        - Performs several LLM -> Tools cycles and build attempts
    """

    def __init__(
        self,
        max_retries: int = 2,
        max_build_attempts: int = 3,
        max_tool_rounds: int = 30,
    ):
        self.exit_stack = AsyncExitStack()
        self.session: Optional[ClientSession] = None
        self.is_session_active = False

        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE_URL"),
        )

        config = load_config()
        self.config = config
        self.base_dir = get_path(config, "base_dir")
        self.result_dir = get_path(config, "result_dir", "auto_repair_results")
        self.temp_work_dir = get_path(config, "temp_work_dir", "temp_workspace")
        self.log_dir = get_path(config, "log_dir", "auto_repair_log_files")
        os.makedirs(self.result_dir, exist_ok=True)
        os.makedirs(self.temp_work_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        self.validator_backend = get_validator_backend(config)

        self.server_script = "server.py"
        self.max_retries = max_retries
        self.max_build_attempts = max_build_attempts
        self.max_tool_rounds = max_tool_rounds

    # --------------- Infrastructure ---------------
    def _log(self, tag: str, msg: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        path = os.path.join(self.log_dir, f"{tag}.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
        print(msg)

    async def connect(self, attempt: int = 1) -> bool:
        self._log("global", f"Connecting to server... (attempt {attempt})")
        try:
            params = StdioServerParameters(
                command="uv", args=["run", self.server_script]
            )
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(params)
            )
            stdio, write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )
            await self.session.initialize()
            self.is_session_active = True
            self._log("global", "Connected to MCP server.")
            return True
        except Exception as e:
            self._log("global", f"Connect failed: {e}")
            if attempt < self.max_retries:
                await asyncio.sleep(3)
                return await self.connect(attempt + 1)
            return False

    async def list_tools(self) -> List[Dict]:
        assert self.session is not None
        resp = await self.session.list_tools()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema,
                },
            }
            for t in resp.tools
        ]
        return tools

    # --------------- Core Process ---------------
    async def process_all_packages(self):
        """Process all packages and switch to your own package name as needed"""
        if not self.is_session_active and not await self.connect():
            self._log("global", "Cannot connect to MCP server, exit.")
            return

        assert self.session is not None
        # Get the pending package from the server (keep it consistent with the original tool)
        pkg_resp = await self.session.call_tool(
            "get_packages_to_process", {"base_dir": self.base_dir}
        )

        pkg_info = json.loads(pkg_resp.content[0].text)
        if not pkg_info.get("success"):
            self._log("global", f"Get packages failed: {pkg_info.get('message')}")
            return

        packages = pkg_info.get("packages", [])
        package_filter = os.getenv("EVIDENT_PACKAGES")
        if package_filter:
            wanted = {p.strip() for p in package_filter.split(",") if p.strip()}
            packages = [pkg for pkg in packages if pkg in wanted]

        run_cfg = self.config.get("run", {}) or {}
        allowlist = run_cfg.get("package_allowlist") or []
        if allowlist:
            packages = [pkg for pkg in packages if pkg in set(allowlist)]

        limit_value = os.getenv("EVIDENT_PACKAGE_LIMIT") or run_cfg.get("max_packages")
        if limit_value:
            packages = packages[: int(limit_value)]

        self._log("global", f"Found {len(packages)} packages.")

        tools = await self.list_tools()
        blocked = {"init_package_environment_tool"}
        tools = [t for t in tools if t["function"]["name"] not in blocked]
        for idx, pkg in enumerate(packages, 1):
            self._log("global", f"\n=== [{idx}/{len(packages)}] {pkg} ===")
            try:
                await self.process_one_package(pkg, tools)
            except Exception as e:
                self._log(pkg, f"Fatal error: {e}\n{traceback.format_exc()}")

    async def process_one_package(self, package_name: str, tools: List[Dict]):
        """Single package repair: several build attempts + several tool calls"""
        assert self.session is not None

        # 1) Initialize the temporary environment (copy the server to the temp directory)
        init_ret = await self.session.call_tool(
            "init_package_environment_tool",
            {
                "base_dir": self.base_dir,
                "package_name": package_name,
                "temp_work_dir": self.temp_work_dir,
                "result_dir": self.result_dir,
            },
        )
        init_data = json.loads(init_ret.content[0].text)
        if not init_data.get("success"):
            self._log(package_name, f"Init failed: {init_data.get('message')}")
            return

        package_path = init_data["package_path"]
        result_file = init_data["result_file"]

        # 2) Read the system prompt word template
        with open("utils/prompts/merged_prompt_loop.txt", "r") as f:
            system_prompt_tpl = f.read()

        # 3) Multiple build attempts
        build_succeeded = False
        final_text = ""
        for attempt in range(1, self.max_build_attempts + 1):
            self._log(
                package_name,
                f"--- Build attempt {attempt}/{self.max_build_attempts} ---",
            )
            # clear per-attempt cache on server side
            try:
                await self.session.call_tool(
                    "reset_package_cache_tool", {"package_name": package_name}
                )
                self._log(package_name, f"Cache cleared for new attempt {attempt}.")
            except Exception as e:
                self._log(package_name, f"Cache clear failed on attempt {attempt}: {e}")

            # The server concatenates historical changes + the context of the current attempt and returns messages
            upd = await self.session.call_tool(
                "update_prompt_with_history_tool",
                {
                    "package_name": package_name,
                    "package_path": package_path,
                    "build_attempt": attempt,
                    "formatted_prompt": system_prompt_tpl.format(
                        package_name=package_name,
                        file_name=result_file,
                        temp_dir=package_path,
                    ),
                },
            )
            messages = json.loads(upd.content[0].text)["messages"]

            # 4) LLM—Tools Closed Loop (Sequential Loop)
            content, build_ok = await self._llm_tools_loop(
                package_name, package_path, messages, tools
            )
            if build_ok:
                build_succeeded = True
                final_text = f"Build succeeded on attempt {attempt}.\n{content or ''}"
                break
            else:
                # In the next attempt, add a user command to guide the repair process.
                messages.append(
                    {
                        "role": "user",
                        "content": f"Build failed after attempt {attempt}. Continue analyzing and repairing, then retry.",
                    }
                )
                final_text = f"Build failed on attempt {attempt}.\n{content or ''}"

        # 5) Save the result
        with open(result_file, "w", encoding="utf-8") as f:
            f.write(final_text)
        self._log(package_name, f"Final saved to {result_file}")
        if not build_succeeded:
            self._log(package_name, "Max attempts reached without success.")

    async def _llm_tools_loop(
        self,
        package_name: str,
        package_path: str,
        messages: List[Dict],
        tools: List[Dict],
    ) -> Tuple[str, bool]:
        """Process LLM tool calls sequentially; enforce validation fallback at the end."""

        def _txt(x):
            # Compatible with MCP content which may be list[str|{text}]
            if isinstance(x, str):
                return x
            if isinstance(x, list):
                parts = []
                for it in x:
                    if isinstance(it, dict) and "text" in it:
                        parts.append(str(it["text"]))
                    else:
                        parts.append(str(it))
                return "\n".join(parts)
            return str(x)

        # The model call
        try:
            resp = self.client.chat.completions.create(
                model="gpt-5-mini", messages=messages, tools=tools
            )
        except Exception as e:
            self._log(package_name, f"Model call failed: {e}")
            return f"Model call failed: {e}", False

        choice = resp.choices[0]
        rounds = 0
        latest_text = choice.message.content or ""

        did_upload = False
        did_check = False

        while rounds < self.max_tool_rounds and choice.finish_reason == "tool_calls":
            rounds += 1
            self._log(package_name, f"== Tool round {rounds}: ")

            for tc in choice.message.tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments or "{}")
                self._log(package_name, f"Tool call: {tool_name}({tool_args})")

                if tool_name in ["log_anomaly_detection_tool", "dependency_constrain_tool"]:
                    tool_args["input_dir"] = package_path

                args_key = make_args_key(tool_name, tool_args)
                # Avoid repeated calls
                repeat_check = await self.session.call_tool(
                    "check_repeat_tool_call",
                    {
                        "tool_name": tool_name,
                        "args_key": args_key,
                        "max_repeat": 5,
                        "package_name": package_name,
                    },
                )
                repeat_allowed = json.loads(repeat_check.content[0].text).get(
                    "allowed", True
                )

                if not repeat_allowed:
                    tool_ret = json.loads(repeat_check.content[0].text).get(
                        "message", "repeated call blocked"
                    )
                else:
                    # Use cache mechanism to save call path
                    cache = await self.session.call_tool(
                        "check_tool_cache",
                        {
                            "call_key": args_key,
                            "tool_name": tool_name,
                            "package_name": package_name,
                        },
                    )
                    cache_data = json.loads(cache.content[0].text)
                    if cache_data.get("hit"):
                        tool_ret = cache_data["result"]
                    else:
                        try:
                            res = await asyncio.wait_for(
                                self.session.call_tool(tool_name, tool_args),
                                timeout=600,
                            )
                            tool_ret = _txt(res.content)
                            self._log(
                                package_name, f"Tool return text: {tool_ret[:1000]}"
                            )

                            if tool_name in [
                                "log_anomaly_detection_tool",
                                "get_structure_of_files",
                                "modify_file_tool",
                            ]:
                                if "error" not in tool_ret.lower():
                                    await self.session.call_tool(
                                        "cache_tool_result",
                                        {
                                            "call_key": args_key,
                                            "result": tool_ret,
                                            "package_name": package_name,
                                        },
                                    )
                        except asyncio.TimeoutError:
                            tool_ret = f"Error: Tool {tool_name} timed out"
                        except Exception as e:
                            tool_ret = f"Error: Tool {tool_name} failed: {e}"

                    await self.session.call_tool(
                        "record_tool_call_history",
                        {"call_key": args_key, "package_name": package_name},
                    )

                # Mark whether the build has been uploaded/verified
                if tool_name == "upload_file_to_obs_tool":
                    did_upload = True
                if tool_name == "check_build_result":
                    did_check = True

                # Feed back the tool result
                messages.append(
                    {
                        "role": "assistant",
                        "content": choice.message.content,
                        "tool_calls": [
                            t.model_dump() for t in choice.message.tool_calls
                        ],
                    }
                )
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": tool_ret}
                )

                # If it's a build verification, parse the result immediately
                if tool_name == "check_build_result":
                    parsed = await self.session.call_tool(
                        "parse_build_result_tool",
                        {"result_content": tool_ret, "package_name": package_name},
                    )
                    if json.loads(parsed.content[0].text).get("success"):
                        return latest_text, True

            # Continue to the next round of models
            try:
                resp = self.client.chat.completions.create(
                    model="gpt-5-mini", messages=messages, tools=tools
                )
                choice = resp.choices[0]
                latest_text = choice.message.content or latest_text
            except Exception as e:
                self._log(package_name, f"Model continuation failed: {e}")
                break

        # ---------- Fallback: If the model does not explicitly perform upload/verification build, it is enforced by the client ----------
        if self.validator_backend == "obs" and not did_upload:
            try:
                up_res = await self.session.call_tool(
                    "upload_file_to_obs_tool", {"package_path": package_path}
                )
                up_txt = _txt(up_res.content)
                self._log(
                    package_name,
                    f"[fallback] upload_file_to_obs_tool => {up_txt[:300]}",
                )
                # Feed the results back (for subsequent prompts/records)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": "fallback_upload",
                        "content": up_txt,
                    }
                )
            except Exception as e:
                self._log(package_name, f"[fallback] upload failed: {e}")

        if not did_check:
            try:
                chk_res = await self.session.call_tool(
                    "check_build_result",
                    {"input_dir": package_path, "package_name": package_name},
                )
                chk_txt = _txt(chk_res.content)
                self._log(
                    package_name, f"[fallback] check_build_result => {chk_txt[:300]}"
                )

                parsed = await self.session.call_tool(
                    "parse_build_result_tool",
                    {"result_content": chk_txt, "package_name": package_name},
                )
                if json.loads(parsed.content[0].text).get("success"):
                    return latest_text, True
            except Exception as e:
                self._log(package_name, f"[fallback] check failed: {e}")

        # Default failure, return to the upper layer to continue the next attempt
        return latest_text, False

    async def cleanup(self):
        try:
            await self.exit_stack.aclose()
        except Exception as e:
            self._log("global", f"Cleanup error: {e}")
        self.is_session_active = False
        self.session = None
        self._log("global", "Cleanup completed.")


async def main():
    cli = AutoRepairClient()
    try:
        await cli.process_all_packages()
    finally:
        await cli.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
