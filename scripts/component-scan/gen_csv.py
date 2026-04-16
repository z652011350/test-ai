"""
gen_csv.py - 从 kit_compont.csv 生成 components.csv

读取 Kit-Component 映射 CSV，生成部件扫描所需的 components.csv 输入文件。
支持按 Kit 过滤和指定默认分析深度。
"""

import argparse
import csv
import sys
from pathlib import Path

# 跨目录导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def generate_csv(kit_mapping_path: Path,
                 output_path: Path,
                 kits_filter: list = None,
                 analyze_depth: str = "thorough") -> int:
    """
    从 kit_compont.csv 生成 components.csv。

    Args:
        kit_mapping_path: kit_compont.csv 路径
        output_path: 输出 components.csv 路径
        kits_filter: 仅包含这些 Kit（None 表示全部）
        analyze_depth: 默认分析深度

    Returns:
        生成的部件数量
    """
    if not kit_mapping_path.exists():
        print(f"[gen_csv] 错误: 文件不存在 {kit_mapping_path}")
        return 0

    # 读取 kit_compont.csv
    rows = []
    with open(kit_mapping_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kit = row.get("kit", "").strip()
            component = row.get("component", "").strip()
            if not kit or not component:
                continue
            rows.append({"kit": kit, "component": component})

    # 按 Kit 过滤
    if kits_filter:
        kit_set = set(k.strip() for k in kits_filter)
        rows = [r for r in rows if r["kit"] in kit_set]
        print(f"[gen_csv] 过滤 Kit: {kit_set}")

    # 生成 components.csv
    fieldnames = [
        "component_name", "component_path", "kit_name",
        "api_doc_path", "api_error_doc_path", "analyze_depth", "enabled"
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in rows:
            writer.writerow({
                "component_name": r["component"],
                "component_path": "",  # 自动拼接
                "kit_name": r["kit"],
                "api_doc_path": "",
                "api_error_doc_path": "",
                "analyze_depth": analyze_depth,
                "enabled": "yes",
            })

    print(f"[gen_csv] 生成 {output_path}: {len(rows)} 个部件")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="从 kit_compont.csv 生成部件扫描 CSV 输入文件"
    )
    parser.add_argument(
        "-kit_mapping",
        default=str(
            Path(__file__).resolve().parent.parent.parent
            / ".claude" / "skills" / "api-level-scan" / "assets" / "kit_compont.csv"
        ),
        help="kit_compont.csv 路径",
    )
    parser.add_argument(
        "-kits", default=None,
        help="仅生成指定 Kit 的部件，逗号分隔 (如 'Network Kit,Image Kit')",
    )
    parser.add_argument(
        "-analyze_depth", default="thorough",
        choices=["quick", "medium", "thorough"],
        help="默认分析深度 (默认: thorough)",
    )
    parser.add_argument(
        "-o", "--output", default="components.csv",
        help="输出文件路径 (默认: components.csv)",
    )

    args = parser.parse_args()

    kits_filter = None
    if args.kits:
        kits_filter = [k.strip() for k in args.kits.split(",")]

    count = generate_csv(
        kit_mapping_path=Path(args.kit_mapping),
        output_path=Path(args.output),
        kits_filter=kits_filter,
        analyze_depth=args.analyze_depth,
    )

    if count > 0:
        print(f"[gen_csv] 完成！可使用以下命令开始扫描:")
        print(f"  python batch_scan.py -csv {args.output}")


if __name__ == "__main__":
    main()
