# API DFX 2.0

HarmonyOS/OpenHarmony API 错误码规范性自动审计平台。基于 Claude Code CLI 驱动，通过 Skill 定义实现 API 声明提取、实现链路探索和规则驱动的合规审计。

**核心流程**：Kit 声明文件 → API 提取（`kit-api-extract`）→ 实现链路探索 → 规则驱动审计（`api-level-scan` 或 `api-level-scan-test`）→ 结构化审计发现

## 目录

- [项目结构](#项目结构)
- [前置条件](#前置条件)
- [快速开始](#快速开始)
- [两种流水线](#两种流水线)
- [调用逻辑](#调用逻辑)
- [适配不同 Agent 工具](#适配不同-agent-工具)
- [路径配置](#路径配置)
- [Skill 参考](#skill-参考)
- [审计规则](#审计规则)
- [输出格式](#输出格式)
- [FAQ](#faq)

## 项目结构

```
api_dfx_2.0/
├── .claude/
│   ├── settings.local.json              # Claude Code 权限配置
│   └── skills/
│       ├── kit-api-extract/             # Skill 1: API 提取 + 实现链路探索
│       │   ├── SKILL.md                 # 技能定义（5 阶段）
│       │   ├── scripts/
│       │   │   ├── extract_kit_api.py   # 从 .d.ts/.h 提取 JS/C API 声明
│       │   │   ├── extract_component_map.py # 结构关系抽取（bundle.json/BUILD.gn）
│       │   │   ├── extract_c_impl_map.py   # C API 实现映射（@library → BUILD.gn → 源文件）
│       │   │   └── merge_agent_results.py # 合并 subagent 结果
│       │   └── reference/
│       │       └── MAPPING_PATTERNS.md  # 16 种 NAPI 映射模式知识库
│       ├── api-level-scan/              # Skill 2: 单体模式审计
│       │   ├── SKILL.md                 # 技能定义（7 步）
│       │   ├── config/rule.json         # 16 条审计规则
│       │   ├── scripts/                 # 规则转换、过滤、分类、验证等脚本
│       │   ├── references/              # 审计指南、经验总结、输出 schema
│       │   ├── templates/               # 汇总报告模板
│       │   └── assets/kit_compont.csv   # Kit-部件映射表
│       └── api-level-scan-test/         # Skill 3: Harness 模式审计
│           ├── SKILL.md                 # 技能定义（8 步）
│           ├── config/rule.json         # 同上 16 条规则
│           ├── scripts/                 # 同上 + extract_errorcode_docs.py
│           └── subagents/               # subagent prompt 模板
│               ├── audit_subagent_prompt.md
│               └── validation_subagent_prompt.md
├── data/
│   ├── docs/                            # HarmonyOS API 文档仓库
│   └── test/                            # 测试数据
└── scripts/
    ├── common/                            # 共享模块（跨流程复用）
    │   ├── __init__.py
    │   ├── runner.py                      # 统一 Agent runner（claude/opencode 双后端）
    │   ├── data_utils.py                  # JSONL 加载/分割/匹配/XLSX 转换
    │   ├── kit_utils.py                   # Kit 名称规范化、文件查找、CSV 读取
    │   └── config.py                      # JSON 配置加载 + CLI 覆盖
    ├── scan_config.json                   # 默认配置文件（路径、后端、重试策略）
    ├── component-scan/                    # 流水线 C：部件级扫描
    │   ├── batch_scan.py                  # 批量扫描入口
    │   ├── claude_runner.py               # Agent CLI 封装（含 build_skill_prompt）
    │   ├── gen_csv.py                     # 生成 components.csv 输入文件
    │   └── result_collector.py            # 结果收集与汇总报告
    ├── kit-scan/                          # 流水线 A：单体模式
    │   ├── scan_kit.py                    # 入口脚本
    │   ├── batch_pipeline.py              # 数据分批、prompt 构建、结果合并、报表
    │   ├── claude_runner.py               # Agent CLI 封装（指数退避重试）
    │   └── batch_scan_all.py              # 批量扫描所有 Kit
    └── kit-scan-test/                     # 流水线 B：Harness 模式
        ├── scan_kit.py                    # 入口脚本
        ├── data_prepare.py               # 数据合并（jsonl_to_xlsx 已提取到 common）
        ├── claude_runner.py               # Agent CLI 封装（追加提示重试，支持 opencode）
        └── batch_scan_all.py              # 批量扫描所有 Kit
```

## 前置条件

| 依赖 | 说明 | 验证 |
|------|------|------|
| Claude Code CLI | AI Agent 引擎，需在 PATH 中可用为 `claude` | `claude --version` |
| Python 3.9+ | 运行流水线脚本 | `python3 --version` |
| openpyxl | JSONL 转 XLSX 依赖 | `pip install openpyxl` |

**外部数据依赖**：

| 数据 | 说明 | 对应参数 |
|------|------|----------|
| interface_sdk-js | HarmonyOS JS SDK 声明仓库，含 `kits/@kit.*.d.ts` 文件 | `-js_decl_path` |
| interface_sdk-c | HarmonyOS C SDK 声明仓库，含 `.h` 头文件（可选） | `-c_decl_path` |
| DataBases | 各部件源码仓库合集，即全量代码仓根目录，如 `ability_ability_runtime/` | `-repo_base` |
| 文档仓库（可选） | HarmonyOS API 文档，用于错误码参考 | `-api_error_code_doc_path` |

## 快速开始

### 单 Kit 扫描

**流水线 B（Harness 模式，推荐）**：

```bash
python3 scripts/kit-scan-test/scan_kit.py \
  -kit "Ability Kit" \
  -js_decl_path /path/to/interface_sdk-js \
  -repo_base /path/to/DataBases \
  -out_path ./scan_out \
  -api_error_code_doc_path /path/to/docs \
  -c_decl_path /path/to/interface_sdk_c
```

**流水线 A（单体模式）**：

```bash
python3 scripts/kit-scan/scan_kit.py \
  -kit "Ability Kit" \
  -js_decl_path /path/to/interface_sdk-js \
  -repo_base /path/to/DataBases \
  -out_path ./scan_out \
  -c_decl_path /path/to/interface_sdk_c
```

### 批量扫描

```bash
# 预览所有 Kit 的命令（不执行）
python3 scripts/kit-scan-test/batch_scan_all.py -n

# 只扫描特定 Kit（支持子串匹配）
python3 scripts/kit-scan-test/batch_scan_all.py -kits "Ability" "Network"

# 跳过已提取的数据，直接审计
python3 scripts/kit-scan-test/scan_kit.py -kit "Ability Kit" ... -skip_extract
```

## 两种流水线

### 流水线 A：单体模式

```
scan_kit.py
  │
  ├─ Step 1: claude -p "/kit-api-extract ..."     # 1 次 Claude 调用
  │           → 输出 api.jsonl + impl_api.jsonl
  │
  ├─ Step 2: batch_pipeline 按 batch_size=40 切分数据
  │
  ├─ Step 3: 逐 batch 调用 claude -p "/api-level-scan ..."  # N 次 Claude 调用
  │           → 每个 batch 输出 api_scan_findings.jsonl
  │
  └─ Step 4: 合并所有 batch 结果 → merged_api_scan_findings.jsonl/.xlsx
```

**参数**：

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `-kit` | 是 | - | Kit 名称，如 "Ability Kit" |
| `-js_decl_path` | 是 | - | interface_sdk-js 目录 |
| `-repo_base` | 是 | - | DataBases 目录 |
| `-out_path` | 是 | - | 输出根目录 |
| `-batch_size` | 否 | 40 | 每个 batch 的 API 数量 |
| `-c_decl_path` | 否 | - | interface_sdk-c 目录（启用 C API 提取） |
| `-skip_extract` | 否 | false | 跳过 API 提取步骤 |

### 流水线 B：Harness 模式

```
scan_kit.py
  │
  ├─ Step 1: claude -p "/kit-api-extract ..."     # 1 次 Claude 调用
  │           → 输出 api.jsonl + impl_api.jsonl
  │
  ├─ Step 2: data_prepare 合并为 merged_input.jsonl
  │
  ├─ Step 3: claude -p "/api-level-scan-test ..."  # 1 次 Claude 调用（技能内部调度）
  │           → 技能内部按策略分组
  │           → 并行派发审计 subagent（通过 Agent tool）
  │           → 派发校验 subagent 合并、去重、自校验
  │           → 输出 api_scan_findings.jsonl + api_call_chains.json + summary.md
  │
  └─ Step 4: 转换 XLSX
```

**参数**（在流水线 A 基础上新增）：

| 参数 | 默认 | 说明 |
|------|------|------|
| `-max_parallel` | 3 | 并行 subagent 最大数量（1-5） |
| `-group_strategy` | auto | 分组策略：module / fixed / auto |
| `-group_size` | 80 | fixed 策略下每组 API 数量 |
| `-rule_xlsx` | - | 自定义规则 XLSX 文件 |
| `-api_error_code_doc_path` | - | 错误码文档目录 |
| `-c_decl_path` | - | interface_sdk-c 目录（启用 C API 提取） |
| `-skip_extract` | false | 跳过 API 提取步骤 |

**分组策略详解**：

| 策略 | 说明 |
|------|------|
| `module` | 按 `module_name` 分组；大模块（>200 API）拆为 ~100 的子组；小模块（<10 API）按 `impl_repo_path` 合并 |
| `fixed` | 按 `group_size` 均匀切分 |
| `auto` | 先尝试 module，若平均组大小在 20-200 之间则用 module，否则回退 fixed |

**断点续跑**：Harness 检查 `{out_path}/api_scan/subagent_results/status_{i}.json`，若 `status == "completed"` 则跳过该组。

### 差异对比

| 维度 | 流水线 A（单体模式） | 流水线 B（Harness 模式） |
|------|----------------------|--------------------------|
| 脚本目录 | `scripts/kit-scan/` | `scripts/kit-scan-test/` |
| 并行执行者 | Python 外部串行调用 N 个 claude 进程 | Claude 内部通过 Agent tool 并行调度 subagent |
| Claude 调用次数 | N+1 次（1 提取 + N 审计） | 2 次（1 提取 + 1 审计） |
| 每批 API 数量 | 固定 40 | 可配置（默认 80） |
| 分组策略 | 无，均匀切分 | module / fixed / auto |
| 重试机制 | 无 | 失败自动重试 3 次 |
| 断点续跑 | 检查结果文件是否存在 | 检查 `status_{i}.json` |
| 结果合并 | Python 脚本拼接 JSONL | validation subagent 合并 + 去重 + 自校验 |
| 错误码文档 | 不支持 | 支持（`-api_error_code_doc_path`） |
| 适用场景 | 小 Kit（<100 API）、简单流程 | 大 Kit、生产环境 |

**推荐**：新用户优先使用流水线 B（Harness 模式），更稳定且支持断点续跑。

## 调用逻辑

### 完整调用链

```
batch_scan_all.py                          # 从 kit_compont.csv 读取 Kit 列表
  │
  └─ subprocess.run(scan_kit.py ...)       # 每个 Kit 调用一次
       │
       ├─ claude_runner → common/runner.py → run_agent()
       │    └─ subprocess.Popen(backend_cmd)              # claude 或 opencode
       │         claude: ["claude", "-p", prompt, "--allowedTools", ...]
       │         opencode: ["opencode", "run", prompt]
       │
       ├─ [流水线 A] batch_pipeline.prepare_batches()     # 切分 batch
       │    └─ claude_runner.run_batch_scan()              # 逐 batch 调用
       │         └─ run_agent("/api-level-scan ...") × N   # 指数退避重试
       │    └─ batch_pipeline.merge_batch_results()        # 合并结果
       │
       └─ [流水线 B] data_prepare.prepare_merged_input()  # 合并为单文件
            └─ claude_runner.run_claude_command("/api-level-scan-test ...")
                 └─ run_agent(..., retry_strategy="append_prompt")
                 └─ 技能内部自行分组 + 调度 subagent + 合并结果
```

### batch_scan_all.py 通用参数

| 参数 | 说明 |
|------|------|
| `-n` / `--dry-run` | 仅打印命令不执行 |
| `-kits word1 word2` | 按子串过滤 Kit 名称 |
| `-skip_extract` | 跳过 API 提取步骤 |

## 适配不同 Agent 工具

所有流水线通过 `scripts/common/runner.py` 统一管理 Agent CLI 调用，支持 **Claude Code CLI** 和 **OpenCode CLI** 两种后端。

### 快速切换后端

编辑 `scripts/scan_config.json`，将 `backend` 改为目标后端：

```json
{
  "backend": "opencode",    // "claude" 或 "opencode"
  "retry_strategy": "exponential"  // "exponential" 或 "append_prompt"
}
```

当前 kit-scan-test 的 `claude_runner.py` 已自动读取此配置。

### 配置文件

`scripts/scan_config.json` 集中管理所有参数，CLI 参数可覆盖配置文件值：

```json
{
  "backend": "claude",
  "max_retries": 3,
  "base_retry_delay": 10.0,
  "retry_strategy": "exponential",
  "batch_size": 30,
  "max_parallel": 3,
  "js_decl_path": "/path/to/interface_sdk-js",
  "c_decl_path": "/path/to/interface_sdk_c",
  "repo_base": "/path/to/DataBases",
  "out_path": "/path/to/scan_out",
  "doc_path": "/path/to/docs"
}
```

### 共享模块说明

| 模块 | 路径 | 职责 |
|------|------|------|
| `runner.py` | `scripts/common/runner.py` | 统一 Agent CLI 调用，支持 claude/opencode 双后端，工厂函数模式 |
| `data_utils.py` | `scripts/common/data_utils.py` | JSONL 加载/分割/匹配/XLSX 转换 |
| `kit_utils.py` | `scripts/common/kit_utils.py` | Kit 名称规范化、声明文件查找、CSV 读取 |
| `config.py` | `scripts/common/config.py` | JSON 配置加载 + CLI 参数覆盖 |

### 两种重试策略

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `exponential` | 指数退避（10s → 20s → 40s），同一 prompt 重试 | kit-scan、component-scan |
| `append_prompt` | 每次重试在 prompt 末尾追加提示语 | kit-scan-test |

### 支持的后端

| 后端 | CLI 命令 | 配置值 |
|------|----------|--------|
| Claude Code | `claude -p <prompt> --allowedTools <tools>` | `"backend": "claude"` |
| OpenCode | `opencode run <prompt>` | `"backend": "opencode"` |

### 工具说明

| 工具 | 用途 | 必要性 |
|------|------|--------|
| `Bash` | 执行 Shell 命令（运行 Python 脚本等） | 必需 |
| `Read` | 读取文件内容 | 必需 |
| `Edit` / `Write` | 写入输出文件 | 必需 |
| `Grep` / `Glob` | 搜索代码 | 必需 |
| `Python` | 执行 Python 代码 | 必需 |
| `Agent` | 派发 subagent（Harness 模式核心） | 流水线 B 必需，流水线 A 不需要 |
| `Find` / `Wc` / `Search` | 辅助搜索 | 建议保留 |

### 修改步骤

1. **替换 CLI 命令**：将 `CLAUDE_CLI` 改为目标命令名（如 `"my-agent"`）
2. **调整命令行参数**：当前使用 `["claude", "-p", prompt, "--allowedTools", tools]` 格式。若新 CLI 使用不同的参数格式（如 `--prompt` 代替 `-p`），需同步修改 `_run_once()` 或 `run_claude_command()` 中的 `cmd` 构建逻辑
3. **调整工具列表**：修改 `ALLOWED_TOOLS` 以匹配新 Agent 支持的工具集

**注意事项**：
- 若新 Agent 不支持 `Agent` 工具，**流水线 B（Harness 模式）将无法工作**，只能使用流水线 A
- Skill 的 SKILL.md 中引用了 Claude 特有的 Agent tool 调用方式，更换 Agent 后需同步修改 prompt 模板

## 路径配置

### 配置文件（推荐）

路径参数集中管理在 `scripts/scan_config.json`，所有流水线脚本自动读取：

```json
{
  "backend": "claude",
  "max_retries": 3,
  "js_decl_path": "/path/to/interface_sdk-js",
  "c_decl_path": "/path/to/interface_sdk_c",
  "repo_base": "/path/to/DataBases",
  "out_path": "/path/to/scan_out",
  "doc_path": "/path/to/docs"
}
```

修改配置文件即可全局生效，无需逐一修改各脚本。CLI 参数会覆盖配置文件中的对应值。

### CLI 参数路径

| 参数 | 含义 | 示例 |
|------|------|------|
| `-js_decl_path` | interface_sdk-js 仓库根目录 | `/path/to/interface_sdk-js` |
| `-c_decl_path` | interface_sdk-c 仓库根目录（可选，启用 C API 提取） | `/path/to/interface_sdk_c` |
| `-repo_base` | DataBases 目录（含各部件源码仓库） | `/path/to/DataBases` |
| `-out_path` | 输出根目录，每个 Kit 在其下创建子目录 | `./scan_out` |

### Kit 声明文件查找逻辑

`scan_kit.py` 按以下顺序查找 Kit 声明文件（Kit 名称去除空格后匹配）：

1. `{js_decl_path}/kits/@kit.{KitName}.d.ts`
2. `{js_decl_path}/kits/@kit.{KitName}.d.ets`
3. `{js_decl_path}/kits/@kit.{KitName}.static.d.ets`

例如 `"Ability Kit"` → 查找 `@kit.AbilityKit.d.ts`

### 输出目录结构

**流水线 A 输出**：
```
{out_path}/{KitName}/
  api.jsonl                              # 提取的 API 声明
  impl_api.jsonl                         # 含实现路径的 API
  batch_result/
    input/batch_0.jsonl ...              # 分批输入
    batch_0/api_scan/api_scan_findings.jsonl  # 各 batch 审计结果
    ...
    merged_api_scan_findings.jsonl       # 合并结果
    merged_api_scan_findings.xlsx        # Excel 版本
```

**流水线 B 输出**：
```
{out_path}/{KitName}/
  api.jsonl                              # 提取的 API 声明
  impl_api.jsonl                         # 含实现路径的 API
  merged_input.jsonl                     # 合并后的审计输入
  api_scan/
    active_rules.json                    # 激活的审计规则
    groups/group_1.jsonl ...             # 分组输入
    subagent_results/                    # subagent 逐组输出
      raw_findings_1.json
      call_chains_1.json
      status_1.json
    api_scan_findings.jsonl              # 最终审计结果
    api_scan_findings.xlsx               # Excel 版本
    api_call_chains.json                 # 调用链
    api_scan_summary.md                  # 汇总报告
    validation_status.json               # 校验状态
```

## Skill 参考

### kit-api-extract — API 提取与实现定位

| 属性 | 值 |
|------|-----|
| 触发方式 | `/kit-api-extract` |
| 参数 | `kit_name`, `js_sdk_path`, `c_sdk_path`（可选）, `databases_dir`, `output_dir` |
| 输出 | `api.jsonl`（声明数据）+ `impl_api.jsonl`（含实现链路） |

执行 6 个阶段：
1. `extract_kit_api.py` 从 `.d.ts` 提取 JS API 声明，若提供 `c_sdk_path` 则同时从 `.h` 提取 C API 声明
2. `extract_component_map.py` 结构关系抽取（bundle.json/BUILD.gn/nm_modname 映射）
3. `extract_c_impl_map.py` C API 实现映射（仅当有 C API 时运行）
4. 按 module 分组，派发 Explore subagent（最多 3 并行）探索 NAPI→Framework→Implementation 链路
5. `merge_agent_results.py` 合并为 `impl_api.jsonl`
6. 重试：NAPI 覆盖率 < 90% 时再探索（最多 2 轮），生成 `api_extraction_report.md`

### api-level-scan — 单体模式审计

| 属性 | 值 |
|------|-----|
| 触发方式 | `/api-level-scan` |
| 参数 | `api_input`（JSONL）, `repo_base`, `out_path`, `rule_xlsx`（可选） |
| 输出 | `api_scan_findings.jsonl` + `api_call_chains.json` + `api_scan_summary.md` |

7 步执行：规则加载 → 解析输入 → 逐 API 审计 → 自校验 → 分类验证 → 生成输出 → 输出验证。无 subagent，Claude 自身完成全部审计。

### api-level-scan-test — Harness 模式审计

| 属性 | 值 |
|------|-----|
| 触发方式 | `/api-level-scan-test` |
| 参数 | 在 api-level-scan 基础上增加 `max_parallel`, `group_strategy`, `group_size`, `api_error_code_doc_path`, `kit_name` |
| 输出 | 同 api-level-scan + `active_rules.json`, `validation_status.json` |

关键区别：API ≤ 30 时 Direct 模式（直接审计），API > 30 时 Harness 模式（分组 → 并行审计 subagent → 校验 subagent）。

## 审计规则

16 条规则，定义在 `config/rule.json`，分为 3 个系列：

### APITEST.ERRORCODE.01 — 错误码定义规范（11 条）

| ID | 描述 |
|----|------|
| 01.001 | @permission API 须定义 201（鉴权失败） |
| 01.002 | @systemapi API 须定义 202（非系统应用调用） |
| 01.003 | 新增 API（since≥24）禁止使用 401 |
| 01.004 | 设备不支持须返回 801 |
| 01.005 | 模拟器不支持须返回 804 |
| 01.006 | 禁止篡改系统保留错误码（1XX-9XX）语义 |
| 01.007 | 自定义错误码须为 SysCap编号+5位序号 |
| 01.008 | 禁止非标准错误码（-1、null 等） |
| 01.009 | 跨语言接口错误码须一致 |
| 01.010 | BusinessError 字段名须一致（code/message） |
| 01.011 | 错误码 code 类型须为 number |

### APITEST.ERRORCODE.02 — 错误码使用规范（4 条）

| ID | 描述 |
|----|------|
| 02.001 | 错误码须与触发原因一致 |
| 02.002 | 禁止一个错误码对应多种场景 |
| 02.003 | 异常分支必须返回错误码，禁止静默失败 |
| 02.004 | 文档与代码实现须一致 |

### APITEST.ERRORCODE.03 — 错误信息质量（2 条）

| ID | 描述 |
|----|------|
| 03.001 | 错误 message 须能帮助定位和解决问题 |
| 03.002 | 文档中错误码须有可操作的处理步骤 |

## 输出格式

### 最终输出：api_scan_findings.jsonl

每行一个 JSON 对象，包含 13 个字段：

| 字段 | 说明 |
|------|------|
| `kit` | Kit 名称 |
| `部件` | 部件名称 |
| `编号` | 规则 ID（如 01.001） |
| `问题描述` | 问题概述 |
| `发现详情说明` | 详细描述 |
| `代码文件` | 问题代码文件路径 |
| `代码行位置` | 行号 |
| `受影响的api` | 受影响的 API 名称 |
| `api声明` | API 声明代码 |
| `声明文件位置` | 声明文件路径 |
| `修改建议` | 修复建议 |
| `问题严重等级` | 严重/高/中/低 |
| `影响的错误码` | 相关错误码 |

### 严重等级

| 等级 | 示例场景 |
|------|----------|
| 严重 | 静默失败、字符串类型错误码、一对多映射 |
| 高 | @permission 缺少 201、错误信息为空、跨语言不一致 |
| 中 | 文档与实现不一致、消息过于泛泛 |
| 低 | 命名规范、参数顺序 |

## FAQ

**Q: 报错 "未找到 claude CLI"**

确认 Claude Code CLI 已安装并在 PATH 中：`which claude`。若使用 OpenCode 后端，确认 `opencode` 在 PATH 中，并在 `scripts/scan_config.json` 中设置 `"backend": "opencode"`。

**Q: Kit 声明文件找不到**

检查 `-js_decl_path` 是否指向 `interface_sdk-js` 根目录（非子目录）。Kit 名称区分大小写，空格会被自动去除（"Ability Kit" → "AbilityKit"）。

**Q: 如何续跑中断的任务**

加 `-skip_extract` 跳过提取步骤。流水线 A 自动跳过已有结果的 batch；流水线 B 通过 `status_{i}.json` 跳过已完成的 subagent。

**Q: 如何添加/修改审计规则**

编辑 `config/rule.json`（两个 Skill 目录下各一份，需保持同步），或通过 `-rule_xlsx` 提供自定义规则 XLSX 文件。

**Q: 流水线 B 的 subagent 全部失败**

`common/runner.py` 会自动重试（默认 3 次），重试策略由 `scan_config.json` 的 `retry_strategy` 控制。若仍失败，检查 Agent CLI 是否正常，或减少 `-max_parallel` 降低并发。

**Q: 如何只扫描特定 Kit**

使用 `batch_scan_all.py -kits "Ability" "Network"` 按子串过滤，或直接运行 `scan_kit.py -kit "具体Kit名"`。

**Q: 如何更换 Python 环境**

`batch_scan_all.py` 使用 `sys.executable` 继承当前 Python 环境。确保运行时激活了正确的虚拟环境。

**Q: 如何修改输出格式**

JSONL → XLSX 的转换逻辑统一在 `scripts/common/data_utils.py` 的 `jsonl_to_xlsx()` 函数中，可自定义列名和格式。
