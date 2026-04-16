"""
batch_scan_all.py - 批量遍历所有 Kit 调用 scan_kit.py

从 kit_compont.csv 中提取去重的 Kit 名称，依次生成并执行 scan_kit.py 命令。
python3 /Users/spongbob/for_guance/api_dfx_2.0/scripts/kit-scan/batch_scan_all.py -kits "Ability" -doc_path /Users/spongbob/for_guance/api_dfx_2.0/data/docs -skip_extract
"""

import subprocess
import sys
from pathlib import Path

import batch_pipeline

# 跨目录导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.kit_utils import load_unique_kit_names
from common.config import load_config, find_config_file

# ============================================================
# 路径配置 - 优先从配置文件读取，否则使用默认值
# ============================================================

# kit_compont.csv 权威路径
CSV_PATH: Path = (
    Path(__file__).resolve().parent.parent / "assets" / "kit_compont.csv"
)

# scan_kit.py 路径（同目录下）
SCAN_KIT_SCRIPT: Path = Path(__file__).resolve().parent / "scan_kit.py"

# 加载配置
_config = load_config(find_config_file(Path(__file__).resolve().parent))

JS_DECL_PATH: str = _config.get("js_decl_path", "/Users/spongbob/for_guance/api_dfx/api/interface_sdk-js")
C_DECL_PATH: str = _config.get("c_decl_path", "")
REPO_BASE: str = _config.get("repo_base", "/Users/spongbob/for_guance/api_dfx/DataBases")
OUT_PATH: str = _config.get("out_path", "/Users/spongbob/for_guance/api_dfx_2.0/scan_out/scan-test_417")
DOC_PATH: str = _config.get("doc_path", "/Users/spongbob/for_guance/api_dfx_2.0/data/docs")


def build_command(kit_name: str, skip_extract: bool = False, doc_path: str = "", c_decl_path: str = "") -> list[str]:
    """构建单个 Kit 的 scan_kit.py 命令。"""
    cmd = [
        sys.executable,
        str(SCAN_KIT_SCRIPT),
        "-kit", kit_name,
        "-js_decl_path", JS_DECL_PATH,
        "-repo_base", REPO_BASE,
        "-out_path", OUT_PATH,
    ]
    if skip_extract:
        cmd.append("-skip_extract")
    if doc_path:
        cmd.extend(["-doc_path", doc_path])
    if c_decl_path:
        cmd.extend(["-c_decl_path", c_decl_path])
    return cmd


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="批量遍历所有 Kit 调用 scan_kit.py")
    parser.add_argument("-n", "--dry-run", action="store_true", help="仅打印命令，不执行")
    parser.add_argument(
        "-kits",
        nargs="+",
        help="指定要扫描的 Kit 名称列表（支持子串匹配），不指定则扫描全部",
    )
    parser.add_argument(
        "-skip_extract",
        action="store_true",
        help="跳过 kit-api-extract 步骤（已有 api.jsonl 和 impl_api.jsonl 时使用）",
    )
    parser.add_argument(
        "-doc_path",
        default=str(DOC_PATH),
        help=f"API 错误码文档目录路径 (默认: {DOC_PATH})",
    )
    return parser.parse_args()


def check_paths():
    """检查关键路径是否存在，不存在则报错退出。"""
    errors = []
    if not CSV_PATH.exists():
        errors.append(f"CSV 文件不存在: {CSV_PATH}")
    if not SCAN_KIT_SCRIPT.exists():
        errors.append(f"scan_kit.py 不存在: {SCAN_KIT_SCRIPT}")
    if not Path(JS_DECL_PATH).exists():
        errors.append(f"SDK 声明目录不存在: {JS_DECL_PATH}")
    if C_DECL_PATH and not Path(C_DECL_PATH).exists():
        print(f"[警告] C SDK 声明目录不存在: {C_DECL_PATH}（将跳过 C API 提取）")
    if not Path(REPO_BASE).exists():
        errors.append(f"仓库基础目录不存在: {REPO_BASE}")

    if errors:
        for e in errors:
            print(f"[错误] {e}")
        sys.exit(1)


def main():
    check_paths()
    args = parse_args()

    all_kits = load_unique_kit_names(CSV_PATH)

    # 按 -kits 参数过滤
    if args.kits:
        kits = [k for k in all_kits if any(filt.lower() in k.lower() for filt in args.kits)]
        print(f"过滤后 {len(kits)}/{len(all_kits)} 个 Kit (过滤词: {args.kits})\n")
    else:
        kits = all_kits
        print(f"共发现 {len(kits)} 个 Kit\n")

    for i, kit in enumerate(kits, 1):
        cmd = build_command(kit, args.skip_extract, args.doc_path, C_DECL_PATH)
        cmd_str = " ".join(cmd)

        if args.dry_run:
            print(f"[{i}/{len(kits)}] {cmd_str}")
        else:
            print(f"\n{'=' * 60}")
            print(f"[{i}/{len(kits)}] 正在处理: {kit}")
            print(f"命令: {cmd_str}")
            print("=" * 60)

            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"[警告] Kit '{kit}' 处理失败 (退出码: {result.returncode})，继续下一个")

    if args.dry_run:
        print(f"\n--dry-run 模式，共 {len(kits)} 条命令，未实际执行")
    else:
        # 汇总所有 Kit 的统计数据
        print("\n" + "=" * 60)
        print("生成全量汇总报表")
        print("=" * 60)

        out_root = Path(OUT_PATH)
        stats_list = []
        for kit_dir in sorted(out_root.iterdir()):
            if not kit_dir.is_dir():
                continue
            if not (kit_dir / "api.jsonl").exists():
                continue
            kit_name = kit_dir.name
            print(f"  统计: {kit_name}")
            try:
                stats = batch_pipeline.compute_kit_stats(kit_dir, kit_name)
                stats_list.append(stats)
            except Exception as e:
                print(f"  [警告] {kit_name} 统计失败: {e}")

        if stats_list:
            batch_pipeline.write_summary_markdown(
                stats_list,
                out_root / "all_kits_summary.md",
                title="全量 Kit 审计汇总报表",
            )
            batch_pipeline.write_summary_xlsx(
                stats_list,
                out_root / "all_kits_summary.xlsx",
                title="全量 Kit 审计汇总报表",
            )
        else:
            print("[提示] 无有效 Kit 数据，跳过全量汇总报表生成")


if __name__ == "__main__":
    main()
