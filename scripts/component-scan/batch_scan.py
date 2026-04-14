"""
batch_scan.py - 部件批量扫描主入口

读取 CSV 输入文件，并行调度 Claude CLI 对每个部件执行 audit-error-codes-new skill 扫描。
支持断点续扫、并行控制、结果汇总。
"""

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from claude_runner import run_component_scan
from result_collector import collect_and_summarize

# 默认路径
DEFAULT_REPO_BASE = "/Users/spongbob/for_guance/api_dfx/DataBases"
DEFAULT_OUT_BASE = "./scan_results"


def read_csv(csv_path: Path) -> List[Dict[str, str]]:
    """读取 CSV 文件，返回行列表。"""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def filter_rows(rows: List[Dict[str, str]],
                components_filter: List[str] = None) -> List[Dict[str, str]]:
    """过滤行：去掉 enabled=no 和不在指定列表中的部件。"""
    filtered = []
    for row in rows:
        # 检查 enabled 字段
        enabled = row.get("enabled", "yes").strip().lower()
        if enabled in ("no", "false", "0"):
            continue

        # 检查部件过滤列表
        if components_filter:
            component_name = row.get("component_name", "").strip()
            if component_name not in components_filter:
                continue

        filtered.append(row)
    return filtered


def check_completed(row: Dict[str, str], out_base: str) -> bool:
    """检查部件是否已完成扫描（存在 ISSUE_REPORT.md）。"""
    component_name = row.get("component_name", "").strip()
    if not component_name:
        return False

    out_dir = Path(out_base) / component_name
    if not out_dir.exists():
        return False

    # 检查是否存在任何 *_ISSUE_REPORT.md 文件
    issue_reports = list(out_dir.glob("*_ISSUE_REPORT.md"))
    return len(issue_reports) > 0


def save_scan_meta(row: Dict[str, str],
                   out_base: str,
                   status: str,
                   elapsed: float) -> None:
    """保存扫描元数据到 _scan_meta.json。"""
    component_name = row.get("component_name", "")
    out_dir = Path(out_base) / component_name
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "component_name": component_name,
        "kit_name": row.get("kit_name", ""),
        "component_path": row.get("component_path", ""),
        "analyze_depth": row.get("analyze_depth", "thorough"),
        "status": status,
        "scan_time": datetime.now().isoformat(),
        "duration_seconds": round(elapsed, 1),
    }

    meta_file = out_dir / "_scan_meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def scan_single(row: Dict[str, str],
                out_base: str,
                repo_base: str,
                max_retries: int) -> Tuple[str, bool, float]:
    """
    扫描单个部件，返回 (component_name, success, elapsed)。
    """
    component_name = row.get("component_name", "unknown")

    try:
        success, output, elapsed = run_component_scan(
            row=row,
            out_base=out_base,
            repo_base=repo_base,
            max_retries=max_retries,
        )
        status = "success" if success else "failed"
        save_scan_meta(row, out_base, status, elapsed)
        return component_name, success, elapsed

    except Exception as e:
        print(f"[{component_name}] 异常: {e}")
        save_scan_meta(row, out_base, "failed", 0)
        return component_name, False, 0


def main():
    parser = argparse.ArgumentParser(
        description="部件批量扫描 - 并行调用 audit-error-codes-new skill"
    )
    parser.add_argument("-csv", required=True, help="CSV 输入文件路径")
    parser.add_argument("-repo_base", default=DEFAULT_REPO_BASE, help="DataBases 根目录")
    parser.add_argument("-out_base", default=DEFAULT_OUT_BASE, help="扫描结果输出根目录")
    parser.add_argument("-max_parallel", type=int, default=3, help="最大并行数 (默认: 3)")
    parser.add_argument("-max_retries", type=int, default=3, help="单个部件最大重试次数 (默认: 3)")
    parser.add_argument("-force", action="store_true", help="强制重新扫描（忽略已完成的）")
    parser.add_argument("-dry_run", action="store_true", help="仅显示扫描计划，不执行")
    parser.add_argument("-components", default=None, help="仅扫描指定部件，逗号分隔")

    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"[batch_scan] 错误: CSV 文件不存在 {csv_path}")
        return

    # 读取并过滤 CSV
    all_rows = read_csv(csv_path)
    components_filter = None
    if args.components:
        components_filter = [c.strip() for c in args.components.split(",")]

    rows = filter_rows(all_rows, components_filter)

    if not rows:
        print("[batch_scan] 没有需要扫描的部件")
        return

    # 断点续扫：分离已完成和待扫描
    pending = []
    completed = []
    for row in rows:
        component_name = row.get("component_name", "")
        if not args.force and check_completed(row, args.out_base):
            completed.append(row)
        else:
            pending.append(row)

    # 打印扫描计划
    print(f"\n{'=' * 60}")
    print(f"[batch_scan] 扫描计划")
    print(f"  CSV 文件: {csv_path}")
    print(f"  Repo 基础目录: {args.repo_base}")
    print(f"  输出目录: {args.out_base}")
    print(f"  最大并行数: {args.max_parallel}")
    print(f"  总部件数: {len(rows)}")
    print(f"  已完成(跳过): {len(completed)}")
    print(f"  待扫描: {len(pending)}")
    print(f"{'=' * 60}")

    if completed:
        print(f"\n[batch_scan] 将跳过已完成部件:")
        for row in completed:
            print(f"  - {row.get('component_name', '')}")

    if not pending:
        print(f"\n[batch_scan] 所有部件已完成扫描")
        collect_and_summarize(Path(args.out_base))
        return

    print(f"\n[batch_scan] 待扫描部件:")
    for row in pending:
        component_name = row.get("component_name", "")
        kit_name = row.get("kit_name", "")
        depth = row.get("analyze_depth", "thorough")
        print(f"  - {component_name} (Kit: {kit_name}, depth: {depth})")

    if args.dry_run:
        print(f"\n[batch_scan] --dry_run 模式，不执行扫描")
        return

    # 并行扫描
    results = []
    total_start = time.time()

    with ThreadPoolExecutor(max_workers=args.max_parallel) as executor:
        futures = {}
        for row in pending:
            future = executor.submit(
                scan_single,
                row=row,
                out_base=args.out_base,
                repo_base=args.repo_base,
                max_retries=args.max_retries,
            )
            futures[future] = row.get("component_name", "")

        for future in as_completed(futures):
            component_name = futures[future]
            try:
                name, success, elapsed = future.result()
                results.append((name, success, elapsed))
                status = "OK" if success else "FAIL"
                print(f"\n[batch_scan] {status}: {name} ({elapsed:.0f}s)")
            except Exception as e:
                results.append((component_name, False, 0))
                print(f"\n[batch_scan] 异常: {component_name} - {e}")

    total_elapsed = time.time() - total_start

    # 汇总
    success_count = sum(1 for _, s, _ in results if s)
    fail_count = sum(1 for _, s, _ in results if not s)

    print(f"\n{'=' * 60}")
    print(f"[batch_scan] 扫描完成")
    print(f"  总耗时: {total_elapsed:.0f}s")
    print(f"  本次扫描: {len(results)} 个")
    print(f"  成功: {success_count}, 失败: {fail_count}")
    print(f"  已跳过: {len(completed)}")
    print(f"{'=' * 60}")

    # 生成汇总
    collect_and_summarize(Path(args.out_base))


if __name__ == "__main__":
    main()
