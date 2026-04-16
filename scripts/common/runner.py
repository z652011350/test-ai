"""
runner.py - 统一 Agent CLI 执行模块

封装 subprocess 调用 Claude CLI 和 OpenCode CLI，支持：
- 两种后端：claude (claude -p) 和 opencode (opencode run)
- 两种重试策略：指数退避 和 追加提示重试
- 统一的实时 stdout/stderr 读取
- 工厂函数按配置返回对应 runner
"""

import subprocess
import time
from typing import List, Tuple

# ============================================================
# 常量
# ============================================================

CLAUDE_CLI: str = "claude"
OPENCODE_CLI: str = "opencode"

ALLOWED_TOOLS: str = "Bash,Read,Edit,Find,Wc,Write,Search,Python,Grep,Glob,Agent"

DEFAULT_MAX_RETRIES: int = 3
BASE_RETRY_DELAY: float = 10.0
RETRY_PROMPT_SUFFIX: str = "\n上次未执行完毕，当前是重试，请你阅读已有相关数据，再继续执行"


# ============================================================
# 核心执行函数
# ============================================================


def _run_once(
    cmd: List[str],
    label: str = "",
    realtime_print: bool = True,
    stderr_limit: int = 0,
) -> Tuple[bool, str]:
    """
    执行单次 CLI 命令（无重试）。

    Args:
        cmd: 完整命令列表
        label: 日志标签前缀
        realtime_print: 是否实时打印 stdout 到终端
        stderr_limit: stderr 截断长度（0 = 不截断，完整输出）

    Returns:
        (success, output)
    """
    prefix = f"[{label}] " if label else ""

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=0,
        )

        full_output: List[str] = []
        pid = process.pid
        cli_name = cmd[0]
        print(f"{prefix}启动 {cli_name} 进程 PID: {pid}")

        # 实时读取输出
        while True:
            line = process.stdout.readline()
            if line:
                if realtime_print:
                    print(line, end="")
                full_output.append(line)
            if process.poll() is not None and not line:
                break

        stderr = process.stderr.read().strip() if process.stderr else ""
        if stderr:
            display_stderr = stderr[:stderr_limit] if stderr_limit > 0 else stderr
            print(f"{prefix}[stderr] {display_stderr}")

        output = "".join(full_output)
        if process.returncode != 0:
            print(f"{prefix}{cli_name} 进程退出码: {process.returncode}")
            return False, output

        return True, output

    except FileNotFoundError:
        msg = f"未找到 {cmd[0]} CLI，请确认已安装并添加到 PATH"
        print(f"{prefix}[错误] {msg}")
        return False, msg
    except Exception as e:
        msg = f"调用 {cmd[0]} 失败: {e}"
        print(f"{prefix}[错误] {msg}")
        return False, msg


# ============================================================
# 重试策略
# ============================================================


def run_with_exponential_backoff(
    cmd: List[str],
    max_retries: int = DEFAULT_MAX_RETRIES,
    label: str = "",
    realtime_print: bool = True,
    stderr_limit: int = 0,
) -> Tuple[bool, str]:
    """
    指数退避重试策略。每次重试前等待 delay = BASE_RETRY_DELAY * 2^attempt。
    适用于 claude runner (component-scan 和 kit-scan 风格)。
    """
    prefix = f"[{label}] " if label else ""
    last_output = ""

    for attempt in range(max_retries + 1):
        if attempt > 0:
            delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))
            print(f"{prefix}第 {attempt}/{max_retries} 次重试，{delay:.0f}s 后重试...")
            time.sleep(delay)

        success, output = _run_once(cmd, label, realtime_print, stderr_limit)
        last_output = output

        if success:
            if attempt > 0:
                print(f"{prefix}第 {attempt} 次尝试成功")
            return True, output

    print(f"{prefix}已达最大重试次数 ({max_retries})，放弃执行")
    return False, last_output


def run_with_append_prompt(
    cmd_builder,
    base_prompt: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    label: str = "",
    realtime_print: bool = True,
    stderr_limit: int = 0,
) -> Tuple[bool, str]:
    """
    追加提示重试策略。每次重试在 prompt 末尾追加 RETRY_PROMPT_SUFFIX。
    适用于 kit-scan-test 风格。

    Args:
        cmd_builder: 函数，接受 prompt 字符串，返回完整命令列表
        base_prompt: 基础 prompt
        max_retries: 最大重试次数
        label: 日志标签
        realtime_print: 是否实时打印
        stderr_limit: stderr 截断长度
    """
    prefix = f"[{label}] " if label else ""
    last_output = ""

    for attempt in range(1, max_retries + 1):
        current_prompt = base_prompt if attempt == 1 else base_prompt + RETRY_PROMPT_SUFFIX

        if attempt > 1:
            print(f"{prefix}第 {attempt}/{max_retries} 次重试")

        cmd = cmd_builder(current_prompt)
        success, output = _run_once(cmd, label, realtime_print, stderr_limit)
        last_output = output

        if success:
            if attempt > 1:
                print(f"{prefix}第 {attempt} 次尝试成功")
            return True, output

        print(f"{prefix}第 {attempt}/{max_retries} 次执行失败")

    print(f"{prefix}已达最大重试次数 ({max_retries})，放弃执行")
    return False, last_output


# ============================================================
# 命令构建器
# ============================================================


def build_claude_cmd(prompt: str, allowed_tools: str = ALLOWED_TOOLS) -> List[str]:
    """构建 Claude CLI 命令。"""
    return [CLAUDE_CLI, "-p", prompt, "--allowedTools", allowed_tools]


def build_opencode_cmd(prompt: str) -> List[str]:
    """构建 OpenCode CLI 命令。"""
    return [OPENCODE_CLI, "run", prompt]


# ============================================================
# 工厂函数
# ============================================================


def run_agent(
    prompt: str,
    backend: str = "claude",
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_strategy: str = "exponential",
    label: str = "",
    realtime_print: bool = True,
    stderr_limit: int = 0,
    allowed_tools: str = ALLOWED_TOOLS,
) -> Tuple[bool, str]:
    """
    统一 Agent 执行入口。根据后端类型和重试策略选择执行方式。

    Args:
        prompt: 完整 prompt 文本
        backend: 后端类型 "claude" 或 "opencode"
        max_retries: 最大重试次数
        retry_strategy: 重试策略 "exponential" 或 "append_prompt"
        label: 日志标签前缀
        realtime_print: 是否实时打印 stdout 到终端
        stderr_limit: stderr 截断长度（0 = 不截断）
        allowed_tools: Claude 后端的允许工具列表

    Returns:
        (success, output)
    """
    if backend == "opencode":
        if retry_strategy == "append_prompt":
            return run_with_append_prompt(
                cmd_builder=build_opencode_cmd,
                base_prompt=prompt,
                max_retries=max_retries,
                label=label,
                realtime_print=realtime_print,
                stderr_limit=stderr_limit,
            )
        else:
            cmd = build_opencode_cmd(prompt)
            return run_with_exponential_backoff(
                cmd, max_retries, label, realtime_print, stderr_limit
            )
    else:
        # 默认 claude 后端
        if retry_strategy == "append_prompt":
            return run_with_append_prompt(
                cmd_builder=lambda p: build_claude_cmd(p, allowed_tools),
                base_prompt=prompt,
                max_retries=max_retries,
                label=label,
                realtime_print=realtime_print,
                stderr_limit=stderr_limit,
            )
        else:
            cmd = build_claude_cmd(prompt, allowed_tools)
            return run_with_exponential_backoff(
                cmd, max_retries, label, realtime_print, stderr_limit
            )
