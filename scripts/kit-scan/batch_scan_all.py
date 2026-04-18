"""
batch_scan_all.py - 批量遍历所有 Kit 调用 scan_kit.py（并行版）

从 kit_compont.csv 中提取去重的 Kit 名称，并行生成并执行 scan_kit.py 命令。
每个进程启动时带随机延迟（1.0-10.0s），最多同时运行 max_parallel 个进程。

用法:
  python3 batch_scan_all.py -kits "Ability" -doc_path /path/to/docs -skip_extract
  python3 batch_scan_all.py -kits "Ability" "BasicServicesKit" -max_parallel 2
"""

import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def run_kit_worker(kit_name: str, cmd: list[str], index: int, total: int) -> tuple[str, int]:
    """Worker 函数：随机延迟后执行单个 Kit 的 scan_kit.py 命令。

    Args:
        kit_name: Kit 名称
        cmd: scan_kit.py 命令及参数
        index: 当前 Kit 序号（从 1 开始）
        total: 总 Kit 数

    Returns:
        (kit_name, returncode) 元组
    """
    delay = random.uniform(1.0, 10.0)
    print(f"[{index}/{total}] {kit_name} 延迟 {delay:.1f}s 后启动...")
    time.sleep(delay)

    print(f"[{index}/{total}] 启动: {kit_name}")
    print(f"  命令: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return (kit_name, result.returncode)


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="批量遍历所有 Kit 调用 scan_kit.py（并行版）")
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
    parser.add_argument(
        "-max_parallel",
        type=int,
        default=_config.get("max_parallel", 3),
        help=f"最大并行进程数 (默认: {_config.get('max_parallel', 3)})",
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

    # 构建所有 Kit 的命令
    kit_commands = []
    for i, kit in enumerate(kits, 1):
        cmd = build_command(kit, args.skip_extract, args.doc_path, C_DECL_PATH)
        kit_commands.append((kit, cmd))

    if args.dry_run:
        # dry-run 模式：顺序打印命令，不执行
        for i, (kit, cmd) in enumerate(kit_commands, 1):
            cmd_str = " ".join(cmd)
            print(f"[{i}/{len(kit_commands)}] {cmd_str}")
        print(f"\n--dry-run 模式，共 {len(kit_commands)} 条命令，未实际执行")
    else:
        # 并行执行模式
        max_parallel = args.max_parallel
        total = len(kit_commands)
        print(f"\n并行执行: 共 {total} 个 Kit, 最大并发数: {max_parallel}")
        print("=" * 60)

        results: list[tuple[str, int]] = []
        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            future_to_kit = {}
            for i, (kit, cmd) in enumerate(kit_commands, 1):
                future = pool.submit(run_kit_worker, kit, cmd, i, total)
                future_to_kit[future] = kit

            for future in as_completed(future_to_kit):
                kit = future_to_kit[future]
                try:
                    kit_name, returncode = future.result()
                    results.append((kit_name, returncode))
                    if returncode != 0:
                        print(f"[警告] Kit '{kit_name}' 处理失败 (退出码: {returncode})")
                    else:
                        print(f"[完成] Kit '{kit_name}' 处理成功")
                except Exception as exc:
                    print(f"[错误] Kit '{kit}' 执行异常: {exc}")
                    results.append((kit, -1))

        # 打印执行结果汇总
        failed = [(name, rc) for name, rc in results if rc != 0]
        print(f"\n{'=' * 60}")
        print(f"执行完毕: {total} 个 Kit, 成功 {total - len(failed)} 个, 失败 {len(failed)} 个")
        if failed:
            for name, rc in failed:
                print(f"  失败: {name} (退出码: {rc})")
        print("=" * 60)

        # 汇总报表生成
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
