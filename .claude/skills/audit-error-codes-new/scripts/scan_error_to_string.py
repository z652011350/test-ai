#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
错误码转字符串问题扫描器
扫描 HarmonyOS/OpenHarmony Kit 中的错误码被转换为字符串的问题
"""

import os
import re
import json
import argparse
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from pathlib import Path
from collections import defaultdict


@dataclass
class Issue:
    """问题信息"""
    type: str
    file: str
    line: int
    code_snippet: str
    context: str = ""


class ErrorToStringScanner:
    """错误码转字符串问题扫描器"""

    # 匹配 napi_throw_error 中使用 to_string
    PATTERN_THROW_TO_STRING = re.compile(
        r'napi_throw_error\s*\(\s*[^,]*,\s*(?:std::)?to_string\s*\(([^)]+)\)\s*\.c_str\(\)',
        re.IGNORECASE
    )

    # 匹配 napi_create_string_utf8 用于错误码
    PATTERN_CREATE_STRING = re.compile(
        r'napi_create_string_utf8\s*\([^,]*,\s*(?:std::)?to_string\s*\(([^)]+)\)\s*\.c_str\(\)',
        re.IGNORECASE
    )

    # 匹配 napi_create_error 中使用 to_string
    PATTERN_CREATE_ERROR = re.compile(
        r'napi_create_error\s*\([^,]*,\s*(?:std::)?to_string\s*\(([^)]+)\)\s*\.c_str\(\)',
        re.IGNORECASE
    )

    # 匹配宏定义中的 to_string 错误码
    PATTERN_MACRO_TO_STRING = re.compile(
        r'#define\s+\w+[^\\]*to_string\s*\(\s*\w+\s*\)\s*\.c_str\(\)',
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.issues: List[Issue] = []

    def scan_all(self) -> Dict:
        """扫描所有代码"""
        # 1. 查找 NAPI 层文件
        napi_files = self._find_napi_files()

        # 2. 扫描每个文件
        for file_path in napi_files:
            self._scan_file(file_path)

        return self._to_dict()

    def _find_napi_files(self) -> List[Path]:
        """查找 NAPI 相关文件"""
        napi_files = []

        # 搜索 frameworks/js 目录
        for pattern in ['**/*.cpp', '**/*.h']:
            for f in self.root_path.rglob(pattern):
                # 只搜索 frameworks/js 目录下的文件
                if 'frameworks/js' in str(f) or 'napi' in str(f).lower():
                    napi_files.append(f)

        # 去重
        return list(set(napi_files))

    def _scan_file(self, file_path: Path):
        """扫描单个文件"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except:
            return

        relative_path = str(file_path.relative_to(self.root_path))
        lines = content.split('\n')

        # 1. 扫描 napi_throw_error
        self._scan_pattern(content, lines, relative_path,
                          self.PATTERN_THROW_TO_STRING, "napi_throw_error_to_string")

        # 2. 扫描 napi_create_string_utf8
        self._scan_pattern(content, lines, relative_path,
                          self.PATTERN_CREATE_STRING, "napi_create_string_utf8")

        # 3. 扫描 napi_create_error
        self._scan_pattern(content, lines, relative_path,
                          self.PATTERN_CREATE_ERROR, "napi_create_error_to_string")

        # 4. 扫描宏定义
        self._scan_macro(content, lines, relative_path)

    def _scan_pattern(self, content: str, lines: List[str], file_path: str,
                      pattern: re.Pattern, issue_type: str):
        """使用正则模式扫描"""
        for match in pattern.finditer(content):
            line_no = content[:match.start()].count('\n') + 1

            # 获取代码片段（当前行及前后各2行）
            start_line = max(0, line_no - 3)
            end_line = min(len(lines), line_no + 2)
            code_snippet = '\n'.join(lines[start_line:end_line])

            self.issues.append(Issue(
                type=issue_type,
                file=file_path,
                line=line_no,
                code_snippet=code_snippet,
                context=match.group(1).strip() if match.groups() else ""
            ))

    def _scan_macro(self, content: str, lines: List[str], file_path: str):
        """扫描宏定义中的问题"""
        for match in self.PATTERN_MACRO_TO_STRING.finditer(content):
            line_no = content[:match.start()].count('\n') + 1

            start_line = max(0, line_no - 3)
            end_line = min(len(lines), line_no + 5)
            code_snippet = '\n'.join(lines[start_line:end_line])

            self.issues.append(Issue(
                type="macro_to_string",
                file=file_path,
                line=line_no,
                code_snippet=code_snippet,
                context="macro"
            ))

    def _to_dict(self) -> Dict:
        """转换为字典"""
        # 按文件分组统计
        by_file = defaultdict(int)
        by_type = defaultdict(int)
        for issue in self.issues:
            by_file[issue.file] += 1
            by_type[issue.type] += 1

        return {
            "metadata": {
                "root_path": str(self.root_path),
                "total_issues": len(self.issues),
                "files_with_issues": len(by_file),
            },
            "summary": {
                "by_file": dict(by_file),
                "by_type": dict(by_type)
            },
            "issues": [asdict(i) for i in self.issues]
        }

    def print_summary(self):
        """打印摘要"""
        print("=" * 60)
        print("错误码转字符串问题扫描结果")
        print("=" * 60)
        print(f"发现 {len(self.issues)} 处问题")

        if self.issues:
            # 按文件分组
            by_file = defaultdict(list)
            for issue in self.issues:
                by_file[issue.file].append(issue)

            print(f"\n问题分布:")
            for file_path, issues in by_file.items():
                print(f"\n  📄 {file_path} ({len(issues)} 处)")
                for issue in issues:
                    print(f"     Line {issue.line}: [{issue.type}]")
                    # 显示代码片段的第一行
                    first_line = issue.code_snippet.split('\n')[0].strip()
                    if len(first_line) > 60:
                        first_line = first_line[:60] + "..."
                    print(f"       {first_line}")

        print("=" * 60)

    def export_json(self, output_path: str):
        """导出为 JSON"""
        data = self._to_dict()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ JSON 已导出: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="错误码转字符串问题扫描器 - 扫描 Kit 中的错误码转换问题"
    )
    parser.add_argument("component_path", help="部件目录路径（如 DataBases/communication_netmanager_base）")
    parser.add_argument("-o", "--output", default="error_to_string_issues.json", help="输出文件路径")

    args = parser.parse_args()

    print(f"🔍 分析目录: {args.component_path}")

    scanner = ErrorToStringScanner(args.component_path)
    scanner.scan_all()
    scanner.print_summary()
    scanner.export_json(args.output)


if __name__ == "__main__":
    main()
