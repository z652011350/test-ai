"""
claude_runner.py - Component 扫描 Agent CLI 执行模块

导入共享 runner 模块，保留 component-scan 独有的 build_skill_prompt 和 run_component_scan。
"""

import sys
import time
from pathlib import Path
from typing import Dict, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.runner import (
    run_agent,
    DEFAULT_MAX_RETRIES,
    ALLOWED_TOOLS,
)


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
    执行 Agent CLI 命令，使用指数退避重试。
    保留原有接口签名（含 label 参数），内部委托给共享 runner。
    component-scan 使用 realtime_print=False 以避免并行扫描时输出交错，
    stderr 截断到 200 字符。
    """
    return run_agent(
        prompt=prompt,
        backend="claude",
        max_retries=max_retries,
        retry_strategy="exponential",
        label=label,
        realtime_print=False,
        stderr_limit=200,
    )


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
