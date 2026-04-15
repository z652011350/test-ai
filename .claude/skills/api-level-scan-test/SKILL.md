---
name: api-level-scan-test
description: >
  Harness 模式的 HarmonyOS/OpenHarmony API 规则驱动审计技能。
  将输入 API 列表按模块分组，通过并行 subagent 执行深度调用链审计，
  再由独立校验 subagent 合并结果并生成最终输出。
  输入为 JSONL 格式的 API 列表（每行含声明、NAPI映射、Framework接口、实现路径等 8 个字段）。
  当用户提供 JSONL 格式的 API 列表并需要对每个 API 逐个进行规范性审计、错误码检查、调用链分析时使用。
  触发场景包括：API 级别审计、单个 API 错码检查、调用链分析、API 规范性扫描、API level scan。
---

## 参数

```json
{
  "api_input": "JSONL 文件路径（每行一个 JSON 对象）",
  "repo_base": "代码仓库基础目录（包含各部件仓库的根目录）",
  "rule_xlsx": "规则 XLSX 文件路径（可选，覆盖 config/rule.json）",
  "out_path": "输出目录",
  "js_sdk_path": "JS SDK 声明文件目录（interface_sdk-js，用于声明层规则预处理）",
  "max_parallel": 3,
  "group_strategy": "auto",
  "api_error_code_doc_path":"API 文档开源代码仓的根目录",
  "kit_name": "Kit 名称，如 'Ability Kit'",
  "group_size": 80
}
```

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `api_input` | 是 | - | JSONL 文件路径，每行一个 JSON 对象 |
| `repo_base` | 是 | - | 代码仓库基础目录，包含各 OpenHarmony 部件仓库 |
| `rule_xlsx` | 否 | - | 规则 XLSX 文件，提供时先转换为 config/rule.json |
| `out_path` | 是 | - | 输出目录，结果保存至 `out_path/api_scan/` |
| `js_sdk_path` | 是 | - | JS SDK 声明文件目录（interface_sdk-js），用于 Step 1.5 声明层规则预处理 |
| `max_parallel` | 否 | 3 | 并行审计 subagent 最大数量（1-5） |
| `group_strategy` | 否 | `auto` | 分组策略：`module`按模块名 / `fixed`固定大小 / `auto`自动选择 |
| `group_size` | 否 | 80 | `fixed` 策略下每组的 API 数量 |
| `api_error_code_doc_path` | 否 | - | API 错误码文档开源仓根目录（包含 zh-cn 目录），提供时提取错误码文档供 subagent 参考 |
| `kit_name` | 否 | - | Kit 名称（如 "Ability Kit"），与 `api_error_code_doc_path` 同时提供时提取该 Kit 的错误码文档 |

---

## 执行模式

统一采用 Harness 模式：将 API 列表按模块分组，并行调度审计 subagent 处理每组 API，再由独立校验 subagent 合并结果，最后由验证 subagent 过滤误报。不论 API 数量多少，均通过 subagent 执行。

---

## 输入格式

每行一个 JSON 对象，包含 8 个字段：

**格式1**
```json
{"api_declaration": "function setController(controller: WindowAnimationController): void", "module_name": "@ohos.animation.windowAnimationManager", "js doc": "/**\n xxx */","impl_api_name": "RSWindowAnimationManager::SetController", "impl_repo_path": "graphic_graphic_2d", "declaration_file": "api/@ohos.animation.windowAnimationManager.d.ts", "NAPI_map_file": "graphic_graphic_2d/interfaces/kits/napi/graphic/animation/window_animation_manager/rs_window_animation_manager.cpp", "Framework_decl_file": "graphic_graphic_2d/rosen/modules/animation/window_animation/include/rs_window_animation_stub.h", "impl_file_path": "graphic_graphic_2d/interfaces/kits/napi/graphic/animation/window_animation_manager/rs_window_animation_manager.cpp"}
```

**格式2**
对于部分未能在前期直接找到映射的api，则采用以下格式
```json
{"api_declaration": "function getWant(callback: AsyncCallback<Want>): void", "js_doc": "/**\n....*/", "module_name": "@ohos.ability.featureAbility", "declaration_file": "api/@ohos.ability.featureAbility.d.ts"}
```
对于这些未能找到映射的api，请设定一个subagent，参考/kit-api-extract的技能说明找到对应的api映射，仅要求 subagent输出impl_api.jsonl即可

| 字段 | 类型 | 说明 |
|------|------|------|
| `api_declaration` | string | API 声明（完整函数签名，来自 .d.ts/.d.ets） |
| `module_name` | string | 模块名（如 `@ohos.animation.windowAnimationManager`） |
| `impl_api_name` | string | 实现函数名（NAPI 映射的 C++ 函数名） |
| `impl_repo_path` | string | 仓库名（仅 repo_name，如 `graphic_graphic_2d`） |
| `declaration_file` | string | API 声明文件路径（.d.ts / .d.ets） |
| `NAPI_map_file` | string | NAPI 映射文件路径（C++ NAPI 插件源码，含 JS 方法名到 C++ 函数的映射关系） |
| `Framework_decl_file` | string | Framework 接口声明文件路径（.h 头文件，定义 IPC 接口） |
| `impl_file_path` | string | 业务逻辑实现文件完整路径（.cpp） |

这些字段对应完整的代码路径分析流程：
1. **interface**（`declaration_file`）：暴露给应用层的函数签名、入参和返回类型
2. **NAPI 映射**（`NAPI_map_file`）：JS 方法名与 C++ 函数的映射关系
3. **Framework 接口声明**（`Framework_decl_file`）：IPC Proxy/Stub 模式的接口定义
4. **业务逻辑实现**（`impl_file_path`）：底层实际处理逻辑的代码

---

## 执行步骤

### Phase A：规则准备

#### Step 1. 规则加载

**1.1** 如果用户提供了 `rule_xlsx`：

```bash
python3 {{skill_path}}/scripts/convert_xlsx_to_json.py "{{rule_xlsx}}" "{{skill_path}}/config/rule.json"
```

转换结果覆盖写入 `config/rule.json`。

**1.2** 如果用户同时提供了 `api_error_code_doc_path` 和 `kit_name`，提取错误码文档：

```bash
python3 {{skill_path}}/scripts/extract_errorcode_docs.py "{{api_error_code_doc_path}}" "{{kit_name}}" "{{out_path}}/api_scan/error_code_doc"
```

输出目录为 `{out_path}/api_scan/error_code_doc/`。

如果脚本报错或未提取到文件，打印警告 `[harness] Warning: No error code docs extracted for kit '{{kit_name}}'`，继续执行后续步骤（不中断流程）。

**1.3** 过滤评分类规则：

```bash
python3 {{skill_path}}/scripts/filter_rules.py "{{skill_path}}/config/rule.json" -o "{{out_path}}/api_scan/active_rules.json"
```

**1.4** 声明层规则检查（脚本预处理，规则 01.001/01.002/01.003）：

对 API 列表中的声明文件执行纯声明层 JSDoc 标签检查，将结果保存为预处理 findings，后续审计 subagent 不再处理这三条规则。

```bash
python3 {{skill_path}}/scripts/check_jsdoc_rules.py \
  --js_sdk {{js_sdk_path}} \
  --api_list {{api_input}} \
  -o "{{out_path}}/api_scan"
```

输出: `{out_path}/api_scan/jsdoc_rule_findings.jsonl` 和 `{out_path}/api_scan/jsdoc_rule_findings.json`

**脚本检查的规则**：
- **01.001**：API 有 `@permission` 时，`@throws` 中必须声明 201
- **01.002**：API 有 `@systemapi` 时，`@throws` 中必须声明 202
- **01.003**：API 的 `@since >= 24` 时，`@throws` 中不应显式列出 401

脚本仅输出 non-compliant 的记录，格式与 raw_findings.json 的 9 字段结构一致。

---

### Phase B：Harness 调度

#### Step 2. 解析与分组

**2.1** 读取 `api_input` 文件路径，逐行解析为 JSON 对象。记录 API 条目总数 n。

**2.2** 分离 Format 2 API（`impl_api_name` 为空且有 `js_doc` 的条目），单独处理。

**2.3** 记录 API 总数 n，继续分组步骤。

**2.4** 按 `group_strategy` 分组：

- **`module`**：按 `module_name` 字段分组。同模块 API 共享声明文件和实现目录，最大化代码读取局部性。单模块 > 200 API 时按 ~100 API 拆分子组。单模块 < 10 个API 时合并, 合并策略优先同 `impl_repo_path` 的相邻小模块, 若无`impl_repo_path`则按个数合并，保证合并后每组不低于20个API。
- **`fixed`**：按 `group_size`（默认 80）均匀切分。
- **`auto`**（默认）：先按 `module` 分组，若平均组大小在 20-200 之间则使用 `module` 策略，否则使用 `fixed` 策略。

**2.5** 创建输出目录并写入分组文件：

```bash
mkdir -p "{{out_path}}/api_scan/groups"
```

将每组 API 写入 `{out_path}/api_scan/groups/group_{i}.jsonl`（i 从 1 开始）。

**2.6** 断点续跑检查：扫描 `{out_path}/api_scan/subagent_results/status_{i}.json`，若存在且 `"status" == "completed"` 则标记该组已完成，跳过。

打印恢复摘要：`[harness] Found X completed groups, Y pending groups, Z total groups`

#### Step 3. 分批调度审计与校验 Subagent

将待处理的组按每 5 个分为一个校验批次。对每个校验批次循环执行以下流程：

**3.1** 取下一个校验批次的组（最多 5 个，从 pending_groups 中取出）。

**3.2** 对该批次内的组，按 `max_parallel` 并行调度审计 subagent：
- 使用 Agent tool 调度，`run_in_background: true`，`subagent_type: "general-purpose"`
- 为每个组构建审计 subagent prompt，严格遵循「审计 Subagent Prompt 模板」
- 每个完成的 subagent 写入 `status_{i}.json` 作为完成标记
- 同时运行的 subagent 个数不得大于 `max_parallel`

**3.3** 等待该批次所有审计 subagent 完成。

**3.4** 该批次审计完成后，立即调度校验 subagent：
- 使用 Agent tool 调度，`subagent_type: "general-purpose"`
- 传入校验 prompt（遵循「校验 Subagent Prompt 模板」），`{{completed_groups}}` 设为该批次的成功组，`{{batch_output_dir}}` 设为 `{out_path}/api_scan/subagent_results/validation_batch_{batch_index}`
- 校验 subagent 将该批次的中间结果写入各自的 `validation_batch_{batch_index}/` 目录
- 等待该校验 subagent 完成

**3.5** 失败处理：若某个审计 subagent 未能产生输出文件，重试一次。若仍失败，标记该组为 failed。

**3.6** 记录校验批次计数 `batch_index++`，重复 3.1-3.5 直到所有组处理完毕。

**3.7** 全部批次完成后，统计：
- 总成功组数、总失败组数
- 校验批次数
- 若全部组都失败，中止流程并报告错误

打印调度摘要：`[harness] Completed: X audit groups in Y validation batches, Z failed groups`

#### Step 4. 合并所有校验批次结果

扫描 `{out_path}/api_scan/subagent_results/` 下所有 `validation_batch_*` 目录：

**4.1** 合并 findings：
- 读取所有 `validation_batch_{i}/raw_findings.json` 的 `findings` 数组
- 合并到一个总的 findings 列表
- 全局去重检查（rule_id + affected_apis）
- **合并 Step 1.4 脚本预处理的声明层 findings**：读取 `{out_path}/api_scan/jsdoc_rule_findings.json` 的 `findings` 数组，追加到合并列表中
- 写入 `{out_path}/api_scan/raw_findings.json`

**4.2** 合并 call_chains：
- 读取所有 `validation_batch_{i}/api_call_chains.json`
- 合并写入 `{out_path}/api_scan/api_call_chains.json`

**4.3** 合并 JSONL：
- 读取所有 `validation_batch_{i}/api_scan_findings.jsonl`
- 合并写入 `{out_path}/api_scan/api_scan_findings.jsonl`

**4.4** 合并分类结果：
- 读取所有 `validation_batch_{i}/classified_findings.json`
- 合并写入 `{out_path}/api_scan/classified_findings.json`

**4.5** 生成汇总报告：读取 `{{skill_path}}/templates/api_scan_summary.md` 模板，填充合并后的数据，写入 `{out_path}/api_scan/api_scan_summary.md`。

**4.6** 运行输出验证：

```bash
python3 {{skill_path}}/scripts/validate_output.py "{{out_path}}/api_scan" --rules "{{out_path}}/api_scan/active_rules.json"
```

如果验证失败，修正问题后重新验证。

**4.7** 写入校验状态：

```json
// 写入 {out_path}/api_scan/validation_status.json
{
  "status": "passed",
  "total_findings": 0,
  "total_groups": 0,
  "validation_batches": 0,
  "failed_groups": [],
  "validation_errors": []
}
```

#### Step 5.5. 调度验证 Subagent

使用 Agent tool 调度单个验证 subagent（`subagent_type: "general-purpose"`），传入验证 prompt（遵循下方的「验证 Subagent Prompt 模板」）。

验证 subagent 负责：
1. 读取 `api_scan_findings.jsonl`（校验 subagent 的最终输出）
2. 对每条发现执行源码级准确性验证：基础校验 → 规则前提条件校验 → 代码证据校验 → 交叉校验
3. 判定 verdict：confirmed / false_positive / unverifiable / partially_correct
4. 用 verified findings 覆盖 `api_scan_findings.jsonl`（仅保留 confirmed + partially_correct + unverifiable）
5. 输出 `false_positive_findings.jsonl` 和 `verification_report.json`
6. 更新 `api_scan_summary.md` 中的统计数据
7. 写入 `verification_status.json`

如果验证 subagent 失败，harness 打印警告但不中断流程（回退使用校验 subagent 的原始 `api_scan_findings.jsonl`）。

---

### Phase C：完成确认

#### Step 6. 检查最终输出

确认以下文件存在于 `{out_path}/api_scan/`：
- `api_scan_findings.jsonl`（已验证版本）
- `api_call_chains.json`
- `api_scan_summary.md`（含验证统计）
- `validation_status.json`（校验 subagent 写入，`status` 为 `passed`）
- `verification_report.json`（验证统计报告）
- `verification_status.json`（验证 subagent 写入，`status` 为 `completed`）

若 `validation_status.json` 显示验证失败，报告具体错误。
若 `verification_status.json` 不存在或 status 非 completed，打印警告但不中断（回退使用校验 subagent 的原始输出）。

---

## 审计 Subagent Prompt 模板

模板文件：`{{skill_path}}/subagents/audit_subagent_prompt.md`

Harness 必须按此模板为每个 group 构造 prompt，将 `{{变量}}` 替换为实际值。

**变量替换规则**：

| 变量 | 替换为 |
|------|--------|
| `{{group_file_path}}` | `{out_path}/api_scan/groups/group_{i}.jsonl` |
| `{{repo_base}}` | 用户提供的 `repo_base` |
| `{{out_path}}` | 用户提供的 `out_path` |
| `{{batch_index}}` | 当前组编号 i |
| `{{api_count}}` | 当前组 API 数量 |
| `{{active_rules_path}}` | `{out_path}/api_scan/active_rules.json` |
| `{{skill_path}}` | skill 目录绝对路径 |
| `{{rules_count}}` | active_rules.json 中规则数量 |
| `{{RULES_SUMMARY}}` | 规则摘要（见下方构建方法） |
| `{{error_code_doc_path}}` | `{out_path}/api_scan/error_code_doc/`（仅当 `api_error_code_doc_path` 和 `kit_name` 均已提供且提取成功时；否则为空字符串） |

**构建规则摘要**：

读取 `active_rules.json`，对每条规则生成一行摘要：
```
- {id}: {description}
```

将所有规则摘要拼接后替换模板中的 `{{RULES_SUMMARY}}` 占位符。

---

## 校验 Subagent Prompt 模板

模板文件：`{{skill_path}}/subagents/validation_subagent_prompt.md`

**变量替换规则**：

| 变量 | 替换为 |
|------|--------|
| `{{out_path}}` | 用户提供的 `out_path` |
| `{{active_rules_path}}` | `{out_path}/api_scan/active_rules.json` |
| `{{skill_path}}` | skill 目录绝对路径 |
| `{{batch_output_dir}}` | `{out_path}/api_scan/subagent_results/validation_batch_{batch_index}` |
| `{{batch_index}}` | 当前校验批次编号（从 1 开始） |
| `{{completed_groups}}` | 该批次成功完成的组编号列表（如 `"1,2,3"`） |
| `{{failed_groups}}` | 该批次失败的组编号列表（如 `"4"`） |

---

## 验证 Subagent Prompt 模板

模板文件：`{{skill_path}}/subagents/verify_subagent_prompt.md`

**变量替换规则**：

| 变量 | 替换为 |
|------|--------|
| `{{findings_input}}` | `{out_path}/api_scan/api_scan_findings.jsonl` |
| `{{repo_base}}` | 用户提供的 `repo_base` |
| `{{active_rules_path}}` | `{out_path}/api_scan/active_rules.json` |
| `{{out_path}}` | 用户提供的 `out_path` |
| `{{skill_path}}` | skill 目录绝对路径 |

---

## Subagent 输出契约

### 审计 Subagent 输出

| 文件 | 路径 | 格式 |
|------|------|------|
| `raw_findings_{i}.json` | `{out_path}/api_scan/subagent_results/` | `{"findings": [...]}` 9 个英文字段 |
| `call_chains_{i}.json` | `{out_path}/api_scan/subagent_results/` | JSON array of call chain docs |
| `status_{i}.json` | `{out_path}/api_scan/subagent_results/` | `{"status":"completed","batch_index":N,"api_count":N,"findings_count":N,"duration_seconds":N}` |

### 校验 Subagent 输出（每批次）

| 文件 | 路径 | 格式 |
|------|------|------|
| `raw_findings.json` | `{out_path}/api_scan/subagent_results/validation_batch_{i}/` | `{"findings": [...]}` 该批次合并后 |
| `api_call_chains.json` | `{out_path}/api_scan/subagent_results/validation_batch_{i}/` | 该批次调用链 |
| `classified_findings.json` | `{out_path}/api_scan/subagent_results/validation_batch_{i}/` | 该批次分类结果 |
| `api_scan_findings.jsonl` | `{out_path}/api_scan/subagent_results/validation_batch_{i}/` | 该批次 13 字段 JSONL |
| `validation_status.json` | `{out_path}/api_scan/subagent_results/validation_batch_{i}/` | `{"status":"completed","batch_index":i,...}` |

### 验证 Subagent 输出

| 文件 | 路径 | 格式 |
|------|------|------|
| `api_scan_findings.jsonl` | `{out_path}/api_scan/` | 覆盖原始文件，仅保留 confirmed/partially_correct/unverifiable（原始 13 字段） |
| `false_positive_findings.jsonl` | `{out_path}/api_scan/` | 被判定为误报的发现，附加 `_verdict` 和 `_verdict_reason` |
| `verification_report.json` | `{out_path}/api_scan/` | `{"total_findings":N,"confirmed":X,"false_positive":Y,...}` |
| `api_scan_summary.md` | `{out_path}/api_scan/` | 更新后的汇总报告（含验证统计段落） |
| `verification_status.json` | `{out_path}/api_scan/` | `{"status":"completed","total_findings":N,"confirmed":X,...}` |

---

## 断点续跑协议

1. 调度前检查 `status_{i}.json` 是否存在且 `"status" == "completed"`
2. 已完成则跳过，打印：`[harness] Skipping group {i} (already completed)`
3. 若 `status_{i}.json` 存在但 `status` 不是 `completed`，或输出文件缺失/格式错误，视为未完成并重新调度
4. 启动时打印恢复摘要：`[harness] Found X completed, Y pending, Z total`

---

## 输出目录结构

```
{out_path}/api_scan/
  active_rules.json                # Phase A 产出
  error_code_doc/                  # 错误码参考文档（Phase A Step 1.3 产出，可选）
  groups/                          # 分组输入文件
    group_1.jsonl ... group_N.jsonl
  subagent_results/                # 审计 subagent per-group 输出
    raw_findings_1.json
    call_chains_1.json
    status_1.json
    ...
    validation_batch_1/            # 校验 subagent 批次 1 输出
      raw_findings.json
      api_call_chains.json
      classified_findings.json
      api_scan_findings.jsonl
      validation_status.json
    validation_batch_2/            # 校验 subagent 批次 2 输出
      ...
  raw_findings.json                # 全部合并后（Step 4 产出）
  classified_findings.json         # 全部合并后（Step 4 产出）
  api_scan_findings.jsonl          # 最终 JSONL 输出（Step 4 产出，验证后更新）
  api_call_chains.json             # 最终调用链（Step 4 产出）
  api_scan_summary.md              # 汇总报告（含验证统计）
  validation_status.json           # 合并校验状态（Step 4 产出）
  false_positive_findings.jsonl    # 误报发现列表
  verification_report.json         # 验证统计报告
  verification_status.json         # 验证 subagent 状态
```

---

## 执行顺序（严格按序）

1. 规则加载 → `filter_rules.py` → `check_jsdoc_rules.py`（声明层预处理 01.001/01.002/01.003）
1.5 [如果提供 `api_error_code_doc_path` + `kit_name`] 提取错误码文档 → `extract_errorcode_docs.py`
2. 解析输入 → 分组 → 检查已完成组（断点续跑）
3. [Format 2 API] 调度映射 subagent 查找 impl 映射
4. 循环：每 5 个组 → 并行调度审计 subagent → 等待完成 → 调度校验 subagent（max_parallel 并发审计）
5. 合并所有校验批次结果（findings + call_chains + JSONL + classify + validate）+ 合并 Step 1.4 脚本预处理 findings
6. 检查 `validation_status.json`，确认通过
7. 调度验证 subagent（源码级准确性验证 + 过滤误报）
8. 检查 `verification_status.json`，确认验证完成

---

## 关键参考文件

| 文件 | 用途 |
|------|------|
| `config/rule.json` | 唯一规则来源 |
| `subagents/audit_subagent_prompt.md` | 审计 subagent prompt 模板 |
| `subagents/validation_subagent_prompt.md` | 校验 subagent prompt 模板 |
| `subagents/verify_subagent_prompt.md` | 验证 subagent prompt 模板 |
| `references/call_chain_analysis_guide.md` | 调用链分析方法（subagent 按需读取） |
| `references/common_error_codes.md` | 通用错误码参考（201/202/203/401/801） |
| `references/LESSONS_LEARNED.md` | 历史审计经验 |
| `references/output_schema.md` | 输出结构定义 |
| `references/problem_patterns_checklist.md` | 常见问题模式（40 项） |
| `templates/api_scan_summary.md` | 汇总报告模板 |
| `scripts/extract_errorcode_docs.py` | 提取 Kit 错误码文档 |
| `scripts/check_jsdoc_rules.py` | 声明层 JSDoc 规则预处理（01.001/01.002/01.003） |

---

## 注意事项

1. **Harness 统一负责分组、调度、编排**，所有审计通过 subagent 执行
2. **config/rule.json 是唯一规则来源**
3. **每个审计 subagent 处理独立的一组 API**，组间无交叉
4. **校验 subagent 单独运行**，不与审计 subagent 并行
5. **subagent 间不共享状态**，仅通过文件系统通信
6. **合并时检查去重**（rule_id + affected_apis）
7. **`call_chains` 必须覆盖所有输入 API**（含无发现的 API）
8. **每个审计 subagent 限制在 20-200 个 API 范围内**
9. **调用链分析无深度限制**
10. **影响的错误码** 必须是开发者通过 BusinessError.code 收到的数值错误码
11. **成功码（0）不是错误码**，在影响的错误码中排除
12. 如果输入量较大，审计 subagent 每处理 10 个 API 将中间结果刷新到文件
13. 仅报告实际违反规则的问题，不得报告遵守规则的情况
14. 无需考虑时间，避免因时间过长而着急输出结果
15. **验证 subagent 以保守为原则**：无法验证的发现应保留而非删除
16. **验证失败不阻断流程**：若验证 subagent 失败，使用校验 subagent 的原始输出

---

## 禁止事项

- 禁止输出评分、权重等评分类字段
- 禁止按 Kit 聚合输出（这是按 API 的审计）
- 禁止使用 GetDoc.py 或抓取文档
- 禁止使用 extract_js_api.py 或 extract_c_api.py（用户直接提供 API 列表）
- 禁止跳过 validate_output.py 验证步骤
- 禁止忽略验证错误
- 禁止在验证 subagent 未完成时删除原始 api_scan_findings.jsonl（验证失败时需保留原始文件）
