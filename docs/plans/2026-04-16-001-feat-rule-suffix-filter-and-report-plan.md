---
title: "feat: 规则 01.003 后缀过滤 + 审计汇总报表"
type: feat
status: active
date: 2026-04-16
origin: docs/brainstorms/rule-01003-and-report-requirements.md
---

# feat: 规则 01.003 后缀过滤 + 审计汇总报表

## Overview

两项独立但相关的改进：(1) 收窄规则 01.003 的检查范围，仅检查动态调度 API（`@since` 后缀为空或包含 `dynamic`）；(2) 在 Kit 扫描流水线中增加汇总报表生成，输出覆盖率、审计进度和问题统计。

## Problem Frame

1. 规则 01.003 当前对所有 `@since >= 24` 的 API 检查 401 声明，不区分 SDK 链接模式（static vs dynamic），导致对仅静态 API 产生不必要的 findings。
2. 批量扫描后无自动报表，需人工查看各 Kit 目录了解整体状况。

## Requirements Trace

- R1. 修改 `check_rule_01_003()` 增加 `@since` 后缀过滤
- R2. 后缀过滤规则：空或含 `dynamic` → 检查；含 `static` 不含 `dynamic` → 跳过
- R3. 所有版本号统一适用
- R4. 跳过的 API 不产生任何输出
- R5. 后缀提取内联实现，不改 `parse_since_version()` 签名
- R6. `scan_kit.py` 中增加报表生成步骤
- R7. 报表包含 10 列指标（Kit 名称、总 API 数、模块数、代码仓数、4 项覆盖率、参与审计数、存在问题数）
- R8. 同时输出 Markdown + XLSX
- R9. `batch_scan_all.py` 汇总各 Kit 生成全量报表
- R10. 审计统计从文件系统计算，不依赖 agent 输出
- R11. 缺失数据时各列独立降级（N/A）

## Scope Boundaries

- 不修改规则 01.001、01.002
- 不修改 agent 侧审计流程
- 不修改 `api.jsonl` 或 `impl_api.jsonl` 数据结构

## Context & Research

### Relevant Code and Patterns

- `check_jsdoc_rules.py` — 现有规则检查脚本，`parse_since_version()` 提取版本号，`check_rule_01_003()` 执行检查
- `batch_pipeline.py` — JSONL 读写模式（`load_and_split_impl_api`）、XLSX 生成模式（`jsonl_to_xlsx` 使用 openpyxl）、batch 文件输出到 `batch_result/input/` 目录
- `scan_kit.py` — 单 Kit 流水线，Step 1 提取、Step 2 批量审计、finally 块合并结果
- `batch_scan_all.py` — 批量编排器，遍历 CSV 中 Kit 名称，逐个调用 `scan_kit.py`

## Key Technical Decisions

- **后缀用"包含 dynamic"子串匹配**：正向判定，兼容所有变体（dynamic&static、dynamiconly 等）
- **后缀提取用 regex 剥离版本号部分**：`re.sub(r'^[\d.]+(\([^)]*\))?\s*', '', last_since)` 处理 `26.0.0 dynamic&static` 和 `6.1.1(24)` 等格式
- **报表生成函数放在 batch_pipeline.py**：复用模块已有的 JSONL 读写和 openpyxl 依赖，scan_kit.py 只负责调用
- **覆盖率分母固定为 api.jsonl 总 API 数**：`api_declaration` 标准化（collapse 空格 + strip）后去重
- **batch_scan_all.py 直接从各 Kit 目录重新计算**：遍历 `scan_out/` 下所有 Kit 子目录，读取 JSONL 文件

## Implementation Units

- [ ] **Unit 1: 规则 01.003 后缀过滤**

**Goal:** 修改 `check_jsdoc_rules.py` 中的规则 01.003，增加 `@since` 后缀过滤逻辑，仅检查动态调度 API

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** None

**Files:**
- Modify: `.claude/skills/api-level-scan/scripts/check_jsdoc_rules.py`
- Test: 需通过实际 `.d.ts` 文件验证后缀过滤行为

**Approach:**
- 在 `check_rule_01_003()` 中，版本号 >= 24 判断通过后，增加后缀过滤
- 后缀提取：使用 regex `re.sub(r'^[\d.]+(\([^)]*\))?\s*', '', last_since)` 从原始 `@since` 值中剥离版本号部分，剩余即为后缀
- 判定逻辑：后缀为空字符串或 `'dynamic' in suffix` → 继续检查；否则 → 返回 None（跳过）
- 不修改 `parse_since_version()` 函数签名

**Test scenarios:**
- `@since 24` (无后缀) → 检查
- `@since 24 dynamic` → 检查
- `@since 24 dynamic&static` → 检查
- `@since 24 dynamiconly` → 检查
- `@since 24 static` → 跳过
- `@since 24 staticonly` → 跳过
- `@since 26.0.0 dynamic&static` → 检查
- `@since 6.1.1(24)` → 检查 (无后缀)
- `@since 23 static` → 跳过（版本号 < 24，先被版本判断过滤）

**Verification:**
- 对已知含 `static` 后缀的 API，运行脚本确认无 finding 产生
- 对含 `dynamic` 后缀且有 401 声明的 API，确认 finding 正常产生

---

- [ ] **Unit 2: 报表生成工具函数**

**Goal:** 在 `batch_pipeline.py` 中新增报表生成相关的工具函数，供 scan_kit.py 和 batch_scan_all.py 调用

**Requirements:** R7, R8, R10, R11

**Dependencies:** None

**Files:**
- Modify: `scripts/kit-scan/batch_pipeline.py`

**Approach:**
新增以下函数：

1. `compute_kit_stats(output_dir: Path, kit_name: str) -> dict` — 从 `api.jsonl`、`impl_api.jsonl`、`batch_result/` 目录计算单个 Kit 的所有统计指标。返回包含所有 10 列数据的字典。核心逻辑：
   - 总 API 数：读取 `api.jsonl`，`api_declaration` 经 `' '.join(decl.split())` 标准化后去重
   - 模块数：`api.jsonl` 中 `module_name` 去重
   - 代码仓数：`impl_api.jsonl` 中 `impl_repo_path` 去重（排除空值）
   - 4 项覆盖率：`impl_api.jsonl` 中对应字段非空计数 / 总 API 数
   - 参与审计数：扫描 `batch_result/input/batch_*.jsonl`，提取所有 API 的 `api_declaration` 去重；目录不存在则返回 `None`
   - 存在问题数：读取 `batch_result/merged_api_scan_findings.jsonl`，提取 `api声明` 字段标准化后去重；文件不存在则返回 `None`

2. `write_summary_markdown(stats_list: list[dict], output_path: Path, title: str)` — 将统计字典列表格式化为 Markdown 表格并写入文件

3. `write_summary_xlsx(stats_list: list[dict], output_path: Path, title: str)` — 使用 openpyxl 生成固定列顺序的 XLSX 表格（覆盖率列格式化为百分比）

**Patterns to follow:**
- `batch_pipeline.jsonl_to_xlsx()` — openpyxl Workbook 使用模式
- `batch_pipeline.load_and_split_impl_api()` — JSONL 文件读取模式

**Test scenarios:**
- 正常数据：api.jsonl + impl_api.jsonl 存在，计算所有指标
- 缺失审计数据：无 batch_result 目录，参与审计数和存在问题数为 None
- 空文件：api.jsonl 为空，总 API 数 = 0，覆盖率 = 0%
- 覆盖率格式化：50/100 显示为 "50.00%"，Markdown 中一致

**Verification:**
- 对 `scan_out/scan-test_416/AbilityKit/` 目录运行 `compute_kit_stats()`，确认返回合理的统计值

---

- [ ] **Unit 3: scan_kit.py 集成报表生成**

**Goal:** 在 scan_kit.py 的流水线中增加报表生成步骤

**Requirements:** R6

**Dependencies:** Unit 2

**Files:**
- Modify: `scripts/kit-scan/scan_kit.py`

**Approach:**
- 在 finally 块中合并结果之后（现有 merge + xlsx 转换逻辑之后），调用 `batch_pipeline.compute_kit_stats()` 和 `write_summary_markdown()` / `write_summary_xlsx()`
- 输出路径：`<output_dir>/<kit_name>_summary.md` 和 `<output_dir>/<kit_name>_summary.xlsx`
- 报表生成不阻塞主流程：try/except 包裹，失败仅打印警告

**Test scenarios:**
- 完整流水线执行：api.jsonl + impl_api.jsonl + batch_result 均存在 → 生成完整报表
- 跳过提取模式（`-skip_extract`）：报表仍基于现有文件生成
- 报表生成失败：不影响退出码

**Verification:**
- 运行 `scan_kit.py` 后确认 `<kit_name>_summary.md` 和 `.xlsx` 文件生成

---

- [ ] **Unit 4: batch_scan_all.py 全量汇总**

**Goal:** 在所有 Kit 扫描完成后，生成跨 Kit 汇总报表

**Requirements:** R9

**Dependencies:** Unit 2

**Files:**
- Modify: `scripts/kit-scan/batch_scan_all.py`

**Approach:**
- 在 Kit 遍历循环结束后，扫描 `OUT_PATH` 下所有子目录
- 对每个子目录，检查是否包含 `api.jsonl`（判断是否为有效的 Kit 输出目录）
- 对有效目录调用 `batch_pipeline.compute_kit_stats()`，使用子目录名作为 Kit 名称
- 汇总所有 Kit 的统计字典，调用 `write_summary_markdown()` 和 `write_summary_xlsx()` 生成全量报表
- 输出路径：`<OUT_PATH>/all_kits_summary.md` 和 `<OUT_PATH>/all_kits_summary.xlsx`

**Test scenarios:**
- 多个 Kit 目录存在：汇总表包含所有 Kit 行
- 部分 Kit 处理失败（目录不完整）：跳过无 `api.jsonl` 的目录
- 无 Kit 目录：打印提示，不生成报表

**Verification:**
- 运行 `batch_scan_all.py` 后确认 `all_kits_summary.md` 和 `.xlsx` 在 `OUT_PATH` 根目录生成

## Open Questions

### Deferred to Implementation

- `compute_kit_stats()` 中的 `api_declaration` 标准化方式（当前方案为 collapse 空格 + strip），实际效果需在实现时用真实数据验证
- 批次输入文件的命名模式（`batch_0.jsonl`, `batch_1.jsonl`...）是否稳定，或有其他命名变体

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `@since` 后缀格式存在未知变体 | "包含 dynamic" 子串匹配策略已覆盖已知和未知变体；后缀提取 regex 已考虑多部分版本号 |
| 覆盖率分子分母来自不同文件，存在 ~2% 格式差异 | `api_declaration` 标准化消除空格差异 |
| 报表生成失败阻塞主流水线 | try/except 包裹，失败仅警告 |
| `api声明` 字段可能不存在于某些 findings JSONL 中 | 检查字段存在性，缺失时返回 None |

## Sources & References

- **Origin document:** [rule-01003-and-report-requirements.md](docs/brainstorms/rule-01003-and-report-requirements.md)
- `check_jsdoc_rules.py` — 规则检查脚本
- `batch_pipeline.py` — JSONL/XLSX 工具模块
- `scan_kit.py` — 单 Kit 流水线
- `batch_scan_all.py` — 批量编排器
