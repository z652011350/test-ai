"""
claude_runner.py - Component 扫描 Claude CLI 执行模块

封装 subprocess 调用 Claude CLI，支持 audit-error-codes-new skill 调用、重试和指数退避。
"""

import subprocess
import time
from typing import Dict, Tuple, Optional

# Claude CLI 命令名
CLAUDE_CLI: str = "claude"

# 允许的工具列表
ALLOWED_TOOLS: str = "Bash,Read,Edit,Find,Wc,Write,Search,Python,Grep,Glob,Agent"

# 重试配置
DEFAULT_MAX_RETRIES: int = 3
BASE_RETRY_DELAY: float = 10.0


def build_skill_prompt(component_path: str,
                       kit_name: str = "",
                       api_doc_path: str = "",
                       api_error_doc_path: str = "",
                       analyze_depth: str = "thorough",
                       out_path: str = "") -> str:
    """构建 audit-error-codes-new skill 调用 prompt。"""
    lines = ["/audit-error-codes-new"]

    lines.append(f"component_path={component_path}")

    if kit_name:
        lines.append(f"kit_name={kit_name}")
    if api_doc_path:
        lines.append(f"api_doc_path={api_doc_path}")
    if api_error_doc_path:
        lines.append(f"api_error_doc_path={api_error_doc_path}")
    if analyze_depth and analyze_depth != "thorough":
        lines.append(f"analyze_depth={analyze_depth}")
    if out_path:
        lines.append(f"out_path={out_path}")

    return "\n".join(lines)


def run_claude_command(prompt: str,
                       max_retries: int = DEFAULT_MAX_RETRIES,
                       label: str = "") -> Tuple[bool, str]:
    """
    执行单次 Claude CLI 命令，支持失败重试和指数退避。

    Args:
        prompt: 完整 prompt 文本
        max_retries: 最大重试次数
        label: 日志标签（如部件名）

    Returns:
        (success, output)
    """
    cmd = [
        CLAUDE_CLI,
        "-p",
        prompt,
        "--allowedTools",
        ALLOWED_TOOLS,
    ]

    prefix = f"[{label}] " if label else ""

    last_output = ""
    for attempt in range(max_retries + 1):
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=0,
            )

            full_output: list = []
            pid = process.pid
            if attempt == 0:
                print(f"{prefix}启动 claude 进程 PID: {pid}")
            else:
                print(f"{prefix}第 {attempt}/{max_retries} 次重试，PID: {pid}")

            # 实时读取输出
            while True:
                line = process.stdout.readline()
                if line:
                    full_output.append(line)
                if process.poll() is not None and not line:
                    break

            stderr = process.stderr.read().strip() if process.stderr else ""
            if stderr:
                print(f"{prefix}[stderr] {stderr[:200]}")

            output = "".join(full_output)
            if process.returncode != 0:
                print(f"{prefix}claude 进程退出码: {process.returncode}")
                last_output = output
                if attempt < max_retries:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    print(f"{prefix}{delay:.0f}s 后重试...")
                    time.sleep(delay)
                    continue
                return False, output

            return True, output

        except FileNotFoundError:
            msg = "未找到 claude CLI，请确认已安装并添加到 PATH"
            print(f"{prefix}[错误] {msg}")
            return False, msg
        except Exception as e:
            msg = f"调用 claude 失败: {e}"
            print(f"{prefix}[错误] {msg}")
            last_output = msg
            if attempt < max_retries:
                delay = BASE_RETRY_DELAY * (2 ** attempt)
                print(f"{prefix}{delay:.0f}s 后重试...")
                time.sleep(delay)
                continue
            return False, msg

    return False, last_output


def run_component_scan(row: Dict[str, str],
                       out_base: str,
                       repo_base: str,
                       max_retries: int = DEFAULT_MAX_RETRIES) -> Tuple[bool, str, float]:
    """
    扫描单个部件。

    Args:
        row: CSV 行数据字典
        out_base: 输出根目录
        repo_base: DataBases 根目录
        max_retries: 最大重试次数

    Returns:
        (success, output, elapsed_seconds)
    """
    component_name = row["component_name"]
    component_path = row.get("component_path") or f"{repo_base}/{component_name}"
    kit_name = row.get("kit_name", "")
    api_doc_path = row.get("api_doc_path", "")
    api_error_doc_path = row.get("api_error_doc_path", "")
    analyze_depth = row.get("analyze_depth", "thorough") or "thorough"
    out_path = f"{out_base}/{component_name}"

    prompt = build_skill_prompt(
        component_path=component_path,
        kit_name=kit_name,
        api_doc_path=api_doc_path,
        api_error_doc_path=api_error_doc_path,
        analyze_depth=analyze_depth,
        out_path=out_path,
    )

    print(f"\n{'=' * 60}")
    print(f"[{component_name}] 开始扫描")
    print(f"  component_path: {component_path}")
    print(f"  out_path: {out_path}")
    print(f"  depth: {analyze_depth}")

    start = time.time()
    success, output = run_claude_command(
        prompt, max_retries=max_retries, label=component_name
    )
    elapsed = time.time() - start

    if success:
        print(f"[{component_name}] 扫描完成，耗时 {elapsed:.1f}s")
    else:
        print(f"[{component_name}] 扫描失败，耗时 {elapsed:.1f}s")

    return success, output, elapsed
