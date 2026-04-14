#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JS/NAPI API 提取器
从 HarmonyOS/OpenHarmony Kit 中提取 JS/NAPI 层的 API 声明和实现
"""

import os
import re
import json
import argparse
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from pathlib import Path


@dataclass
class NapiApi:
    """NAPI API 信息"""
    js_name: str
    napi_func: str
    is_async: Optional[bool]  # True=async, False=sync, None=regular
    file: str
    line: int
    napi_code: str = ""


@dataclass
class NapiModule:
    """NAPI 模块信息"""
    module_name: str
    entry_file: str
    entry_line: int
    init_func: str
    helper_apis: List[NapiApi] = field(default_factory=list)
    instance_apis: List[NapiApi] = field(default_factory=list)
    properties: List[Dict] = field(default_factory=list)
    # 用于去重的集合
    _api_keys: set = field(default_factory=set)

    def add_api(self, api: NapiApi, is_helper: bool = False):
        """添加 API（自动去重）"""
        # 使用 js_name + napi_func 作为唯一键
        key = (api.js_name, api.napi_func)
        if key in self._api_keys:
            return False
        self._api_keys.add(key)
        if is_helper:
            self.helper_apis.append(api)
        else:
            self.instance_apis.append(api)
        return True

    def add_property(self, prop: Dict):
        """添加属性（自动去重）"""
        key = ('prop', prop.get('name'))
        if key in self._api_keys:
            return False
        self._api_keys.add(key)
        self.properties.append(prop)
        return True


class JsNapiApiExtractor:
    """JS/NAPI API 提取器"""

    # 匹配模块名（支持直接字符串或宏定义）
    PATTERN_MODULE_NAME = re.compile(r'\.nm_modname\s*=\s*([^\s,]+)')

    # 匹配 Init 函数
    PATTERN_INIT_FUNC = re.compile(r'\.nm_register_func\s*=\s*(\w+)')

    # 匹配 napi_module_register 行
    PATTERN_MODULE_REGISTER = re.compile(r'napi_module_register')

    # 匹配 DECLARE_NAPI_FUNCTION_WITH_DATA (异步/同步版本，支持字符串或宏)
    PATTERN_NAPI_FUNC_DATA = re.compile(
        r'DECLARE_NAPI_FUNCTION_WITH_DATA\s*\(\s*([^\s,]+)\s*,\s*([\w:]+)\s*,\s*(\w+)\s*\)'
    )

    # 匹配 DECLARE_NAPI_FUNCTION (普通函数，支持字符串或宏)
    PATTERN_NAPI_FUNC = re.compile(
        r'DECLARE_NAPI_FUNCTION\s*\(\s*([^\s,]+)\s*,\s*([\w:]+)\s*\)'
    )

    # 匹配 DECLARE_NAPI_STATIC_FUNCTION (静态函数，支持字符串或宏)
    PATTERN_NAPI_STATIC_FUNC = re.compile(
        r'DECLARE_NAPI_STATIC_FUNCTION\s*\(\s*([^\s,]+)\s*,\s*([\w:]+)\s*\)'
    )

    # 匹配 DECLARE_WRITABLE_NAPI_FUNCTION (可写函数，支持字符串或宏)
    PATTERN_WRITABLE_NAPI_FUNC = re.compile(
        r'DECLARE_WRITABLE_NAPI_FUNCTION\s*\(\s*([^\s,]+)\s*,\s*([\w:]+)\s*\)'
    )

    # 匹配 DECLARE_NAPI_PROPERTY
    PATTERN_NAPI_PROPERTY = re.compile(
        r'DECLARE_NAPI_PROPERTY\s*\(\s*"([^"]+)"\s*,'
    )

    # 匹配 NAPI 函数定义 (支持多级嵌套类名，如 ClassName::NestedClass::MethodName)
    PATTERN_NAPI_FUNC_DEF = re.compile(
        r'napi_value\s+([\w:]+)\s*\(\s*napi_env\s+\w+\s*,\s*napi_callback_info\s+\w+\s*\)'
    )

    # 匹配静态成员函数定义（支持多级嵌套类名）
    # 格式：napi_value OuterClass::InnerClass::...::MethodName(napi_env
    PATTERN_STATIC_FUNC_DEF = re.compile(
        r'(?:static\s+)?napi_value\s+([\w:]+)\s*\(\s*napi_env'
    )

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.modules: List[NapiModule] = []

    def extract_all(self) -> Dict:
        """提取所有 NAPI API"""
        # 1. 查找 NAPI 入口文件
        entry_files = self._find_napi_entry_files()

        # 2. 解析每个入口文件
        for entry_file in entry_files:
            self._parse_entry_file(entry_file)

        return self._to_dict()

    def _find_napi_entry_files(self) -> List[Path]:
        """查找所有 NAPI 入口文件"""
        entry_files = []

        for cpp_file in self.root_path.rglob("*.cpp"):
            if self._is_napi_entry_file(cpp_file):
                entry_files.append(cpp_file)

        return entry_files

    def _is_napi_entry_file(self, cpp_file: Path) -> bool:
        """判断是否是 NAPI 入口文件"""
        try:
            content = cpp_file.read_text(encoding='utf-8', errors='ignore')
            return 'napi_module_register' in content and 'nm_modname' in content
        except:
            return False

    def _parse_entry_file(self, entry_file: Path):
        """解析 NAPI 入口文件"""
        try:
            content = entry_file.read_text(encoding='utf-8', errors='ignore')
        except:
            return

        relative_path = str(entry_file.relative_to(self.root_path))

        # 提取模块名（可能是字符串字面量或宏定义）
        module_match = self.PATTERN_MODULE_NAME.search(content)
        if not module_match:
            return
        module_name_raw = module_match.group(1).strip()

        # 如果是字符串字面量，去掉引号
        if module_name_raw.startswith('"') and module_name_raw.endswith('"'):
            module_name = module_name_raw[1:-1]
        else:
            # 是宏定义，需要查找其值
            module_name = self._resolve_macro_value(content, module_name_raw)
            if not module_name:
                module_name = module_name_raw  # 找不到定义就保留宏名

        # 检查是否已经存在同名模块
        existing_module = None
        for m in self.modules:
            if m.module_name == module_name:
                existing_module = m
                break

        # 提取 Init 函数名
        init_match = self.PATTERN_INIT_FUNC.search(content)
        init_func = init_match.group(1) if init_match else "Init"

        # 提取 napi_module_register 行号
        entry_line = 0
        for i, line in enumerate(content.split('\n'), 1):
            if self.PATTERN_MODULE_REGISTER.search(line):
                entry_line = i
                break

        if existing_module:
            # 模块已存在，合并 API
            module = existing_module
        else:
            # 创建新模块
            module = NapiModule(
                module_name=module_name,
                entry_file=relative_path,
                entry_line=entry_line,
                init_func=init_func
            )
            self.modules.append(module)

        # 查找该模块下的所有 NAPI 文件
        # 从入口文件所在模块目录提取（向上找到模块根目录）
        module_dir = self._find_module_root_dir(entry_file)

        # 提取该文件的宏定义映射
        macro_map = self._extract_macro_definitions(content)

        self._extract_apis_from_dir(module_dir, module, macro_map)

    def _find_module_root_dir(self, entry_file: Path) -> Path:
        """找到模块的根目录（包含 src 的目录）"""
        # 从入口文件向上找到包含 src 的目录
        current = entry_file.parent
        while current != current.parent:
            if current.name == 'src':
                return current.parent
            # 检查当前目录下是否有 src
            if (current / 'src').exists():
                return current
            current = current.parent
        return entry_file.parent

    def _resolve_macro_value(self, content: str, macro_name: str) -> Optional[str]:
        """解析宏定义的值"""
        # 匹配 constexpr const char *NAME = "value" 或 const char *NAME = "value"
        pattern = re.compile(
            r'(?:constexpr\s+)?(?:const\s+)?char\s*\*?\s*' + re.escape(macro_name) +
            r'\s*=\s*"([^"]+)"'
        )
        match = pattern.search(content)
        if match:
            return match.group(1)
        return None

    def _extract_macro_definitions(self, content: str) -> Dict[str, str]:
        """提取文件中所有的宏定义（字符串常量）"""
        macro_map = {}

        # 匹配 constexpr const char *NAME = "value" 格式
        pattern = re.compile(
            r'(?:constexpr\s+)?(?:const\s+)?char\s*\*?\s*(\w+)\s*=\s*"([^"]+)"'
        )
        for match in pattern.finditer(content):
            macro_map[match.group(1)] = match.group(2)

        # 匹配 static constexpr const char *NAME = "value" 格式（类静态成员）
        pattern_static = re.compile(
            r'static\s+constexpr\s+const\s+char\s*\*\s*(\w+)\s*=\s*"([^"]+)"'
        )
        for match in pattern_static.finditer(content):
            macro_map[match.group(1)] = match.group(2)

        # 匹配 #define NAME "value" 格式
        pattern_define = re.compile(r'#define\s+(\w+)\s+"([^"]+)"')
        for match in pattern_define.finditer(content):
            macro_map[match.group(1)] = match.group(2)

        # 匹配 constexpr const char *NAME = "value" 格式（带命名空间或类前缀）
        pattern_ns = re.compile(
            r'(?:constexpr\s+)?(?:const\s+)?char\s*\*?\s*[\w:]+::(\w+)\s*=\s*"([^"]+)"'
        )
        for match in pattern_ns.finditer(content):
            macro_map[match.group(1)] = match.group(2)

        # 匹配类内的 static constexpr const char *NAME = "value" 格式
        # 需要从类定义中提取，格式如：class ClassName { ... static constexpr const char* NAME = "value"; ... };
        pattern_class_member = re.compile(
            r'static\s+constexpr\s+const\s+char\s*\*\s*(\w+)\s*=\s*"([^"]+)"'
        )
        for match in pattern_class_member.finditer(content):
            macro_map[match.group(1)] = match.group(2)

        return macro_map

    def _extract_apis_from_dir(self, napi_dir: Path, module: NapiModule, macro_map: Dict[str, str] = None):
        """从目录中提取所有 API"""
        if macro_map is None:
            macro_map = {}

        # 首先从头文件中提取所有宏定义
        for header_file in napi_dir.rglob("*.h"):
            try:
                content = header_file.read_text(encoding='utf-8', errors='ignore')
                file_macros = self._extract_macro_definitions(content)
                macro_map.update(file_macros)
            except:
                pass

        # 查找目录下所有 cpp 文件
        for cpp_file in napi_dir.rglob("*.cpp"):
            # 不跳过入口文件，因为入口文件中也可能有 API 声明（如 createKVManager）
            self._extract_apis_from_file(cpp_file, module, macro_map)

    def _extract_apis_from_file(self, cpp_file: Path, module: NapiModule, macro_map: Dict[str, str] = None):
        """从文件中提取 API"""
        if macro_map is None:
            macro_map = {}

        try:
            content = cpp_file.read_text(encoding='utf-8', errors='ignore')
        except:
            return

        relative_path = str(cpp_file.relative_to(self.root_path))
        lines = content.split('\n')

        # 提取当前文件的宏定义并合并
        file_macros = self._extract_macro_definitions(content)
        combined_macros = {**macro_map, **file_macros}

        # 提取 NAPI 函数代码
        napi_func_codes = self._extract_napi_func_codes(content)

        # 判断是否是 helper 文件
        is_helper = 'helper' in str(cpp_file).lower() or 'Helper' in str(cpp_file)

        for i, line in enumerate(lines, 1):
            # 匹配 DECLARE_NAPI_FUNCTION_WITH_DATA
            match = self.PATTERN_NAPI_FUNC_DATA.search(line)
            if match:
                js_name_raw = match.group(1)
                napi_func = match.group(2)
                data_type = match.group(3).upper()

                # 解析 js_name（可能是字符串或宏）
                js_name = self._resolve_js_name(js_name_raw, combined_macros)

                # 判断是同步还是异步
                is_async = None
                if data_type == 'ASYNC':
                    is_async = True
                elif data_type == 'SYNC':
                    is_async = False

                # 获取 NAPI 函数代码
                napi_code = napi_func_codes.get(napi_func, "")

                api = NapiApi(
                    js_name=js_name,
                    napi_func=napi_func,
                    is_async=is_async,
                    file=relative_path,
                    line=i,
                    napi_code=napi_code[:1000]  # 限制长度
                )

                module.add_api(api, is_helper)
                continue

            # 匹配 DECLARE_NAPI_FUNCTION
            match = self.PATTERN_NAPI_FUNC.search(line)
            if match:
                js_name_raw = match.group(1)
                napi_func = match.group(2)

                # 解析 js_name（可能是字符串或宏）
                js_name = self._resolve_js_name(js_name_raw, combined_macros)

                # 获取 NAPI 函数代码
                napi_code = napi_func_codes.get(napi_func, "")

                # 根据 js_name 是否以 Sync 结尾来判断是否是同步函数
                is_async = False if js_name.endswith('Sync') else None

                api = NapiApi(
                    js_name=js_name,
                    napi_func=napi_func,
                    is_async=is_async,
                    file=relative_path,
                    line=i,
                    napi_code=napi_code[:1000]
                )

                module.add_api(api, is_helper)
                continue

            # 匹配 DECLARE_NAPI_STATIC_FUNCTION
            match = self.PATTERN_NAPI_STATIC_FUNC.search(line)
            if match:
                js_name_raw = match.group(1)
                napi_func = match.group(2)

                # 解析 js_name（可能是字符串或宏）
                js_name = self._resolve_js_name(js_name_raw, combined_macros)

                # 获取 NAPI 函数代码
                napi_code = napi_func_codes.get(napi_func, "")

                # 静态函数根据 js_name 是否以 Sync 结尾来判断是否是同步函数
                is_async = False if js_name.endswith('Sync') else None

                api = NapiApi(
                    js_name=js_name,
                    napi_func=napi_func,
                    is_async=is_async,
                    file=relative_path,
                    line=i,
                    napi_code=napi_code[:1000]
                )

                module.add_api(api, is_helper)
                continue

            # 匹配 DECLARE_WRITABLE_NAPI_FUNCTION
            match = self.PATTERN_WRITABLE_NAPI_FUNC.search(line)
            if match:
                js_name_raw = match.group(1)
                napi_func = match.group(2)

                # 解析 js_name（可能是字符串或宏）
                js_name = self._resolve_js_name(js_name_raw, combined_macros)

                # 获取 NAPI 函数代码
                napi_code = napi_func_codes.get(napi_func, "")

                # 根据 js_name 是否以 Sync 结尾来判断是否是同步函数
                is_async = False if js_name.endswith('Sync') else None

                api = NapiApi(
                    js_name=js_name,
                    napi_func=napi_func,
                    is_async=is_async,
                    file=relative_path,
                    line=i,
                    napi_code=napi_code[:1000]
                )

                module.add_api(api, is_helper)
                continue

            # 匹配 DECLARE_NAPI_PROPERTY
            match = self.PATTERN_NAPI_PROPERTY.search(line)
            if match:
                prop_name_raw = match.group(1)
                prop_name = self._resolve_js_name(prop_name_raw, combined_macros)
                module.add_property({
                    "name": prop_name,
                    "file": relative_path,
                    "line": i
                })

    def _resolve_js_name(self, name_raw: str, macro_map: Dict[str, str]) -> str:
        """解析 js_name，可能是字符串字面量或宏定义"""
        name_raw = name_raw.strip()

        # 如果是字符串字面量
        if name_raw.startswith('"') and name_raw.endswith('"'):
            return name_raw[1:-1]

        # 如果是宏定义，查找其值
        if name_raw in macro_map:
            return macro_map[name_raw]

        # 处理 ClassName::MACRO_NAME 格式 - 提取 MACRO_NAME 部分再查找
        if '::' in name_raw:
            macro_name = name_raw.split('::')[-1]
            if macro_name in macro_map:
                return macro_map[macro_name]

        # 找不到定义，返回原始名称
        return name_raw

    def _extract_napi_func_codes(self, content: str) -> Dict[str, str]:
        """提取所有 NAPI 函数代码"""
        func_codes = {}

        for match in self.PATTERN_NAPI_FUNC_DEF.finditer(content):
            func_name = match.group(1)
            func_start = match.start()

            # 提取函数体
            func_body = self._extract_function_body(content, func_start)
            if func_body:
                func_codes[func_name] = func_body

        # 处理多级嵌套类名函数定义
        for match in self.PATTERN_STATIC_FUNC_DEF.finditer(content):
            full_name = match.group(1)  # 完整的函数名，如 ConnectionModule::NetConnectionInterface::On
            func_start = match.start()

            func_body = self._extract_function_body(content, func_start)
            if func_body:
                func_codes[full_name] = func_body

                # 分割名称，生成各种可能的简称
                # 例如：ConnectionModule::NetConnectionInterface::On
                # 生成：On, NetConnectionInterface::On, ConnectionModule::NetConnectionInterface::On
                parts = full_name.split('::')
                if len(parts) >= 2:
                    # 存储方法名
                    method_name = parts[-1]
                    func_codes[method_name] = func_body

                    # 存储各种部分名称组合
                    for i in range(len(parts) - 1):
                        partial_name = '::'.join(parts[i:])
                        func_codes[partial_name] = func_body

        return func_codes

    def _extract_function_body(self, content: str, start: int) -> str:
        """提取函数体"""
        # 找到函数开始的 {
        brace_start = content.find('{', start)
        if brace_start == -1:
            return ""

        # 匹配 {} 对
        brace_count = 1
        pos = brace_start + 1
        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1

        return content[brace_start:pos]

    def _to_dict(self) -> Dict:
        """转换为字典"""
        total_helper_apis = sum(len(m.helper_apis) for m in self.modules)
        total_instance_apis = sum(len(m.instance_apis) for m in self.modules)
        total_properties = sum(len(m.properties) for m in self.modules)

        return {
            "metadata": {
                "root_path": str(self.root_path),
                "module_count": len(self.modules),
                "total_helper_apis": total_helper_apis,
                "total_instance_apis": total_instance_apis,
                "total_properties": total_properties,
                "total_apis": total_helper_apis + total_instance_apis
            },
            "modules": [
                {
                    "module_name": m.module_name,
                    "entry_file": m.entry_file,
                    "entry_line": m.entry_line,
                    "init_func": m.init_func,
                    "helper_api_count": len(m.helper_apis),
                    "instance_api_count": len(m.instance_apis),
                    "property_count": len(m.properties),
                    "helper_apis": [asdict(a) for a in m.helper_apis],
                    "instance_apis": [asdict(a) for a in m.instance_apis],
                    "properties": m.properties
                }
                for m in self.modules
            ]
        }

    def print_summary(self):
        """打印摘要"""
        print("=" * 60)
        print("JS/NAPI API 提取结果")
        print("=" * 60)

        total_helper = sum(len(m.helper_apis) for m in self.modules)
        total_instance = sum(len(m.instance_apis) for m in self.modules)
        total_props = sum(len(m.properties) for m in self.modules)

        print(f"模块数量: {len(self.modules)}")
        print(f"Helper API: {total_helper} 个")
        print(f"Instance API: {total_instance} 个")
        print(f"属性: {total_props} 个")
        print(f"总计: {total_helper + total_instance + total_props} 个")

        for m in self.modules:
            print(f"\n模块: {m.module_name}")
            print(f"  入口: {m.entry_file}:{m.entry_line}")
            print(f"  Helper API: {len(m.helper_apis)} 个")
            print(f"  Instance API: {len(m.instance_apis)} 个")

            # 显示前5个 API
            all_apis = m.helper_apis + m.instance_apis
            for api in all_apis[:5]:
                async_str = "async" if api.is_async else ("sync" if api.is_async is False else "regular")
                print(f"    {api.js_name} ({async_str}) -> {api.napi_func}")
            if len(all_apis) > 5:
                print(f"    ... 还有 {len(all_apis) - 5} 个")

        print("=" * 60)

    def export_json(self, output_path: str):
        """导出为 JSON"""
        data = self._to_dict()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ JSON 已导出: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="JS/NAPI API 提取器 - 从 Kit 中提取 JS/NAPI 层 API"
    )
    parser.add_argument("component_path", help="部件目录路径（如 DataBases/communication_netmanager_base）")
    parser.add_argument("-o", "--output", default="js_napi_api.json", help="输出文件路径")

    args = parser.parse_args()

    print(f"🔍 分析目录: {args.component_path}")

    extractor = JsNapiApiExtractor(args.component_path)
    extractor.extract_all()
    extractor.print_summary()
    extractor.export_json(args.output)


if __name__ == "__main__":
    main()
