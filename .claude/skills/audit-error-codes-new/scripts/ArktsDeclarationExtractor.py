from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd


@dataclass
class ArktsDeclaration:
    """单个函数声明的抽取结果"""
    function_name: str
    params: str
    return_type: str
    errors: Dict[str, str]
    raw_comment: str
    rel_file_path: str
    line_no: int
    issue: Optional[str] = None

    def to_dict(self) -> dict:
        # 对齐你的字段命名习惯
        return {
            "function_name": self.function_name,
            "params": self.params,
            "return_type": self.return_type,
            "errors": self.errors,
            "raw_comment": self.raw_comment,
            "rel_file_path": self.rel_file_path,
            "line_no": self.line_no,
            "issue": self.issue,
        }


class ArktsDeclarationExtractor:
    """
    专门用于提取 ArkTS 声明文件中带 JSDoc 的函数声明与方法签名
    支持 .d.ts 与 .ets
    """

    _THROWS_LINE = re.compile(r"^\s*@throws\s+\{\s*BusinessError\s*\}\s*(.*)\s*$")
    _TAG_LINE = re.compile(r"^\s*@\w+")
    _LINE_COMMENT = re.compile(r"^\s*//")
    _BLOCK_COMMENT_START = re.compile(r"^\s*/\*")
    _JS_DOC_START_INLINE = re.compile(r"/\*\*")
    _BLOCK_COMMENT_END_INLINE = re.compile(r"\*/")

    # JSDoc 后面若出现这些开头，说明不是函数签名，不绑定
    _NON_FUNCTION_START = re.compile(
        r"^\s*(declare\s+)?(namespace|interface|type|class|enum)\b"
        r"|^\s*(export\s+default)\b"
        r"|^\s*(import)\b"
        r"|^\s*(let|const|var)\b"
    )

    # 函数声明起始行
    _FUNCTION_START = re.compile(
        r"^\s*(export\s+)?(declare\s+)?function\s+[A-Za-z_\$][\w\$]*\s*(<[^>]*>)?\s*\(",
    )

    # 方法签名起始行，比如 set(value: T): Promise<void>;
    _METHOD_START = re.compile(
        r"^\s*[A-Za-z_\$][\w\$]*\s*\??\s*(<[^>]*>)?\s*\(",
    )

    # 属性箭头函数类型，例如 foo: (a: A) => R;
    _ARROW_PROP_START = re.compile(
        r"^\s*([A-Za-z_\$][\w\$]*)\s*\??\s*:\s*\(",
    )

    _MODIFIERS = {
        "export", "declare", "default",
        "public", "private", "protected",
        "static", "readonly", "abstract",
        "async",
    }

    def __init__(self, root_dir: str | Path, exts: Tuple[str, ...] = (".d.ts", ".ets")):
        self.root_dir = Path(root_dir).resolve()
        self.exts = exts

    def scan(self) -> List[ArktsDeclaration]:
        out: List[ArktsDeclaration] = []
        for p in self._iter_target_files():
            out.extend(self.scan_file(p))
        return out

    def _iter_target_files(self):
        for p in self.root_dir.rglob("*"):
            if not p.is_file():
                continue
            if any(p.name.endswith(ext) for ext in self.exts):
                yield p

    def scan_file(self, file_path: str | Path) -> List[ArktsDeclaration]:
        file_path = Path(file_path)
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        rel_path = self._rel_path(file_path)

        jsdoc_blocks = self._find_jsdoc_blocks(lines)

        decls: List[ArktsDeclaration] = []
        for (c_start, c_end) in jsdoc_blocks:
            raw_comment = "\n".join(lines[c_start:c_end + 1])

            sig_info = self._extract_function_signature_immediately_after(lines, c_end + 1)
            if sig_info is None:
                continue

            sig_text, sig_start_line = sig_info

            parsed = self._parse_signature(sig_text)
            if parsed is None:
                print(f"签名解析失败:{sig_text}")
                print(f"lines{lines}")
                print(f"rel_path{rel_path}")
                decls.append(
                    ArktsDeclaration(
                        function_name="",
                        params="",
                        return_type="",
                        errors={},
                        raw_comment=raw_comment,
                        rel_file_path=rel_path,
                        line_no=sig_start_line,
                        issue="签名解析失败",
                    )
                )
                continue

            fn_name, params, ret_type = parsed
            errors, issue = self._parse_throws(raw_comment)

            decls.append(
                ArktsDeclaration(
                    function_name=fn_name,
                    params=params,
                    return_type=ret_type,
                    errors=errors,
                    raw_comment=raw_comment,
                    rel_file_path=rel_path,
                    line_no=sig_start_line,
                    issue=issue,
                )
            )

        return decls

    def _rel_path(self, file_path: Path) -> str:
        try:
            return str(file_path.resolve().relative_to(self.root_dir))
        except Exception:
            return file_path.name

    def _find_jsdoc_blocks(self, lines: List[str]) -> List[Tuple[int, int]]:
        """
        找所有 /** ... */ 块注释，支持同一行闭合
        """
        blocks: List[Tuple[int, int]] = []
        in_jsdoc = False
        start = -1

        for i, line in enumerate(lines):
            if not in_jsdoc:
                if self._JS_DOC_START_INLINE.search(line):
                    in_jsdoc = True
                    start = i
                    if self._BLOCK_COMMENT_END_INLINE.search(line) and line.find("*/") > line.find("/**"):
                        blocks.append((start, i))
                        in_jsdoc = False
                        start = -1
            else:
                if self._BLOCK_COMMENT_END_INLINE.search(line):
                    blocks.append((start, i))
                    in_jsdoc = False
                    start = -1

        return blocks

    def _extract_function_signature_immediately_after(
            self, lines: List[str], start_idx: int
    ) -> Optional[Tuple[str, int]]:
        """
        只绑定紧邻的声明
        若 JSDoc 后面紧邻的语句不是函数或方法签名，直接返回 None
        """
        n = len(lines)
        i = start_idx

        # 跳过空行和 // 注释，跳过普通 /* ... */ 块注释
        while i < n:
            s = lines[i].strip()
            if not s:
                i += 1
                continue
            if self._LINE_COMMENT.match(s):
                i += 1
                continue
            if s.startswith("/*") and not s.startswith("/**"):
                i = self._skip_block_comment(lines, i)
                continue
            break

        if i >= n:
            return None

        first = lines[i]

        # 如果紧邻是 namespace 或 let/const 等，直接不绑定
        if self._NON_FUNCTION_START.match(first):
            return None

        # 判断是否可能是函数起始
        if not (self._FUNCTION_START.match(first) or self._METHOD_START.match(first) or self._ARROW_PROP_START.match(
                first)):
            return None

        # 拼接完整签名
        sig_start = i
        buf: List[str] = []
        paren = 0
        saw_open = False

        while i < n:
            line = lines[i]
            buf.append(line)

            for ch in line:
                if ch == "(":
                    paren += 1
                    saw_open = True
                elif ch == ")":
                    paren = max(paren - 1, 0)

            joined = "\n".join(buf)

            # 必须在合理范围内尽快看到 '('
            if not saw_open and len(buf) >= 3:
                return None

            if saw_open and paren == 0:
                # 声明文件通常以 ; 结束
                if ";" in line:
                    sig_text = joined[: joined.find(";") + 1]
                    return sig_text, sig_start + 1
                # .ets 里可能有实现体
                if "{" in line:
                    sig_text = joined[: joined.find("{")].rstrip()
                    return sig_text, sig_start + 1

            # 保险上限
            if len(joined) > 20000:
                return None

            i += 1

        return None

    @staticmethod
    def _skip_block_comment(lines: List[str], idx: int) -> int:
        n = len(lines)
        i = idx
        while i < n:
            if "*/" in lines[i]:
                return i + 1
            i += 1
        return n

    def _parse_signature(self, sig: str) -> Optional[Tuple[str, str, str]]:
        """
        兼容以下形态
        1) attributeNames<T extends keyof X>(callback: ...): void;
        2) attributeNames<T extends keyof X>(): Promise<Array<T>>;
        3) attributeValue<T extends keyof X>(\n ... \n): void;
        4) function enableAbility(...): Promise<void>;
        5) set(value: T): Promise<void>;
        """
        s = sig.strip()

        m_arrow = re.match(
            r"^\s*([A-Za-z_\$][\w\$]*)\s*\??\s*:\s*\((.*)\)\s*=>\s*([^;{]+)\s*;?\s*$",
            s,
            flags=re.DOTALL,
        )
        if m_arrow:
            name = m_arrow.group(1).strip()
            params = self._collapse_ws(m_arrow.group(2))
            ret_type = self._collapse_ws(m_arrow.group(3))
            return name, params, ret_type

        # B) constructor(...)
        if re.match(r"^\s*constructor\s*\(", s):
            open_idx = s.find("(")
            close_idx = self._find_matching_paren(s, open_idx)
            if close_idx is None:
                return None
            params = self._collapse_ws(s[open_idx + 1:close_idx])
            return "constructor", params, "void"

        # C) 常规 function 或方法签名
        open_idx = s.find("(")
        if open_idx < 0:
            return None

        head = s[:open_idx].strip()

        tokens = [t for t in re.split(r"\s+", head) if t]
        cleaned: List[str] = []
        for t in tokens:
            if t in self._MODIFIERS:
                continue
            cleaned.append(t)
        head2 = " ".join(cleaned).strip()

        head2 = re.sub(r"^\s*function\s+", "", head2).strip()

        before_generic, _generic = self._strip_trailing_ts_generic(head2)
        name = self._extract_identifier_at_end(before_generic)
        if not name:
            return None

        close_idx = self._find_matching_paren(s, open_idx)
        if close_idx is None:
            return None

        params_raw = s[open_idx + 1:close_idx]
        params = self._collapse_ws(params_raw)

        tail = s[close_idx + 1:].strip()
        m_ret = re.search(r"^\s*:\s*([^;{]+)", tail, flags=re.DOTALL)
        ret_type = self._collapse_ws(m_ret.group(1)) if m_ret else "any"

        return name, params, ret_type
    @staticmethod
    def _extract_identifier_at_end(s: str) -> Optional[str]:
        """
        从字符串末尾提取 TS 标识符，允许可选的 '?'
        """
        m = re.search(r"([A-Za-z_\$][\w\$]*)\s*\??\s*$", s)
        if not m:
            return None
        return m.group(1)

    @staticmethod
    def _strip_trailing_ts_generic(head: str) -> Tuple[str, str]:
        """
        从 head 末尾剥离 TypeScript 泛型块，例如:
        "attributeValue<T extends keyof X>" -> ("attributeValue", "<T extends keyof X>")
        若没有泛型则返回 (head, "")
        支持简单嵌套: Array<Map<K,V>> 这种会被当作整体处理
        """
        s = head.rstrip()
        if not s.endswith(">"):
            return s, ""

        depth = 0
        i = len(s) - 1
        while i >= 0:
            ch = s[i]
            if ch == ">":
                depth += 1
            elif ch == "<":
                depth -= 1
                if depth == 0:
                    generic = s[i:].strip()
                    before = s[:i].rstrip()
                    return before, generic
            i -= 1

        return s, ""

    @staticmethod
    def _find_matching_paren(s: str, open_idx: int) -> Optional[int]:
        depth = 0
        for i in range(open_idx, len(s)):
            ch = s[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
        return None

    def _parse_throws(self, raw_comment: str) -> Tuple[Dict[str, str], Optional[str]]:
        inner_lines = self._normalize_jsdoc_lines(raw_comment)

        errors: Dict[str, str] = {}
        issues: List[str] = []

        saw_throws = False
        saw_code_without_msg = False
        saw_msg_without_code = False

        i = 0
        n = len(inner_lines)

        while i < n:
            line = inner_lines[i].rstrip()
            m = self._THROWS_LINE.match(line)
            if not m:
                i += 1
                continue

            saw_throws = True
            tail = (m.group(1) or "").strip()

            code: Optional[str] = None
            msg: str = ""

            m1 = re.match(r"^([+-]?\d+)\s*-\s*(.*)$", tail)
            if m1:
                code = m1.group(1).strip()
                msg = (m1.group(2) or "").strip()
            else:
                # 2) 201 Permission verification failed.
                m1b = re.match(r"^([+-]?\d+)\s+(.+)$", tail)
                if m1b:
                    code = m1b.group(1).strip()
                    msg = (m1b.group(2) or "").strip()
                else:
                    # 3) - return error message
                    m2 = re.match(r"^-\s*(.*)$", tail)
                    if m2:
                        msg = (m2.group(1) or "").strip()
                    else:
                        # 4) 0
                        m3 = re.match(r"^([+-]?\d+)\s*$", tail)
                        if m3:
                            code = m3.group(1).strip()
                            msg = ""
                        else:
                            # 5) 极端形态，全部当 message
                            msg = tail

            # 续行拼接，直到下一个 tag 或结束
            j = i + 1
            cont: List[str] = []
            while j < n:
                nxt = inner_lines[j].rstrip()
                if self._TAG_LINE.match(nxt):
                    break
                if nxt.strip():
                    cont.append(nxt.strip())
                j += 1

            if cont:
                msg = (msg + " " + " ".join(cont)).strip() if msg else " ".join(cont).strip()

            msg = self._collapse_ws(msg)

            if code is not None:
                if not msg:
                    msg = "no message"
                    saw_code_without_msg = True
                errors[code] = msg
            else:
                if msg:
                    saw_msg_without_code = True
                    errors[msg] = "no error code"
                else:
                    saw_msg_without_code = True
                    errors["unknown error"] = "no error code"

            i = j

        if not saw_throws:
            issues.append("未声明任何异常")
        if saw_code_without_msg:
            issues.append("无错误信息-有错误码")
        if saw_msg_without_code:
            issues.append("有错误信息-无错误码")

        issue = "；".join(issues) if issues else None
        return errors, issue

    @staticmethod
    def _normalize_jsdoc_lines(raw_comment: str) -> List[str]:
        lines = raw_comment.splitlines()

        # 去掉最外层 /** 与 */
        if lines and "/**" in lines[0]:
            lines = lines[1:]
        if lines and "*/" in lines[-1]:
            lines = lines[:-1]

        cleaned: List[str] = []
        for ln in lines:
            ln2 = ln.strip()
            if ln2.startswith("*"):
                ln2 = ln2[1:].lstrip()
            cleaned.append(ln2)
        return cleaned

    @staticmethod
    def _collapse_ws(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()


def dump_json(decls: List[ArktsDeclaration]) -> str:
    return json.dumps([d.to_dict() for d in decls], ensure_ascii=False, indent=2)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="ArkTS 声明提取器 - 从 .d.ts 和 .ets 文件中提取带 JSDoc 的函数声明",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 扫描指定目录，输出到默认文件
  python ArktsDeclarationExtractor.py kits/accessibility/interfaces

  # 指定输出文件
  python ArktsDeclarationExtractor.py kits/accessibility/interfaces -o output.csv -j output.json

  # 自定义文件扩展名
  python ArktsDeclarationExtractor.py kits/accessibility/interfaces -e .d.ts .ets
        """
    )

    parser.add_argument(
        "input_dir",
        help="输入目录路径（包含 .d.ts 或 .ets 文件）"
    )

    parser.add_argument(
        "-o", "--output",
        dest="csv_output",
        help="输出 CSV 文件路径（默认: test.csv）",
        default="test.csv"
    )

    parser.add_argument(
        "-j", "--json",
        dest="json_output",
        help="输出 JSON 文件路径（默认: decls_full.json）",
        default="decls_full.json"
    )

    parser.add_argument(
        "-e", "--exts",
        dest="extensions",
        nargs="+",
        help="要处理的文件扩展名（默认: .d.ts .ets）",
        default=[".d.ts", ".ets"]
    )

    args = parser.parse_args()

    # 创建提取器
    extractor = ArktsDeclarationExtractor(args.input_dir, exts=tuple(args.extensions))

    # 扫描文件
    print(f"正在扫描目录: {args.input_dir}")
    decls = extractor.scan()

    # 分类数据
    csv_data = []
    issues = dict()
    for decl in decls:
        if decl.issue:
            if issues.get(decl.issue):
                issues[decl.issue].append(decl)
            else:
                issues[decl.issue] = [decl]
        csv_data.append({
            'function_name': decl.function_name,
            'errors': decl.errors,
            'issue': decl.issue,
            'line_no': decl.line_no,
            'file_path': decl.rel_file_path,
            'params': decl.params,
            'raw_comment': decl.raw_comment,
            'return_type': decl.return_type,
        })

    # 保存 CSV
    df = pd.DataFrame(csv_data)
    df.to_csv(args.csv_output, index=False, encoding='utf-8')
    print(f"CSV 已保存至: {args.csv_output}")

    # 保存 JSON
    content = json.dumps([d.to_dict() for d in decls], ensure_ascii=False, indent=2) + "\n"
    with open(args.json_output, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"JSON 已保存至: {args.json_output}")

    # 打印统计
    print(f"\n{'=' * 60}")
    print(f"扫描完成统计")
    print(f"{'=' * 60}")
    print(f"总计 API 数: {len(decls)}")
    if issues:
        print(f"\n问题 API 分类:")
        for issue, items in issues.items():
            print(f"  - {issue}: {len(items)} 个")
    else:
        print("\n未发现问题 API")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()