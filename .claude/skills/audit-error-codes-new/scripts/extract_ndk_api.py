#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NDK API 提取器
从 HarmonyOS/OpenHarmony Kit 中提取 NDK 层的 C API 声明
"""

import os
import re
import json
import argparse
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class NdkApi:
    """NDK API 信息"""
    name: str
    return_type: str
    params: str
    file: str
    line: int
    description: str = ""


@dataclass
class NdkType:
    """NDK 类型定义"""
    name: str
    type: str  # struct, enum, typedef
    file: str
    line: int


class NdkApiExtractor:
    """NDK API 提取器"""

    # 匹配 OH_ 函数声明（支持返回指针类型，如 "Type *" 或 "Type*" 或 "const char *"）
    # 支持 OH_NetConn_, OH_, OHOS_ 等各种前缀
    # 使用 re.DOTALL 使 . 匹配换行符，支持多行函数声明
    # 使用 [^\S\n]* 代替 \s* 来匹配空白但不包括换行符，确保从正确行开始匹配
    # 捕获组: 1=const修饰符(可选), 2=类型名, 3=指针符号(可选), 4=函数名, 5=参数
    PATTERN_FUNCTION = re.compile(
        r'^[^\S\n]*(?:(const)\s+)?(\w+)\s*(\*?)\s*((?:OH_|OHOS_)\w+)\s*\(([^)]*)\)\s*;',
        re.MULTILINE | re.DOTALL
    )

    # 匹配 typedef struct
    PATTERN_TYPEDEF_STRUCT = re.compile(
        r'typedef\s+(?:struct|union)\s+\w*\s*\{[^}]*\}\s*(\w+);',
        re.DOTALL
    )

    # 匹配 typedef 指针
    PATTERN_TYPEDEF_POINTER = re.compile(
        r'typedef\s+(?:struct\s+)?\w+(?:\s*\*)*\s+(\w+);'
    )

    # 匹配 typedef enum
    PATTERN_TYPEDEF_ENUM = re.compile(
        r'typedef\s+enum\s*\{[^}]*\}\s*(\w+);',
        re.DOTALL
    )

    # 匹配 typedef 函数指针
    PATTERN_TYPEDEF_FUNC_PTR = re.compile(
        r'typedef\s+\w+(?:\s*\*)?\s*\(\s*\*?\s*(\w+)\s*\)\s*\([^)]*\)'
    )

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.ndk_apis: List[NdkApi] = []
        self.ndk_types: List[NdkType] = []

    def extract_all(self) -> Dict:
        """提取所有 NDK API"""
        # 1. 查找 NDK 头文件
        ndk_files = self._find_ndk_files()

        # 2. 解析每个文件
        for file_path in ndk_files:
            self._parse_file(file_path)

        return self._to_dict()

    def _find_ndk_files(self) -> List[Path]:
        """查找 NDK 头文件"""
        ndk_files = []

        # 搜索标准 NDK 目录
        ndk_dirs = [
            self.root_path / "interfaces" / "ndk" / "include",
            self.root_path / "interfaces" / "kits" / "c",  # 支持 kits/c 目录
        ]

        for ndk_dir in ndk_dirs:
            if ndk_dir.exists():
                for f in ndk_dir.rglob("*.h"):
                    ndk_files.append(f)

        # 如果没有找到，尝试搜索整个项目
        if not ndk_files:
            for f in self.root_path.rglob("*.h"):
                # 检查文件是否包含 OH_ 或 OHOS_ 前缀的函数
                try:
                    content = f.read_text(encoding='utf-8', errors='ignore')
                    if re.search(r'(?:OH_|OHOS_)\w+\s*\(', content):
                        ndk_files.append(f)
                except:
                    pass

        # 去重
        return list(set(ndk_files))

    def _parse_file(self, file_path: Path):
        """解析单个文件"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except:
            return

        relative_path = str(file_path.relative_to(self.root_path))
        lines = content.split('\n')

        # 1. 解析函数声明
        self._parse_functions(content, lines, relative_path)

        # 2. 解析类型定义
        self._parse_types(content, lines, relative_path)

    def _parse_functions(self, content: str, lines: List[str], file_path: str):
        """解析函数声明"""
        for match in self.PATTERN_FUNCTION.finditer(content):
            const_modifier = match.group(1)  # 可选的 const
            type_name = match.group(2).strip()
            pointer = match.group(3).strip()  # 可选的指针符号 *
            func_name = match.group(4).strip()
            params = match.group(5).strip()

            # 构建完整的返回类型
            if const_modifier:
                return_type = f"const {type_name} *"
            elif pointer:
                return_type = f"{type_name} *"
            else:
                return_type = type_name

            # 清理参数（移除多余空格）
            params = re.sub(r'\s+', ' ', params)

            # 计算行号
            line_no = content[:match.start()].count('\n') + 1

            # 检查是否已存在
            if not any(a.name == func_name for a in self.ndk_apis):
                self.ndk_apis.append(NdkApi(
                    name=func_name,
                    return_type=return_type,
                    params=params,
                    file=file_path,
                    line=line_no
                ))

    def _parse_types(self, content: str, lines: List[str], file_path: str):
        """解析类型定义"""
        # 解析 typedef struct/union
        for match in self.PATTERN_TYPEDEF_STRUCT.finditer(content):
            type_name = match.group(1).strip()
            line_no = content[:match.start()].count('\n') + 1

            if not any(t.name == type_name for t in self.ndk_types):
                self.ndk_types.append(NdkType(
                    name=type_name,
                    type="struct",
                    file=file_path,
                    line=line_no
                ))

        # 解析 typedef enum
        for match in self.PATTERN_TYPEDEF_ENUM.finditer(content):
            type_name = match.group(1).strip()
            line_no = content[:match.start()].count('\n') + 1

            if not any(t.name == type_name for t in self.ndk_types):
                self.ndk_types.append(NdkType(
                    name=type_name,
                    type="enum",
                    file=file_path,
                    line=line_no
                ))

        # 解析 typedef 函数指针
        for match in self.PATTERN_TYPEDEF_FUNC_PTR.finditer(content):
            type_name = match.group(1).strip()
            line_no = content[:match.start()].count('\n') + 1

            if not any(t.name == type_name for t in self.ndk_types):
                self.ndk_types.append(NdkType(
                    name=type_name,
                    type="func_ptr",
                    file=file_path,
                    line=line_no
                ))

    def _to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "metadata": {
                "root_path": str(self.root_path),
                "ndk_api_count": len(self.ndk_apis),
                "ndk_type_count": len(self.ndk_types),
            },
            "ndk_apis": [asdict(a) for a in self.ndk_apis],
            "ndk_types": [asdict(t) for t in self.ndk_types]
        }

    def print_summary(self):
        """打印摘要"""
        print("=" * 60)
        print("NDK API 提取结果")
        print("=" * 60)
        print(f"NDK API: {len(self.ndk_apis)} 个")
        print(f"NDK 类型: {len(self.ndk_types)} 个")

        if self.ndk_apis:
            print(f"\nNDK API 列表:")
            for a in self.ndk_apis[:10]:
                params_short = a.params[:40] + "..." if len(a.params) > 40 else a.params
                print(f"  {a.return_type} {a.name}({params_short})")
            if len(self.ndk_apis) > 10:
                print(f"  ... 还有 {len(self.ndk_apis) - 10} 个")

        if self.ndk_types:
            print(f"\nNDK 类型列表:")
            for t in self.ndk_types[:10]:
                print(f"  {t.type} {t.name}")
            if len(self.ndk_types) > 10:
                print(f"  ... 还有 {len(self.ndk_types) - 10} 个")

        print("=" * 60)

    def export_json(self, output_path: str):
        """导出为 JSON"""
        data = self._to_dict()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ JSON 已导出: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="NDK API 提取器 - 从 Kit 中提取 NDK 层 API"
    )
    parser.add_argument("component_path", help="部件目录路径（如 DataBases/communication_netmanager_base）")
    parser.add_argument("-o", "--output", default="ndk_api.json", help="输出文件路径")

    args = parser.parse_args()

    print(f"🔍 分析目录: {args.component_path}")

    extractor = NdkApiExtractor(args.component_path)
    extractor.extract_all()
    extractor.print_summary()
    extractor.export_json(args.output)


if __name__ == "__main__":
    main()
