"""
scan_kit.py - Kit 级 API 审计流水线入口

完整流水线：
  Step 1: 调用 Claude CLI 使用 kit-api-extract 技能提取 Kit API 数据
  Step 2: 按批次调用 Claude CLI 使用 api-level-scan 技能进行审计（已注释）

用法:
  python scan_kit.py -kit 'Ability Kit' -out_path 'path/to/out' \
    -js_decl_path 'path/to/interface_sdk-js' -repo_base 'path/to/database'
"""

import argparse
import sys
from pathlib import Path

import claude_runner

# 跨目录导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.kit_utils import normalize_kit_name, resolve_kit_file


def build_extract_prompt(
    kit_name: str, js_sdk_path: str, repo_base: str, output_dir: str,
    c_sdk_path: str = ""
) -> str:
    """生成 kit-api-extract 技能的 prompt。"""
    prompt = (
        f"/kit-api-extract\n"
        f"kit_name = {kit_name}\n"
        f"js_sdk_path = {js_sdk_path}\n"
        f"databases_dir = {repo_base}\n"
        f"output_dir = {output_dir}"
    )
    if c_sdk_path:
        prompt += f"\nc_sdk_path = {c_sdk_path}"
    return prompt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kit 级 API DFX 审计流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-kit", required=True, help='Kit 名称，如 "Ability Kit" 或 "AbilityKit"'
    )
    parser.add_argument(
        "-out_path", required=True, help="输出根目录"
    )
    parser.add_argument(
        "-js_decl_path", required=True, help="interface_sdk-js 目录路径"
    )
    parser.add_argument(
        "-repo_base", required=True, help="DataBases 目录路径（包含各部件仓库）"
    )
    parser.add_argument(
        "-batch_size", type=int, default=40, help="每个 batch 包含的 API 数量 (默认: 40)"
    )
    parser.add_argument(
        "-skip_extract",
        action="store_true",
        help="跳过 kit-api-extract 步骤（已有 api.jsonl 和 impl_api.jsonl 时使用）",
    )
    parser.add_argument(
        "-doc_path",
        default="",
        help="API 错误码文档目录路径（可选）",
    )
    parser.add_argument(
        "-c_decl_path",
        default="",
        help="interface_sdk_c 目录路径（可选，提供时启用 C API 提取）",
    )
    return parser.parse_args()


def main():
    print("=" * 60)
    print("Kit 级 API 审计流水线")
    print("=" * 60)

    args = parse_args()

    # 标准化 Kit 名称
    kit_name = normalize_kit_name(args.kit)
    output_dir = Path(args.out_path) / kit_name
    js_decl_path = Path(args.js_decl_path)
    repo_base = Path(args.repo_base).resolve()
    c_decl_path = Path(args.c_decl_path) if args.c_decl_path else None

    print(f"\nKit: {kit_name}")
    print(f"输出目录: {output_dir}")
    print(f"SDK 路径: {js_decl_path}")
    if c_decl_path:
        print(f"C SDK 路径: {c_decl_path}")
    print(f"仓库基础: {repo_base}")
    print(f"Batch 大小: {args.batch_size}")

    # 验证 Kit 声明文件存在
    kit_file = resolve_kit_file(kit_name, js_decl_path)
    print(f"Kit 声明文件: {kit_file}")

    # ========================================
    # Step 1: 调用 kit-api-extract 提取 API
    # ========================================
    if not args.skip_extract:
        print("\n" + "=" * 60)
        print("Step 1: 调用 kit-api-extract 提取 API 数据")
        print("=" * 60)

        output_dir.mkdir(parents=True, exist_ok=True)

        prompt = build_extract_prompt(
            kit_name, str(js_decl_path), str(repo_base), str(output_dir),
            c_sdk_path=str(c_decl_path) if c_decl_path else ""
        )

        success, _ = claude_runner.run_claude_command(prompt)
        if not success:
            print("[错误] kit-api-extract 执行失败")
            sys.exit(1)

        # 验证输出文件
        api_path = output_dir / "api.jsonl"
        impl_api_path = output_dir / "impl_api.jsonl"
        if not api_path.exists() or not impl_api_path.exists():
            print(f"[错误] 提取后未找到 api.jsonl 或 impl_api.jsonl")
            print(f"  api.jsonl: {api_path} ({'存在' if api_path.exists() else '不存在'})")
            print(f"  impl_api.jsonl: {impl_api_path} ({'存在' if impl_api_path.exists() else '不存在'})")
            sys.exit(1)
    else:
        print("\n[跳过] kit-api-extract 步骤 (-skip_extract)")

    print("\n" + "=" * 60)
    print("流水线执行完毕")
    print("=" * 60)


if __name__ == "__main__":
    main()
