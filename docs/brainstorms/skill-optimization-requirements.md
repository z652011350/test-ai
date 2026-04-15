---
date: 2026-04-15
topic: skill-optimization-kit-extract-and-api-scan
---

# kit-api-extract 与 api-level-scan Skill 优化

## Problem Frame

两个 HarmonyOS/OpenHarmony API 审计 skill 存在效率问题：

1. **kit-api-extract** — Agent 在追踪 API 实现路径时依赖大量搜索和猜测，缺少部件仓结构的先验知识，导致探索慢、覆盖率不稳定。实际上 `bundle.json`、`BUILD.gn` 和 C++ 文件中的 `nm_modname` 包含了确定性的结构关系，可以被脚本预先提取。

2. **api-level-scan** — 部分审计规则（`@permission`/`@systemapi`/`@since` 相关）本质上只需检查声明文件的 JSDoc 标签，但目前由 agent 逐条检查，浪费上下文窗口。这些检查可以脚本化。

## Requirements

**kit-api-extract 关系抽取脚本**

- R1. 编写 Python 脚本，输入 Kit 名称、DataBases 目录路径，以及 kit_compont.csv 路径。脚本通过 kit_compont.csv 将 Kit 名称映射到部件仓目录（使用 case-insensitive 匹配），然后扫描该部件仓，从 `bundle.json` 提取部件元信息（name、subsystem、destPath、fwk_group、inner_kits）和依赖关系
- R2. 脚本从 `BUILD.gn` 文件中提取 `ohos_shared_library`（及其他 GN target 类型，具体范围见 Outstanding Questions）target 的 `sources` 列表、`relative_install_dir`、`deps` 等编译关系。解析策略：优先处理直接赋值的静态 sources 列表，跳过变量引用和条件分支等复杂 GN 语法
- R3. 脚本扫描 C++ 源文件中的 `nm_modname` 声明，建立 `@ohos.X.Y` → nm_modname 入口文件路径（即包含 `nm_modname` 注册的 `.cpp` 文件）的确定性映射。对于无法通过 `"X.Y"` → `@ohos.X.Y.d.ts` 命名约定匹配的 nm_modname 条目，记录为 unmatched entries 供 agent 后续处理
- R4. 脚本输出结构化映射表（JSON 格式，用于 agent 查表检索，区别于 JSONL 的逐行追加模式），供 kit-api-extract 的 agent 在 Phase 2 探索时直接查表使用，避免盲搜。映射表包含：组件元信息、每个 @ohos.X.Y 模块对应的 nm_modname 入口文件路径、关联的 BUILD.gn target 及其 sources 列表
- R5. 修改 kit-api-extract 的 SKILL.md，在 Phase 1 和 Phase 2 之间插入「结构关系抽取」步骤（原 Phase 2-5 编号顺延），agent 使用映射表指导探索范围

**api-level-scan 声明层检查脚本**

- R6. 编写 Python 脚本，输入声明文件目录路径（interface_sdk-js）和 API 列表（JSONL），读取 `.d.ts`/`.d.ets` 声明文件，提取 JSDoc 标签（`@permission`、`@systemapi`、`@since`、`@throws`）。暂不处理 `.h` 文件的 Doxygen 格式（见 Outstanding Questions）。脚本复用 `extract_kit_api.py` 中已有的 JSDoc 解析逻辑（`extract_throws`、`has_tag` 等函数）
- R7. 脚本执行规则 01.001 的声明层检查：API 有 `@permission` 时，`@throws` 中必须声明 201。声明层发现违规即直接标记为 non-compliant finding，不需要实现层确认
- R8. 脚本执行规则 01.002 的声明层检查：API 有 `@systemapi` 时，`@throws` 中必须声明 202。声明层发现违规即直接标记为 non-compliant finding，不需要实现层确认
- R9. 脚本执行规则 01.003 的声明层检查：API 的 `@since >= 24` 时（若同一 API 有多个 `@since` 声明，取最后一个声明的版本号作为 since 版本），`@throws` 中不应显式列出 401
- R10. 脚本输出 JSONL 格式的声明层检查结果。仅输出 non-compliant 的记录（与现有 raw_findings.json 的「有 finding = 违规」语义一致）。每条记录的字段兼容 api-level-scan 的最终 JSONL 格式（13 个中文字段），包含 rule_id、api_declaration、module_name、declaration_file、evidence、severity_level、modification_suggestion 等必要字段
- R11. 修改 api-level-scan 的 SKILL.md：(1) 在 Phase B 之前增加声明层检查预处理步骤；(2) 从 Step 3.4 的规则前置条件检查表中移除 01.001/01.002/01.003，agent 不再处理这三条规则；(3) 在 Step 3 结束后增加脚本预处理 findings 与 agent findings 的合并步骤；(4) 同步更新 Step 4 自校验逻辑，移除对 01.001/01.002/01.003 的自校验项；(5) 确保 validate_output.py 和 classify_findings.py 兼容合并后的 findings

## Success Criteria

- kit-api-extract 运行时，agent 在 Phase 2 能直接从映射表获知 API 的 nm_modname 入口文件路径（模块注册的 `.cpp` 文件）和关联的 BUILD.gn target 及 sources，不需要盲搜
- api-level-scan 运行时，规则 01.001/01.002/01.003 的检查结果由脚本直接输出，不进入 agent 上下文
- 两个脚本均为纯 Python 3，无外部依赖

## Scope Boundaries

- 不修改规则 01.004-03.002 的检查方式（这些仍需 agent 分析实现代码）
- 不修改 `extract_kit_api.py`（现有的 Phase 1 API 声明抽取脚本保持不变）
- kit-api-extract 关系抽取脚本仅扫描当前 Kit 对应的部件仓，不做全局扫描
- 不处理 C API（NDK）的 BUILD.gn 关系抽取，仅聚焦 JS/NAPI API
- 声明层检查脚本暂不处理 `.h` 文件的 Doxygen 格式

## Key Decisions

- **声明层检查仅做声明验证，不做实现层检查**：用户确认当前实现默认符合声明，因此 01.001/01.002 的实现层检查不再需要。声明层发现违规即直接标记为 non-compliant
- **按 Kit 扫描而非全局扫描**：每次 kit-api-extract 运行只扫描当前 Kit 的部件仓，轻量快速
- **映射表为 JSON 格式**：用于 agent 查表检索，与 JSONL 的逐行追加用途不同。JSON 格式适合表达嵌套的结构关系（组件→模块→文件）
- **仅输出 non-compliant 记录**：声明层检查脚本只输出违规的 finding，与现有 raw_findings.json 的语义一致，避免格式转换开销

## Dependencies / Assumptions

- 部件仓目录结构与当前 DataBases 目录一致（`bundle.json` 在部件根目录，BUILD.gn 在各子目录）
- `nm_modname` 命名约定（`"X.Y"` 对应 `@ohos.X.Y.d.ts`）在大多数部件仓中一致，脚本需处理非标准命名（unmatched entries fallback）
- `kit_compont.csv` 中 Kit → 部件目录的映射是准确的（脚本使用 case-insensitive 匹配兼容大小写差异）

## Outstanding Questions

### Deferred to Planning

- [Affects R2-R3][Technical] BUILD.gn 的解析深度 — 需要支持哪些 GN 语法的子集？是否只处理常见的 `ohos_shared_library`/`ohos_static_library`/`js_declaration` target？建议先做最小可行方案：仅处理直接赋值的静态 sources 列表
- [Affects R4][Technical] 映射表的具体 JSON schema 设计 — 需要在 planning 阶段根据 agent 实际需要的信息字段来确定
- [Affects R6][Needs research] JSDoc 标签解析的边界情况处理 — 多行标签、连续 JSDoc 块等，需要参考 `extract_kit_api.py` 已有的解析逻辑（`extract_throws`、`has_tag` 等函数）进行复用
- [Affects R6][Needs research] `.h` 文件 Doxygen 格式的解析是否在首版中支持 — C API 使用 Doxygen 格式（`@return` 而非 `@throws`），与 JSDoc 解析逻辑完全不同。建议首版仅支持 `.d.ts`/`.d.ets`，后续扩展 `.h`

## Next Steps

-> `/ce:work` 进行结构化实现
