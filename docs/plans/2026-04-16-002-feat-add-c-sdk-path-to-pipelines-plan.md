---
title: "feat: 流水线添加 c_sdk_path 参数支持"
type: feat
status: active
date: 2026-04-16
---

# feat: 流水线添加 c_sdk_path 参数支持

## Overview

kit-api-extract 技能的 SKILL.md 已支持 `c_sdk_path` 参数，但现有流水线脚本（scan_kit.py、batch_scan_all.py）和全局配置（scan_config.json）尚未集成此参数。本次变更将 `c_decl_path`（C SDK 路径）添加到所有流水线层级，使 C API 提取功能可以自动启用。

C SDK 路径：`/Users/spongbob/for_guance/api_dfx/api/interface_sdk_c`

## Problem Frame

kit-api-extract 技能在 SKILL.md 中已定义 `c_sdk_path` 可选参数，`extract_kit_api.py` 脚本也支持 `--c_decl_repo` / `-c` 参数。但流水线中间层（scan_kit.py、batch_scan_all.py）不传递此参数，导致 C API 提取功能在批量运行时无法使用。

## Requirements Trace

- R1. `scan_config.json` 添加 `c_decl_path` 字段，默认指向 `/Users/spongbob/for_guance/api_dfx/api/interface_sdk_c`
- R2. `scripts/common/config.py` 默认值添加 `c_decl_path`
- R3. `scripts/kit-scan/scan_kit.py` 添加 `-c_decl_path` 参数，传递到 kit-api-extract prompt
- R4. `scripts/kit-scan/batch_scan_all.py` 加载并传递 `c_decl_path` 到 scan_kit.py
- R5. `scripts/kit-scan-test/scan_kit.py` 同 R3
- R6. `scripts/kit-scan-test/batch_scan_all.py` 同 R4

## Scope Boundaries

- 不修改 SKILL.md（已支持 c_sdk_path）
- 不修改 `extract_kit_api.py`（已支持 `-c` 参数）
- 不修改 `component-scan` 目录（该流水线不使用 kit-api-extract 技能）

## Context & Research

### Relevant Code and Patterns

- 参数传递链路：`scan_config.json` → `batch_scan_all.py` → `scan_kit.py` → `claude_runner.py` → SKILL.md prompt → `extract_kit_api.py -c`
- `js_decl_path` 的传递模式即为参考范本：config 加载 → 全局变量 → CLI 参数 → build_command/build_extract_prompt

### 参数名映射

| 层级 | JS SDK 参数名 | C SDK 参数名 |
|------|-------------|-------------|
| scan_config.json | `js_decl_path` | `c_decl_path`（新增） |
| config.py 默认值 | `js_decl_path` | `c_decl_path`（新增） |
| scan_kit.py CLI | `-js_decl_path` | `-c_decl_path`（新增） |
| SKILL.md prompt | `js_sdk_path` | `c_sdk_path` |
| extract_kit_api.py CLI | `-js` | `-c` |

## Key Technical Decisions

- **CLI 参数名选择 `c_decl_path`**：与 `js_decl_path` 命名风格一致，保持流水线内部的统一性
- **可选参数**：`c_decl_path` 为可选，未提供时 kit-api-extract 仅处理 JS API，向后兼容
- **路径验证**：仅在提供了 `c_decl_path` 时验证路径存在性

## Implementation Units

- [x] **Unit 1: 更新全局配置和默认值**

**Goal:** 在 scan_config.json 和 config.py 中添加 c_decl_path 字段

**Requirements:** R1, R2

**Dependencies:** None

**Files:**
- Modify: `scripts/scan_config.json`
- Modify: `scripts/common/config.py`

**Approach:**
- scan_config.json 添加 `"c_decl_path": "/Users/spongbob/for_guance/api_dfx/api/interface_sdk_c"`
- config.py 的 `_DEFAULTS` 字典添加 `"c_decl_path": ""`

**Test scenarios:**
- Test expectation: none — 配置变更，通过后续单元集成测试覆盖

**Verification:**
- config.py 的 `_DEFAULTS` 包含 `c_decl_path` 键
- `load_config()` 返回的字典包含配置文件中的 `c_decl_path` 值

- [x] **Unit 2: kit-scan 流水线添加 c_decl_path 传递**

**Goal:** scan_kit.py 和 batch_scan_all.py 支持 c_decl_path 参数

**Requirements:** R3, R4

**Dependencies:** Unit 1

**Files:**
- Modify: `scripts/kit-scan/scan_kit.py`
- Modify: `scripts/kit-scan/batch_scan_all.py`

**Approach:**
- scan_kit.py:
  - `parse_args()` 添加 `-c_decl_path` 可选参数
  - `build_extract_prompt()` 增加 `c_sdk_path` 可选参数，有值时追加到 prompt
  - `main()` 中读取 args.c_decl_path 并传入 build_extract_prompt
  - 路径验证：仅当提供了 c_decl_path 时检查路径存在性
  - 打印信息增加 C SDK 路径（如果提供）
- batch_scan_all.py:
  - 加载配置时读取 `c_decl_path`
  - `build_command()` 添加 c_decl_path 参数
  - check_paths() 增加 C SDK 路径存在性检查（仅当配置了时）

**Patterns to follow:**
- `js_decl_path` 在同文件中的传递方式

**Test scenarios:**
- Happy path: 提供 -c_decl_path 时 prompt 包含 `c_sdk_path = <path>`
- Edge case: 不提供 -c_decl_path 时 prompt 仅包含 `js_sdk_path`，向后兼容
- Edge case: c_decl_path 路径不存在时打印警告但不阻断（因为 C SDK 处理是可选的）

**Verification:**
- `python scan_kit.py -kit "Ability Kit" -out_path /tmp/test -js_decl_path /path/to/js -repo_base /path/to/db -c_decl_path /path/to/c` 构建的 prompt 包含 `c_sdk_path`
- 不带 `-c_decl_path` 时行为与修改前完全一致

- [x] **Unit 3: kit-scan-test 流水线添加 c_decl_path 传递**

**Goal:** kit-scan-test 目录下的 scan_kit.py 和 batch_scan_all.py 同步添加 c_decl_path 支持

**Requirements:** R5, R6

**Dependencies:** Unit 1

**Files:**
- Modify: `scripts/kit-scan-test/scan_kit.py`
- Modify: `scripts/kit-scan-test/batch_scan_all.py`

**Approach:**
- 与 Unit 2 完全相同的修改模式，应用到 kit-scan-test 目录的对应文件

**Patterns to follow:**
- Unit 2 中 kit-scan 目录的修改方式

**Test scenarios:**
- 同 Unit 2 的测试场景

**Verification:**
- kit-scan-test 的 scan_kit.py 支持 `-c_decl_path` 参数
- kit-scan-test 的 batch_scan_all.py 从配置加载并传递 c_decl_path

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| C SDK 路径不存在导致流水线中断 | c_decl_path 为可选参数，仅在提供时验证路径 |
| prompt 格式变化导致 kit-api-extract 解析异常 | c_sdk_path 追加方式与 js_sdk_path 完全一致 |

## Sources & References

- SKILL.md 参数定义: `.claude/skills/kit-api-extract/SKILL.md`
- C API 需求文档: `docs/brainstorms/c-api-extraction-requirements.md`
