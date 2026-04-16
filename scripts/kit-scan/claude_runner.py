"""
claude_runner.py - Claude CLI 执行模块（kit-scan 版）

导入共享 runner 模块，保留 kit-scan 独有的 run_batch_scan 逻辑。
"""

import time
from functools import partial
from pathlib import Path
from typing import Callable, List, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.runner import (
    run_agent,
    DEFAULT_MAX_RETRIES,
    ALLOWED_TOOLS,
)


def run_claude_command(
    prompt: str, max_retries: int = DEFAULT_MAX_RETRIES
) -> Tuple[bool, str]:
    """
    执行 Claude CLI 命令，使用指数退避重试。
    保留原有接口签名，内部委托给共享 runner。
    """
    return run_agent(
        prompt=prompt,
        backend="claude",
        max_retries=max_retries,
        retry_strategy="exponential",
        realtime_print=True,
        stderr_limit=0,
    )


def run_batch_scan(
    batch_paths: List[Path],
    output_dir: Path,
    repo_base: Path,
    build_prompt_fn: Callable[[Path, Path, Path], str],
    result_filename: str = "api_scan_findings.jsonl",
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> None:
    """
    遍历每个 batch 文件，构建 prompt 并调用 Claude CLI 执行审计。
    若某个 batch 的结果文件已存在，则跳过该批次。
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
        print(f"prompt :{prompt}")

        print(f"\n{'=' * 50}")
        print(f"[claude_runner] 处理 batch {idx + 1}/{total}")
        print(f"  输入: {batch_path}")
        print(f"  输出: {batch_out_dir}")

        start = time.time()
        success, _ = run_claude_command(prompt, max_retries)
        elapsed = time.time() - start

        if success:
            print(f"  [完成] 耗时 {elapsed:.1f}s")
        else:
            print(f"  [失败] 耗时 {elapsed:.1f}s，继续处理下一个 batch")

    print(f"\n[claude_runner] 全部 batch 处理完毕: {total} 个 (跳过 {skipped} 个已有结果)")
