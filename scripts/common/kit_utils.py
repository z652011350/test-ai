"""
kit_utils.py - Kit 辅助函数共享模块

提供 Kit 名称规范化、Kit 声明文件查找、CSV 读取等公共功能。
从 kit-scan/scan_kit.py 和 kit-scan/batch_scan_all.py 提取的公共逻辑。
"""

import csv
from pathlib import Path


def normalize_kit_name(raw_name: str) -> str:
    """
    标准化 Kit 名称。
    "Ability Kit" -> "AbilityKit"
    "AbilityKit" -> "AbilityKit" (幂等)
    """
    return raw_name.replace(" ", "")


def resolve_kit_file(kit_name: str, js_sdk_path: Path) -> Path:
    """
    查找 Kit 声明文件，依次尝试 .d.ts / .d.ets / .static.d.ets。

    Raises:
        FileNotFoundError: 所有扩展名均未找到
    """
    candidates = [
        js_sdk_path / "kits" / f"@kit.{kit_name}.d.ts",
        js_sdk_path / "kits" / f"@kit.{kit_name}.d.ets",
        js_sdk_path / "kits" / f"@kit.{kit_name}.static.d.ets",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"找不到 Kit 声明文件: @kit.{kit_name}.d.ts/.d.ets\n"
        f"已搜索: {[str(c) for c in candidates]}"
    )


def load_unique_kit_names(csv_path: Path) -> list[str]:
    """从 CSV 中提取去重且保持顺序的 kit 名称列表。"""
    kits: list[str] = []
    seen: set[str] = set()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # 跳过表头 kit,component
        for row in reader:
            if not row:
                continue
            kit = row[0].strip()
            if kit and kit not in seen:
                seen.add(kit)
                kits.append(kit)
    print(f"从 {csv_path} 中提取到 {len(kits)} 个唯一 Kit 名称")
    return kits
