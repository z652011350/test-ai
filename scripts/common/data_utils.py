"""
data_utils.py - JSONL 数据处理共享模块

提供 JSONL 文件读取、分割、匹配和 XLSX 转换功能。
从 kit-scan/batch_pipeline.py 和 kit-scan-test/data_prepare.py 提取的公共逻辑。
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple


def load_and_split_impl_api(
    impl_api_path: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    读取 impl_api.jsonl，分离 impl_api_name 为空和不为空的数据。

    Returns:
        (empty_impl_list, non_empty_impl_list)
    """
    empty_list: List[Dict[str, Any]] = []
    non_empty_list: List[Dict[str, Any]] = []

    with open(impl_api_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("impl_api_name", "") == "":
                empty_list.append(record)
            else:
                non_empty_list.append(record)

    print(
        f"[data_utils] 读取 impl_api.jsonl 完成: "
        f"impl_api_name 为空 {len(empty_list)} 条, "
        f"不为空 {len(non_empty_list)} 条"
    )
    return empty_list, non_empty_list


def load_matching_api_data(
    api_path: Path, empty_impl_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    读取 api.jsonl，匹配 impl_api_name 为空的数据对应的条目。
    使用 api_declaration + module_name + declaration_file 三字段联合匹配。
    """
    match_keys = set()
    for record in empty_impl_list:
        key = (
            record.get("api_declaration", ""),
            record.get("module_name", ""),
            record.get("declaration_file", ""),
        )
        match_keys.add(key)

    matched: List[Dict[str, Any]] = []
    with open(api_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            key = (
                record.get("api_declaration", ""),
                record.get("module_name", ""),
                record.get("declaration_file", ""),
            )
            if key in match_keys:
                matched.append(record)

    print(
        f"[data_utils] 从 api.jsonl 匹配到 {len(matched)} 条数据 "
        f"(待匹配 {len(empty_impl_list)} 条)"
    )
    return matched


def jsonl_to_xlsx(jsonl_path: Path, xlsx_path: Path) -> int:
    """
    将 JSONL 文件转为 XLSX 表格。
    逐行读取 JSONL，以第一行的所有 key 作为表头，每行数据写入一行。
    """
    from openpyxl import Workbook

    records: List[Dict[str, Any]] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    if not records:
        print(f"[data_utils] JSONL 文件为空，跳过 XLSX 生成: {jsonl_path}")
        return 0

    # 收集所有 key（保持首次出现的顺序）
    seen: set = set()
    headers: List[str] = []
    for rec in records:
        for k in rec:
            if k not in seen:
                seen.add(k)
                headers.append(k)

    wb = Workbook()
    ws = wb.active
    ws.title = "audit_results"
    ws.append(headers)

    for rec in records:
        ws.append([rec.get(h, "") for h in headers])

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(xlsx_path))
    print(f"[data_utils] XLSX 已生成: {xlsx_path} ({len(records)} 行)")
    return len(records)
