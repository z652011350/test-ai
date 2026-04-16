"""
batch_pipeline.py - 批量 API 数据处理模块

负责 JSONL 文件读写、数据分批、prompt 构建和结果合并。
不调用 Claude CLI，仅处理数据流。
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.data_utils import load_and_split_impl_api, load_matching_api_data, jsonl_to_xlsx

# 每个 batch 审计完成后，结果文件名
RESULT_FILENAME: str = "api_scan_findings.jsonl"


def prepare_batches(
    non_empty_impl: List[Dict[str, Any]],
    matched_api: List[Dict[str, Any]],
    batch_size: int,
    output_dir: Path,
) -> List[Path]:
    """
    合并数据、按 batch_size 分组，并将每批写入独立的 JSONL 文件。

    输出到 {output_dir}/batch_result/input/batch_0.jsonl, batch_1.jsonl, ...

    Returns:
        所有 batch 文件路径列表
    """
    all_data = non_empty_impl + matched_api

    input_dir = output_dir / "batch_result" / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    batch_paths: List[Path] = []
    for i in range(0, len(all_data), batch_size):
        batch = all_data[i : i + batch_size]
        batch_path = input_dir / f"batch_{i // batch_size}.jsonl"
        with open(batch_path, "w", encoding="utf-8") as f:
            for record in batch:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        batch_paths.append(batch_path)
        print(
            f"[batch_pipeline] 写入 batch {i // batch_size}: "
            f"{len(batch)} 条 API -> {batch_path}"
        )

    print(
        f"[batch_pipeline] 共 {len(all_data)} 条数据, "
        f"分为 {len(batch_paths)} 个 batch (batch_size={batch_size})"
    )
    return batch_paths


def build_scan_prompt(
    batch_input_path: Path,
    batch_out_dir: Path,
    repo_base: Path,
    doc_path: str = "",
    kit_name: str = "",
    js_sdk_path: str = "",
) -> str:
    """
    为单个 batch 构建 /api-level-scan 的 prompt。
    使用文件路径引用而非嵌入 JSONL 数据。
    """

    prompt = (
        f"/api-level-scan\n"
        f"api_input=\n{batch_input_path}\n"
        f"repo_base={repo_base}\n"
        f"out_path={batch_out_dir}\n"

    )
    if js_sdk_path:
        prompt += f"js_sdk_path={js_sdk_path}\n"
    if batch_out_dir.parent/'api_extraction_report.md' in batch_out_dir.parent.iterdir():
        prompt += "api_extraction_report_path={}\n".format(batch_out_dir.parent/'api_extraction_report.md')
        print(f"  [提示] 已存在 api_extraction_report.md，已将相关知识路径注入")
    if doc_path and kit_name:
        prompt += f"api_error_code_doc_path={doc_path}\n"
        prompt += f"kit_name={kit_name}\n"
    return prompt


def collect_batch_result_dirs(output_dir: Path) -> List[Path]:
    """
    扫描 {output_dir}/batch_result/ 下所有匹配 batch_{i} 模式的目录，
    按编号排序返回。
    """
    batch_result_dir = output_dir / "batch_result"
    if not batch_result_dir.exists():
        return []

    dirs: List[Path] = []
    for p in sorted(batch_result_dir.iterdir()):
        if p.is_dir() and p.name.startswith("batch_") and p.name != "input":
            dirs.append(p)
    return dirs


def merge_batch_results(output_dir: Path, output_path: Path) -> int:
    """
    自动扫描 batch_result 下所有 batch 目录，将每个目录下的
    api_scan/api_scan_findings.jsonl 合并为一个文件。
    """
    batch_dirs = collect_batch_result_dirs(output_dir)
    if not batch_dirs:
        print("[batch_pipeline] 未找到任何 batch 结果目录")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_lines = 0
    with open(output_path, "w", encoding="utf-8") as out_f:
        for dir_path in batch_dirs:
            result_file = dir_path / "api_scan" / RESULT_FILENAME
            if not result_file.exists():
                print(f"  [跳过] 结果文件不存在: {result_file}")
                continue

            with open(result_file, "r", encoding="utf-8") as in_f:
                for line in in_f:
                    line = line.strip()
                    if not line:
                        continue
                    out_f.write(line + "\n")
                    total_lines += 1

    print(f"[batch_pipeline] 合并完成: {total_lines} 条记录 -> {output_path}")
    return total_lines


# ============================================================
# 汇总报表生成
# ============================================================

def _normalize_decl(decl: str) -> str:
    """标准化 API 声明：collapse 空格 + strip。"""
    return ' '.join(decl.split())


def compute_kit_stats(output_dir: Path, kit_name: str) -> Dict[str, Any]:
    """计算单个 Kit 的所有统计指标。"""
    stats: Dict[str, Any] = {"kit_name": kit_name}

    # --- api.jsonl ---
    api_path = output_dir / "api.jsonl"
    api_decls: set = set()
    modules: set = set()

    if api_path.exists():
        with open(api_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                decl = record.get("api_declaration", "")
                if decl:
                    api_decls.add(_normalize_decl(decl))
                mod = record.get("module_name", "")
                if mod:
                    modules.add(mod)

    total_api_count = len(api_decls)
    stats["total_api_count"] = total_api_count
    stats["module_count"] = len(modules)

    # --- impl_api.jsonl ---
    impl_path = output_dir / "impl_api.jsonl"
    impl_repos: set = set()
    impl_seen_decls: set = set()
    napi_count = 0
    impl_name_count = 0
    fwk_decl_count = 0
    impl_file_count = 0

    if impl_path.exists():
        with open(impl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                repo = record.get("impl_repo_path", "")
                if repo:
                    impl_repos.add(repo)

                decl = _normalize_decl(record.get("api_declaration", ""))
                if not decl or decl in impl_seen_decls:
                    continue
                impl_seen_decls.add(decl)

                if record.get("NAPI_map_file", ""):
                    napi_count += 1
                if record.get("impl_api_name", ""):
                    impl_name_count += 1
                if record.get("Framework_decl_file", ""):
                    fwk_decl_count += 1
                if record.get("impl_file_path", ""):
                    impl_file_count += 1

    stats["repo_count"] = len(impl_repos)

    def _coverage(numerator: int, denominator: int) -> str:
        if denominator == 0:
            return "0.00%"
        return f"{numerator / denominator * 100:.2f}%"

    stats["napi_coverage"] = _coverage(napi_count, total_api_count)
    stats["impl_name_coverage"] = _coverage(impl_name_count, total_api_count)
    stats["fwk_decl_coverage"] = _coverage(fwk_decl_count, total_api_count)
    stats["impl_file_coverage"] = _coverage(impl_file_count, total_api_count)

    # --- 参与审计的 API 数 ---
    batch_input_dir = output_dir / "batch_result" / "input"
    audited_decls: set = set()
    if batch_input_dir.exists():
        for batch_file in sorted(batch_input_dir.glob("batch_*.jsonl")):
            with open(batch_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    decl = record.get("api_declaration", "")
                    if decl:
                        audited_decls.add(_normalize_decl(decl))
        stats["audited_api_count"] = len(audited_decls)
    else:
        stats["audited_api_count"] = None

    # --- 存在问题的 API 数 ---
    findings_path = output_dir / "batch_result" / "merged_api_scan_findings.jsonl"
    problem_decls: set = set()
    if findings_path.exists():
        with open(findings_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                decl = record.get("api声明", "")
                if decl:
                    problem_decls.add(_normalize_decl(decl))
        stats["problem_api_count"] = len(problem_decls)
    else:
        stats["problem_api_count"] = None

    return stats


# 报表列定义（固定顺序）
_SUMMARY_COLUMNS = [
    ("kit_name", "Kit 名称"),
    ("total_api_count", "总 API 数"),
    ("module_count", "模块数"),
    ("repo_count", "代码仓数"),
    ("napi_coverage", "NAPI 覆盖率"),
    ("impl_name_coverage", "实现函数名覆盖率"),
    ("fwk_decl_coverage", "Framework 声明覆盖率"),
    ("impl_file_coverage", "业务实现覆盖率"),
    ("audited_api_count", "参与审计的 API 数"),
    ("problem_api_count", "存在问题的 API 数"),
]


def write_summary_markdown(
    stats_list: List[Dict[str, Any]],
    output_path: Path,
    title: str = "审计汇总报表",
) -> None:
    """将统计字典列表格式化为 Markdown 表格并写入文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"# {title}", ""]

    header = "| " + " | ".join(col_label for _, col_label in _SUMMARY_COLUMNS) + " |"
    separator = "| " + " | ".join("---" for _ in _SUMMARY_COLUMNS) + " |"
    lines.append(header)
    lines.append(separator)

    for stats in stats_list:
        row_values = []
        for col_key, _ in _SUMMARY_COLUMNS:
            val = stats.get(col_key)
            row_values.append(str(val) if val is not None else "N/A")
        lines.append("| " + " | ".join(row_values) + " |")

    lines.append("")
    content = "\n".join(lines)
    output_path.write_text(content, encoding="utf-8")
    print(f"[batch_pipeline] Markdown 报表已生成: {output_path}")


def write_summary_xlsx(
    stats_list: List[Dict[str, Any]],
    output_path: Path,
    title: str = "审计汇总报表",
) -> None:
    """使用 openpyxl 生成固定列顺序的 XLSX 汇总表格。"""
    from openpyxl import Workbook

    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "汇总报表"

    headers = [col_label for _, col_label in _SUMMARY_COLUMNS]
    ws.append(headers)

    for stats in stats_list:
        row = []
        for col_key, _ in _SUMMARY_COLUMNS:
            val = stats.get(col_key)
            row.append(val if val is not None else "N/A")
        ws.append(row)

    wb.save(str(output_path))
    print(f"[batch_pipeline] XLSX 报表已生成: {output_path} ({len(stats_list)} 行)")
