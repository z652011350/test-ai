"""
claude_runner.py - Claude CLI 执行模块

封装 subprocess 调用 Claude CLI，支持单次执行和批量扫描。
"""

import subprocess
import time
from pathlib import Path
from typing import List, Tuple, Callable

# Claude CLI 命令名（确保在 PATH 中）
CLAUDE_CLI: str = "claude"

# 允许的工具列表
ALLOWED_TOOLS: str = "Bash,Read,Edit,Find,Wc,Write,Search,Python,Grep,Glob,Agent"


def run_claude_command(prompt: str) -> Tuple[bool, str]:
    """
    执行单次 Claude CLI 命令。

    Args:
        prompt: 通过 -p 传递的完整 prompt

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
        print(f"[claude_runner] 启动 claude 进程 PID: {pid}")

        # 实时读取输出
        while True:
            line = process.stdout.readline()
            if line:
                print(line, end="")
                full_output.append(line)
            if process.poll() is not None and not line:
                break

        stderr = process.stderr.read().strip() if process.stderr else ""
        if stderr:
            print(f"  [stderr] {stderr}")

        output = "".join(full_output)
        if process.returncode != 0:
            print(f"  [错误] claude 进程退出码: {process.returncode}")
            return False, output

        return True, output

    except FileNotFoundError:
        msg = "未找到 claude CLI，请确认已安装并添加到 PATH"
        print(f"  [错误] {msg}")
        return False, msg
    except Exception as e:
        msg = f"调用 claude 失败: {e}"
        print(f"  [错误] {msg}")
        return False, msg


def run_batch_scan(
    batch_paths: List[Path],
    output_dir: Path,
    repo_base: Path,
    build_prompt_fn: Callable[[Path, Path, Path], str],
    result_filename: str = "api_scan_findings.jsonl",
) -> None:
    """
    遍历每个 batch 文件，构建 prompt 并调用 Claude CLI 执行审计。
    若某个 batch 的结果文件已存在，则跳过该批次。

    Args:
        batch_paths: batch JSONL 输入文件路径列表
        output_dir: Kit 输出根目录
        repo_base: DataBases 目录路径
        build_prompt_fn: 构建 prompt 的回调函数 (batch_path, batch_out_dir, repo_base) -> str
        result_filename: 结果文件名，用于判断是否已存在
    """
    batch_result_dir = output_dir / "batch_result"
    total = len(batch_paths)
    skipped = 0

    for idx, batch_path in enumerate(batch_paths):
        batch_out_dir = batch_result_dir / f"batch_{idx}"

        # 检查该批次结果是否已存在
        result_file = batch_out_dir / "api_scan" / result_filename
        if result_file.exists():
            skipped += 1
            print(f"\n[claude_runner] 跳过 batch {idx + 1}/{total} (结果已存在: {result_file})")
            continue

        batch_out_dir.mkdir(parents=True, exist_ok=True)
        prompt = build_prompt_fn(batch_path, batch_out_dir, repo_base)

        print(f"\n{'=' * 50}")
        print(f"[claude_runner] 处理 batch {idx + 1}/{total}")
        print(f"  输入: {batch_path}")
        print(f"  输出: {batch_out_dir}")

        start = time.time()
        success, _ = run_claude_command(prompt)
        elapsed = time.time() - start

        if success:
            print(f"  [完成] 耗时 {elapsed:.1f}s")
        else:
            print(f"  [失败] 耗时 {elapsed:.1f}s，继续处理下一个 batch")

    print(f"\n[claude_runner] 全部 batch 处理完毕: {total} 个 (跳过 {skipped} 个已有结果)")
