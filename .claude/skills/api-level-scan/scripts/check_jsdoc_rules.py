#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
声明层 JSDoc 规则检查脚本。

对 HarmonyOS/OpenHarmony API 声明文件执行纯声明层检查：
- 规则 01.001: @permission 存在时，@throws 中必须声明 201
- 规则 01.002: @systemapi 存在时，@throws 中必须声明 202
- 规则 01.003: @since >= 24 时，@throws 中不应显式列出 401

仅输出 non-compliant 的记录（JSONL 格式），与 api-level-scan 的 raw_findings 格式兼容。

用法:
    python3 check_jsdoc_rules.py \\
      --js_sdk /path/to/interface_sdk-js \\
      --api_list /path/to/api.jsonl \\
      -o /path/to/output

输出:
    <output_dir>/jsdoc_rule_findings.jsonl — 声明层检查的 non-compliant findings
    <output_dir>/jsdoc_rule_findings.json — 同内容的 JSON 数组（供合并用）
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ============================================================
# JSDoc 解析（复用 extract_kit_api.py 的逻辑）
# ============================================================

def extract_tag_value(blocks, tag):
    """从注释块列表中提取标签值（取最后一个块的值）。"""
    for block in reversed(blocks):
        for line in block.split('\n'):
            m = re.match(rf'\s*\*\s*{re.escape(tag)}\s+(.+)', line)
            if m:
                return m.group(1).strip()
    return ''


def has_tag(blocks, tag):
    """检查注释块列表中是否包含某标签。"""
    for block in blocks:
        for line in block.split('\n'):
            if re.match(rf'\s*\*\s*{re.escape(tag)}\b', line):
                return True
    return False


def extract_all_tag_values(blocks, tag):
    """提取所有指定标签的值列表。"""
    values = []
    for block in blocks:
        for line in block.split('\n'):
            m = re.match(rf'\s*\*\s*{re.escape(tag)}\s+(.+)', line)
            if m:
                values.append(m.group(1).strip())
    return values


def extract_throws_codes(blocks):
    """从 JSDoc 块列表中提取 @throws 错误码列表（仅返回错误码数字）。"""
    codes = set()
    for block in blocks:
        lines = block.split('\n')
        for line in lines:
            m = re.match(
                r'\s*\*\s*@throws\s*\{\s*\w+\s*\}\s*(\d+)\s*-', line
            )
            if m:
                codes.add(m.group(1))
    return codes


def parse_since_version(since_raw):
    """从 @since 原始值中提取版本号数字。

    "24" → 24
    "24 dynamic&static" → 24
    "6.1.1(24)" → 24
    "23 static" → 23
    """
    if not since_raw:
        return 0
    # 处理 "6.1.1(24)" 格式
    m = re.search(r'\((\d+)\)', since_raw)
    if m:
        return int(m.group(1))
    # 取第一个数字
    m = re.match(r'(\d+)', since_raw)
    if m:
        return int(m.group(1))
    return 0


# ============================================================
# 声明文件解析
# ============================================================

def find_api_jsdoc(content, api_declaration):
    """在声明文件内容中查找指定 API 的 JSDoc 块列表。

    返回匹配的 JSDoc 文本列表（可能为多个连续块），或 None。
    """
    # 查找所有 JSDoc 块
    jsdoc_re = re.compile(r'/\*\*[\s\S]*?\*/', re.MULTILINE)
    matches = list(jsdoc_re.finditer(content))

    if not matches:
        return None

    # 清理 api_declaration 用于匹配（去掉修饰符，取核心签名）
    clean_decl = re.sub(r'^(?:export\s+)?(?:declare\s+)?', '', api_declaration.strip())
    clean_decl = ' '.join(clean_decl.split())  # 标准化空白

    i = 0
    while i < len(matches):
        # 收集连续的 JSDoc 块
        blocks = [matches[i]]
        j = i + 1
        while j < len(matches):
            gap = content[matches[j - 1].end():matches[j].start()]
            if gap.strip() == '':
                blocks.append(matches[j])
                j += 1
            else:
                break

        # 提取声明文本
        after_text = content[blocks[-1].end():]
        decl = extract_declaration_text(after_text)

        if decl:
            clean_found = re.sub(r'^(?:export\s+)?(?:declare\s+)?', '', decl.strip())
            clean_found = ' '.join(clean_found.split())

            # 模糊匹配：检查核心签名是否一致
            if _signatures_match(clean_found, clean_decl):
                return [b.group() for b in blocks]

        i = j

    return None


def extract_declaration_text(text):
    """从注释块后的文本中提取声明（到 ; 或 } 或下一个 /** 为止）。"""
    text = text.lstrip()
    if not text:
        return ''
    brace = 0
    in_str = False
    sch = None
    for i, ch in enumerate(text):
        if ch in '"\'`' and (i == 0 or text[i - 1] != '\\'):
            if not in_str:
                in_str = True
                sch = ch
            elif ch == sch:
                in_str = False
        elif not in_str:
            if ch == '{':
                brace += 1
            elif ch == '}':
                brace -= 1
                if brace < 0:
                    return text[:i].strip()
            elif ch == ';' and brace == 0:
                return text[:i].strip()
            elif text[i:i + 3] == '/**':
                return text[:i].strip()
    dnl = text.find('\n\n')
    if dnl > 0:
        return text[:dnl].strip()
    return text.strip()


def _signatures_match(found, target):
    """检查两个签名是否匹配（宽松比较）。"""
    # 去掉装饰器
    def strip_decorators(s):
        while s.startswith('@'):
            m = re.match(r'@\w+\s*', s)
            if m:
                s = s[m.end():].lstrip()
            else:
                break
        return s

    f = strip_decorators(' '.join(found.split()))
    t = strip_decorators(' '.join(target.split()))

    # 完全匹配
    if f == t:
        return True

    # 提取函数名和参数部分进行匹配
    f_name = re.match(r'(?:static\s+)?(?:readonly\s+)?(?:async\s+)?(?:function\s+)?(\w+)\s*\(', f)
    t_name = re.match(r'(?:static\s+)?(?:readonly\s+)?(?:async\s+)?(?:function\s+)?(\w+)\s*\(', t)

    if f_name and t_name and f_name.group(1) == t_name.group(1):
        # 同名函数，比较参数列表
        return True

    return False


# ============================================================
# 规则检查
# ============================================================

def check_rule_01_001(jsdoc_blocks, api_declaration, module_name, declaration_file):
    """规则 01.001: @permission 存在时，@throws 中必须声明 201。"""
    if not has_tag(jsdoc_blocks, '@permission'):
        return None  # 规则不适用

    throws_codes = extract_throws_codes(jsdoc_blocks)
    if '201' in throws_codes:
        return None  # 合规

    permission_val = extract_tag_value(jsdoc_blocks, '@permission')
    return {
        "rule_id": "APITEST.ERRORCODE.01.001",
        "rule_description": "当API带有@permission标签时，检查API是否定义了在鉴权失败时抛出201错误码",
        "finding_description": f"[声明层检查] API 声明了 @permission {permission_val}，但 @throws 中未声明 201 错误码。",
        "evidence": [
            {"file": declaration_file, "line": 0, "snippet": f"@permission {permission_val} 声明存在，但 @throws 列表中缺少 201"}
        ],
        "component": "",
        "affected_apis": [api_declaration.split('(')[0].strip().split()[-1] if '(' in api_declaration else api_declaration],
        "modification_suggestion": f"在 @throws 中添加: @throws {{ BusinessError }} 201 - Permission denied.",
        "severity_level": "高",
        "affected_error_codes": "201",
    }


def check_rule_01_002(jsdoc_blocks, api_declaration, module_name, declaration_file):
    """规则 01.002: @systemapi 存在时，@throws 中必须声明 202。"""
    if not has_tag(jsdoc_blocks, '@systemapi'):
        return None  # 规则不适用

    throws_codes = extract_throws_codes(jsdoc_blocks)
    if '202' in throws_codes:
        return None  # 合规

    return {
        "rule_id": "APITEST.ERRORCODE.01.002",
        "rule_description": "当API带有@systemapi标签时，检查API实现中是否定义了在非系统应用调用系统API时抛出202错误码",
        "finding_description": f"[声明层检查] API 声明了 @systemapi，但 @throws 中未声明 202 错误码。",
        "evidence": [
            {"file": declaration_file, "line": 0, "snippet": "@systemapi 标签存在，但 @throws 列表中缺少 202"}
        ],
        "component": "",
        "affected_apis": [api_declaration.split('(')[0].strip().split()[-1] if '(' in api_declaration else api_declaration],
        "modification_suggestion": "在 @throws 中添加: @throws { BusinessError } 202 - Permission denied. A non-system application is not allowed to call a system API.",
        "severity_level": "高",
        "affected_error_codes": "202",
    }


def extract_since_suffix(since_raw):
    """从 @since 原始值中提取版本号之后的后缀文本。

    "24" → ""
    "24 dynamic" → "dynamic"
    "24 dynamic&static" → "dynamic&static"
    "6.1.1(24)" → ""
    "6.1.1(24) dynamic" → "dynamic"
    "26.0.0 dynamic&static" → "dynamic&static"
    "24 static" → "static"
    """
    if not since_raw:
        return ''
    # 剥离版本号部分：数字+点号（如 26.0.0）+ 可选括号格式（如 (24)）+ 前导空格
    suffix = re.sub(r'^[\d.]+(\([^)]*\))?\s*', '', since_raw)
    return suffix.strip()


# 需要检查的后缀白名单（动态调度 API）
_CHECKED_SUFFIXES = {'', 'dynamic', 'dynamic&static', 'dynamic@static'}


def check_rule_01_003(jsdoc_blocks, api_declaration, module_name, declaration_file):
    """规则 01.003: @since >= 24 且后缀为空/dynamic/dynamic&static 时，@throws 中不应显式列出 401。"""
    since_values = extract_all_tag_values(jsdoc_blocks, '@since')
    if not since_values:
        return None  # 无 @since 标签，规则不适用

    # 取最后一个 @since 的版本号
    last_since = since_values[-1]
    version = parse_since_version(last_since)

    if version < 24:
        return None  # 版本号 < 24，规则不适用

    # 后缀白名单过滤：仅检查空后缀、dynamic、dynamic&static
    suffix = extract_since_suffix(last_since)
    if suffix not in _CHECKED_SUFFIXES:
        return None  # 后缀不在白名单内（static、staticonly、dynamiconly 等），跳过

    throws_codes = extract_throws_codes(jsdoc_blocks)
    if '401' not in throws_codes:
        return None  # 合规

    return {
        "rule_id": "APITEST.ERRORCODE.01.003",
        "rule_description": "当新增API（since 版本号大于或等于\"6.1.1(24)\"或\"24\"）时，检查是否定义了401错误码，如果出现了则不符合规范",
        "finding_description": f"[声明层检查] API 的 @since 为 {last_since}（>= 24，后缀: {'无' if not suffix else suffix}），但 @throws 中显式列出了 401 错误码，不符合规范。",
        "evidence": [
            {"file": declaration_file, "line": 0, "snippet": f"@since {last_since} 版本 >= 24，@throws 中包含 401"}
        ],
        "component": "",
        "affected_apis": [api_declaration.split('(')[0].strip().split()[-1] if '(' in api_declaration else api_declaration],
        "modification_suggestion": f"移除 @throws 中的 401 错误码声明。@since {version} 及以上版本不应显式列出 401。",
        "severity_level": "中",
        "affected_error_codes": "401",
    }


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='声明层 JSDoc 规则检查（01.001/01.002/01.003）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''示例:
  python3 check_jsdoc_rules.py \\
    --js_sdk /path/to/interface_sdk-js \\
    --api_list /path/to/api.jsonl \\
    -o output
        ''',
    )
    parser.add_argument('--js_sdk', required=True, help='JS SDK 声明文件目录（interface_sdk-js）')
    parser.add_argument('--api_list', required=True, help='API 列表 JSONL 文件路径')
    parser.add_argument('-o', '--output', default='output', help='输出目录（默认: output）')
    args = parser.parse_args()

    js_sdk = Path(args.js_sdk)
    api_list_path = Path(args.api_list)

    if not js_sdk.is_dir():
        print(f"[Error] JS SDK directory not found: {args.js_sdk}", file=sys.stderr)
        sys.exit(1)
    if not api_list_path.exists():
        print(f"[Error] API list file not found: {args.api_list}", file=sys.stderr)
        sys.exit(1)

    # 加载 API 列表
    apis = []
    with open(api_list_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    apis.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"[Warning] Invalid JSON line: {line[:100]}", file=sys.stderr)

    print(f"[Step 1] Loaded {len(apis)} APIs from {api_list_path}")

    # 构建声明文件缓存
    decl_cache = {}
    sdk_api_dir = js_sdk / 'api' if (js_sdk / 'api').is_dir() else js_sdk

    # 规则检查
    findings = []
    checked = 0
    skipped_no_file = 0
    skipped_no_jsdoc = 0

    for api_entry in apis:
        api_declaration = api_entry.get('api_declaration', '')
        module_name = api_entry.get('module_name', '')
        declaration_file = api_entry.get('declaration_file', '')

        if not api_declaration or not declaration_file:
            continue

        # 定位声明文件
        if declaration_file not in decl_cache:
            # declaration_file 格式通常为 "api/@ohos.xxx.d.ts"
            decl_path = js_sdk / declaration_file
            if not decl_path.exists():
                # 尝试其他路径
                decl_path = sdk_api_dir / declaration_file.replace('api/', '')
            if decl_path.exists():
                try:
                    decl_cache[declaration_file] = decl_path.read_text(encoding='utf-8', errors='replace')
                except Exception:
                    decl_cache[declaration_file] = None
            else:
                decl_cache[declaration_file] = None

        content = decl_cache.get(declaration_file)
        if content is None:
            skipped_no_file += 1
            continue

        # 查找 API 对应的 JSDoc 块
        jsdoc_blocks = find_api_jsdoc(content, api_declaration)
        if jsdoc_blocks is None:
            # 回退：如果 js_doc 字段已提供，直接使用
            js_doc_raw = api_entry.get('js_doc', '') or api_entry.get('js doc', '')
            if js_doc_raw:
                # 将 js_doc 拆分为 JSDoc 块
                jsdoc_blocks = []
                for m in re.finditer(r'/\*\*[\s\S]*?\*/', js_doc_raw):
                    jsdoc_blocks.append(m.group())
            if not jsdoc_blocks:
                skipped_no_jsdoc += 1
                continue

        checked += 1

        # 执行三条规则检查
        for check_fn in [check_rule_01_001, check_rule_01_002, check_rule_01_003]:
            finding = check_fn(jsdoc_blocks, api_declaration, module_name, declaration_file)
            if finding:
                # 补充 component 字段
                impl_repo = api_entry.get('impl_repo_path', '')
                finding['component'] = impl_repo if impl_repo else module_name.replace('@ohos.', '').replace('.', '_')
                findings.append(finding)

    # 输出
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSONL 输出
    jsonl_file = out_dir / 'jsdoc_rule_findings.jsonl'
    with open(jsonl_file, 'w', encoding='utf-8') as f:
        for finding in findings:
            f.write(json.dumps(finding, ensure_ascii=False) + '\n')

    # JSON 输出（供合并用）
    json_file = out_dir / 'jsdoc_rule_findings.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({"findings": findings}, f, ensure_ascii=False, indent=2)

    # 统计
    print(f"\n[Done] Check complete")
    print(f"  APIs checked: {checked}")
    print(f"  Skipped (no declaration file): {skipped_no_file}")
    print(f"  Skipped (no JSDoc match): {skipped_no_jsdoc}")
    print(f"  Findings: {len(findings)}")
    print(f"  Output: {jsonl_file}")

    # 按规则统计
    rule_counts = {}
    for f in findings:
        rid = f['rule_id']
        rule_counts[rid] = rule_counts.get(rid, 0) + 1
    for rid, count in sorted(rule_counts.items()):
        print(f"    {rid}: {count} findings")


if __name__ == '__main__':
    main()
