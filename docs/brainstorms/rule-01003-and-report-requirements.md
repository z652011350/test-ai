---
date: 2026-04-16
topic: rule-01.003-suffix-filtering-and-summary-report
---

# 规则 01.003 后缀过滤 + 审计汇总报表

## Problem Frame

两个独立但相关的改进需求：

1. **规则 01.003 检查范围过宽** — 当前 `check_jsdoc_rules.py` 对所有 `@since >= 24` 的 API 检查 401 错误码声明，不区分 `@since` 的 SDK 链接模式后缀。实际上仅需检查支持动态调度的 API（后缀为空、`dynamic`、`dynamic&static`），应跳过仅静态链接的 API（`static`、`staticonly` 等）。

2. **缺少审计汇总报表** — 批量扫描完成后，没有自动生成的 Kit 级统计数据报表。目前需要人工查看每个 Kit 的输出目录来了解整体状况，缺少覆盖率、审计进度和问题汇总的集中视图。

## Requirements

### 规则 01.003 后缀过滤

- R1. 修改 `check_jsdoc_rules.py` 中的 `check_rule_01_003()` 函数，在版本号 >= 24 判断之后，增加 `@since` 后缀过滤逻辑
- R2. 后缀过滤规则：解析 `@since` 值中版本号之后的文本部分（suffix）
  - **需要检查**（suffix 为以下之一）：空（无后缀）、`dynamic`、`dynamic&static`、`dynamic@static`
  - **跳过**：其他所有后缀（`static`、`staticonly`、`dynamiconly` 等）
- R3. 对所有版本号统一适用该过滤规则（24、25、26... 均遵循相同的后缀判定逻辑）
- R4. 被跳过的 API 不计入 findings，也不产生任何输出记录
- R5. 在 `check_rule_01_003()` 中内联实现后缀提取：从 `last_since` 原始值中移除已解析的版本号部分即可得到后缀文本，无需修改 `parse_since_version()` 的返回签名

### 审计汇总报表

- R6. 在 `scan_kit.py` 中增加报表生成步骤：在 Step 3（合并审计结果，当前位于 finally 块中）执行完毕后，增加独立的报表生成步骤，生成该 Kit 的统计数据
- R7. 报表包含以下列（每个 Kit 一行）：

  | 列名 | 数据来源 | 计算方式 |
  |---|---|---|
  | Kit 名称 | 运行参数 | `normalize_kit_name(kit_name)`（去空格版本，来自 scan_kit.py） |
  | 总 API 数 | `api.jsonl` | 去重计数（按 `api_declaration` 标准化后，标准化方式：collapse 空格后 strip）。所有覆盖率指标的分母固定为此值 |
  | 模块数 | `api.jsonl` | 去重计数（按 `module_name`） |
  | 代码仓数 | `impl_api.jsonl` | 去重计数（按 `impl_repo_path`，排除空值） |
  | NAPI 覆盖率 | `impl_api.jsonl` | `NAPI_map_file` 非空的 API 数 / 总 API 数。注意：分子从 `impl_api.jsonl` 直接计数非空行，与 `api.jsonl` 之间可能存在 ~2% 的 api_declaration 格式差异（空格），通过标准化消除 |
  | 实现函数名覆盖率 | `impl_api.jsonl` | `impl_api_name` 非空的 API 数 / 总 API 数（同上） |
  | Framework 声明覆盖率 | `impl_api.jsonl` | `Framework_decl_file` 非空的 API 数 / 总 API 数（同上） |
  | 业务实现覆盖率 | `impl_api.jsonl` | `impl_file_path` 非空的 API 数 / 总 API 数（同上） |
  | 参与审计的 API 数 | 批次输入文件 | 从 `batch_result/` 下的批次输入 JSONL 文件中统计被送去审计的 API 数（去重） |
  | 存在问题的 API 数 | 审计输出文件 | 从 `batch_result/merged_api_scan_findings.jsonl` 中提取 `api声明` 字段去重计数（标准化后），作为有违规 finding 的 API 数量 |

- R8. 报表输出格式：同时生成 Markdown 表格和 XLSX 表格
  - Markdown: `<output_dir>/<kit_name>_summary.md`
  - XLSX: `<output_dir>/<kit_name>_summary.xlsx`
- R9. 在 `batch_scan_all.py` 中增加汇总步骤：所有 Kit 扫描完成后，直接从各 Kit 输出目录的 `api.jsonl`、`impl_api.jsonl`、`batch_result/merged_api_scan_findings.jsonl` 重新计算统计数据，生成全量汇总报表（同样输出 Markdown + XLSX）

### 流水线统计指标

- R10. `参与审计的 API 数` 和 `存在问题的 API 数` 由流水线脚本从文件系统直接计算，不依赖 agent 输出，避免 agent 异常导致数据缺失
  - `参与审计的 API 数`：从 `batch_result/` 下的批次输入 JSONL 文件中统计被送去审计的 API 数（去重）
  - `存在问题的 API 数`：从 `batch_result/merged_api_scan_findings.jsonl` 中的 `api声明` 字段（标准化后）去重计数，作为有违规 finding 的 API 数量
- R11. 缺失数据时各列的降级处理：
  - 覆盖率相关列（总 API 数、模块数、代码仓数、NAPI/FW/实现覆盖率）：仅依赖 `api.jsonl` 和 `impl_api.jsonl`，不受审计执行状态影响
  - `参与审计的 API 数`：若 `batch_result/` 下无批次输入 JSONL 文件（批次未准备），显示 `N/A`
  - `存在问题的 API 数`：若 `batch_result/merged_api_scan_findings.jsonl` 不存在（审计未产出），显示 `N/A`

## Success Criteria

- 规则 01.003 仅对 `@since` 后缀为空或包含 `dynamic` 子串的 API 生成 401 违规 findings（空后缀如 `@since 24` 等同于动态调度 API），对仅静态 API（`@since N static`、`@since N staticonly` 等 `@since` 后缀不含 `dynamic` 的 API）不生成任何 finding
- 单 Kit 扫描完成后，自动生成包含覆盖率、审计进度、问题汇总的报表（Markdown + XLSX）
- 批量扫描完成后，自动生成跨 Kit 汇总报表
- `参与审计的 API 数` 和 `存在问题的 API 数` 可靠地从流水线文件计算，不受 agent 异常影响。两者语义不同：参与审计数统计被送去审计的 API 总量（来自批次输入），存在问题数统计 JSONL findings 中有记录的 API（来自 `api声明` 字段去重）

## Scope Boundaries

- 不修改规则 01.001、01.002 的检查逻辑
- 不修改 agent 侧的审计流程，仅修改预处理脚本和流水线脚本
- 不修改 `api.jsonl` 或 `impl_api.jsonl` 的数据结构
- 覆盖率指标的计算完全基于 `impl_api.jsonl` 现有字段，不增加新的提取步骤

## Key Decisions

- **后缀过滤采用白名单**：仅检查后缀为空（无后缀）、`dynamic`、`dynamic&static`、`dynamic@static` 的 API，其他后缀（`static`、`staticonly`、`dynamiconly` 等）均跳过
- **报表集成到 scan_kit.py 而非独立脚本**：减少文件数量，且 scan_kit.py 已经持有所有需要的路径信息
- **参与审计数从批次输入文件计算，问题数从 findings JSONL 计算**：两者语义不同，参与数 = 被送去审计的 API 总量，问题数 = 有违规记录的 API 数量
- **覆盖率分母固定为 api.jsonl 总 API 数**：所有覆盖率指标（NAPI、实现函数名、Framework 声明、业务实现）的分母统一使用 `api.jsonl` 去重计数，保证口径一致
- **batch_scan_all.py 从各 Kit 目录重新计算汇总**：不依赖中间文件或 subprocess 返回值，直接读取各 Kit 输出目录中的 JSONL 文件

## Dependencies / Assumptions

- `impl_api.jsonl` 中的覆盖率相关字段（`impl_api_name`、`NAPI_map_file`、`Framework_decl_file`、`impl_file_path`）在 kit-api-extract 阶段已正确填充
- 审计输出 JSONL 的 `受影响的api` 字段存在非标准化值（如括号后缀），不适合用于精确去重；改用 `api声明` 字段进行去重计数
- `scan_kit.py` 和 `extract_kit_api.py` 中的 `normalize_kit_name` 行为相反（去空格 vs 加空格），Kit 名称在报表中使用 scan_kit.py 的版本（去空格）
- XLSX 生成复用 `openpyxl` 依赖（已在 `batch_pipeline.py` 中引入），不引入新依赖。注意：`batch_pipeline.jsonl_to_xlsx()` 是通用 JSONL 转换器，汇总报表需要独立的 XLSX 生成逻辑

## Next Steps

-> `/ce:plan` 进行实现规划
