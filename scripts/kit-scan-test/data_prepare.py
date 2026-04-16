"""
data_prepare.py - API 数据准备模块（kit-scan-test 版）

负责 JSONL 文件合并。不调用 CLI。
数据加载和 XLSX 转换已提取到 common/data_utils.py。
"""

import json
from pathlib import Path
from typing import List, Dict, Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.data_utils import load_and_split_impl_api, load_matching_api_data, jsonl_to_xlsx


def prepare_merged_input(
    non_empty_impl: List[Dict[str, Any]],
    matched_api: List[Dict[str, Any]],
    output_dir: Path,
) -> Path:
    """
    合并 Format 1（有完整 impl 路径）和 Format 2（有 js_doc）数据，
    写入单个 JSONL 文件供 api-level-scan-test 技能使用。

    Returns:
        合并后的 JSONL 文件路径
    """
    merged_path = output_dir / "merged_input.jsonl"
    all_data = non_empty_impl + matched_api

    with open(merged_path, "w", encoding="utf-8") as f:
        for record in all_data:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        f"[data_prepare] 合并完成: 共 {len(all_data)} 条 API -> {merged_path}\n"
        f"  Format 1 (有 impl 路径): {len(non_empty_impl)} 条\n"
        f"  Format 2 (有 js_doc):    {len(matched_api)} 条"
    )
    return merged_path
