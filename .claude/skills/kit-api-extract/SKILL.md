---
name: kit-api-extract
description: >
  提取指定 HarmonyOS/OpenHarmony Kit 的 API 声明，通过 Agent 深度探索每个 API 的完整实现链路
  （声明→NAPI映射→Framework声明→业务逻辑实现）。当用户需要对任意 Kit（如 MediaKit、NetworkKit、
  AudioKit、AbilityKit 等）进行 API 提取分析、实现代码定位、调用链追踪时使用此技能。
  触发词包括：Kit API 提取、模块映射、实现定位、API 分析、Kit 代码仓分析、声明文件解析、API 实现、
  调用链追踪。当用户提到某个 Kit 的名称并希望了解其 API 结构或找到实现代码时，也应触发此技能。
---

# Kit API 提取与深度实现定位

## 概述

本技能从 HarmonyOS/OpenHarmony 的 Kit 声明文件出发，完成四步分析流程：

1. **提取 API** — 通过脚本从 Kit 聚合声明文件中提取所有方法类型的 API
2. **结构关系抽取** — 通过脚本从部件仓中提取 bundle.json/BUILD.gn/nm_modname 的确定性映射关系
3. **深度实现探索** — 为每个模块派发 subagent，利用映射表指导探索，沿 NAPI→Framework→业务逻辑 4 层链路追踪每个 API 的完整实现
4. **汇总输出** — 合并结果并更新映射模式知识库

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| kit_name | string | 是 | Kit 名称，如 `MediaKit`、`AbilityKit`、`NetworkKit` |
| js_sdk_path | string | 是 | js 声明文件入口路径 |
| databases_dir | string | 是 | DataBases 目录路径|
| output_dir | string | 是 | 输出目录|

## 执行步骤

### Phase 1: 提取 API 声明

运行提取脚本，从 Kit 声明文件解析所有子模块并提取 API 声明。

```bash
# 提取指定 kit
python3 skills/kit-api-extract/scripts/extract_kit_api.py \
  -js {js_sdk_path} \
  -o {output_dir}/{kit_name} \
  --kit "{kit_display_name}"
```
输出: {output_dir}/{kit_name}/api.jsonl

**参数说明**:

| 参数 | 短写 | 说明 |
|------|------|------|
| `--js_decl_repo` | `-js` | JS/TS SDK 目录路径 (interface_sdk-js) |
| `--c_decl_repo` | `-c` | C SDK 目录路径 (interface_sdk_c) |
| `--output` | `-o` | 输出目录 (默认: output) |
| `--kit` | — | 仅输出指定 kit 的 API (如 "Ability Kit") |

**输出文件命名规则**:

| 用法 | 输出路径 |
|------|---------|
| 指定 `--kit "Ability Kit"` | `<output_dir>/api.jsonl` |

**输出格式**: `api.jsonl`，每行一个 API 声明：
```json
{"api_declaration":"function xxx(params): returnType","js_doc":"/** ... */","module_name":"@ohos.xxx","declaration_file":"api/@ohos.xxx.d.ts"}
```
获取到脚本输出后即可开始进行下一步的结构关系抽取。

### Phase 2: 结构关系抽取（确定性脚本）

运行关系抽取脚本，从部件仓中提取 bundle.json、BUILD.gn 和 nm_modname 的结构映射关系。

```bash
python3 skills/kit-api-extract/scripts/extract_component_map.py \
  --kit "{kit_display_name}" \
  --databases {databases_dir} \
  --csv skills/api-level-scan/assets/kit_compont.csv \
  -o {output_dir}/{kit_name}
```

输出: `{output_dir}/{kit_name}/component_map.json`

**映射表内容**：
- `components` — 每个部件的 bundle.json 元信息（subsystem、syscap、deps、fwk_group、inner_kits）
- `build_targets` — BUILD.gn 中 ohos_shared_library/js_declaration 等目标的 sources、deps、relative_install_dir
- `module_map` — `@ohos.X.Y` → nm_modname 入口文件路径 → 关联 BUILD.gn target 的确定性映射

Agent 在后续 Phase 3 的探索中应优先查阅此映射表：
- 通过 `module_map` 直接获取模块的 NAPI 入口文件路径，避免盲搜 nm_modname
- 通过 `related_targets` 获取 BUILD.gn target 的 sources 列表，快速定位所有实现文件
- 通过 `bundle.inner_kits` 获取 Framework 接口头文件列表

### Phase 3: Agent 深度实现探索

读取 `api.jsonl` 和 `component_map.json`，按 `module_name` 分组。
**为每个模块(或多个少量api的模块合并)派发一个 Explore 类型的 subagent**，执行以下 6 步探索流程。
**第i个 subagent 负责探索 module_name_i 下的所有 API**，并将结果以 JSONL 格式保存。
**启动每个subagent时，汇总之前的探索关键发现**，以便新 subagent 可以参考并避免重复劳动。

#### subagent 指令模板

为每个模块的 subagent 提供以下 prompt（替换如 `{{}}` 包裹的变量）：

```
你需要在 DataBases 目录中追踪模块 {{module_name}} 的所有 API 实现。
该模块的声明文件为 {{declaration_file}}，仅针对以下 API：
{{api_list}}

**结构映射表（来自 Phase 2 脚本输出）**：
{{module_map_entry}}
（如果上面的映射表为空，则表示该模块未在 component_map.json 中找到 nm_modname 入口，需要自行搜索）

请先读取 {{`reference/MAPPING_PATTERNS.md`的绝对路径}} 了解已知映射模式，然后严格按以下 6 步探索：

Step 1 — 理解 API 接口定义：
读取声明文件 {{declaration_file}}，理解每个 API 的函数签名、入参和返回类型。

Step 2 — 定位 NAPI 映射层：
**优先使用映射表**：如果映射表中已有该模块的 entry_file 和 related_targets，直接使用：
1. 读取 entry_file（nm_modname 入口文件），找到注册函数（register_func）
2. 从 related_targets 的 sources 列表中获取所有实现文件

**如果映射表中无该模块**，在 DataBases/ 下搜索该模块的 NAPI 插件源码。搜索策略（按优先级）：
1. 搜索 .nm_modname = "{{module_short_name}}" 定位模块注册入口（native_module.cpp）
2. 在找到的目录中搜索已知映射模式（参考 {{`reference/MAPPING_PATTERNS.md`的绝对路径}} ）
3. 若未找到，尝试以下非标准搜索：
   - BindNativeFunction / BindNativeFunctionInObj（OHOS 特有封装）
   - napi_property_descriptor 直接定义数组（不使用宏）
   - 纯 JS/ArkTS 模块（.js / .abc 文件，无 nm_register_func）
   - syscap → bundle.json 匹配定位代码仓后再搜索
4. 建立 JS 方法名 → C++ 函数名的映射关系

Step 3 — 追踪业务逻辑实现：
从 Step 2 找到的 C++ 函数出发，追踪调用链：
1. 找到 NAPI 函数体中调用的 Framework 接口（通常在 interfaces/kits/native/ 或 interfaces/inner_api/ 下的 .h 文件）
2. 找到 Framework 接口的实际实现（通常在 frameworks/native/ 下的 .cpp 文件）
3. 对于使用 Proxy/Stub 模式的接口，追踪到 Proxy 类的实现

Step 4 — 归纳代码路径：
对每个 API 输出完整的代码路径链：
- interface: declaration_file(声明文件相对路径)
- NAPI映射: napi_file_path(NAPI 文件相对路径)
- Framework接口声明: framework_header_path(Framework 声明文件相对路径)
- 业务逻辑实现: impl_cpp_path(业务逻辑实现文件相对路径)

请以 JSONL 格式保存结果则至{{output_dir}}/subagent_res/impl_api_subagent_{{i}}.jsonl，每个 API 一行json对象：
  {"api_declaration": "function xxx(params): returnType","module_name": "{{module_name}}","impl_api_name": "CppFuncName","impl_repo_path": "repo_name","declaration_file": "api/@ohos.xxx.d.ts","NAPI_map_file": "repo_name/path/to/napi_file.cpp","Framework_decl_file": "repo_name/path/to/framework.h","impl_file_path": "repo_name/path/to/impl.cpp"
  }

如果某个层无法定位，对应字段留空字符串 ""。必须保存

Step 5 - 校验输出文件的格式准确:
确保{{output_dir}}/subagent_res/impl_api_subagent_{{i}}.jsonl文件的格式正确，每行都是一个包含以下字段的 JSON 对象：

  {"api_declaration": "function xxx(params): returnType","module_name": "{{module_name}}","js_doc": "/** ... */","impl_api_name": "CppFuncName","impl_repo_path": "repo_name","declaration_file": "api/@ohos.xxx.d.ts","NAPI_map_file": "repo_name/path/to/napi_file.cpp","Framework_decl_file": "repo_name/path/to/framework.h","impl_file_path": "repo_name/path/to/impl.cpp"
  }

Step 6 - 记录探索过程中的关键发现:
报告本次探索过程中发现的所有关键线索和映射模式（如发现了新的 NAPI 映射模式，或某个 API 的特殊实现路径）
```

#### subagent 派发策略

- 按模块分组，每组一个 subagent
- 可并行派发多个 subagent（最多 3 个并行）
- 优先处理 API 数量多的模块
- 对于 import 但仅 re-export 类型/接口（无函数方法）的模块，跳过
- 对于 API 数量较少的模块（如 < 5 个 API），可合并到同一 subagent 中处理

### Phase 4: 汇总输出

1. 收集所有 subagent 保存的结果,采用`scripts/merge_results.py`脚本将所有agent的结果合并到一个文件 `impl_api.jsonl` 中
2. 写入 `impl_api.jsonl`，每行一个 JSON 对象:

```json
{
  "api_declaration": "function xxx(params): returnType",
  "module_name": "@ohos.xxx",
  "js_doc": "/** ... */",
  "impl_api_name": "CppFuncName",
  "impl_repo_path": "repo_name",
  "declaration_file": "api/@ohos.xxx.d.ts",
  "NAPI_map_file": "repo_name/path/to/napi_file.cpp",
  "Framework_decl_file": "repo_name/path/to/framework.h",
  "impl_file_path": "repo_name/path/to/impl.cpp"
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `api_declaration` | API 函数签名 |
| `module_name` | 模块路径（如 `@ohos.xxx`） |
| `js_doc` | API 的 JS Doc 注释 |
| `impl_api_name` | NAPI 层 C++ 函数名 |
| `impl_repo_path` | 实现代码仓目录名（如 `ability_ability_runtime`） |
| `declaration_file` | .d.ts 声明文件相对路径 |
| `NAPI_map_file` | NAPI 映射文件相对路径（含文件名） |
| `Framework_decl_file` | Framework 接口声明 .h 文件相对路径 |
| `impl_file_path` | 业务逻辑实现 .cpp 文件相对路径 |

3. **更新映射模式知识库**：检查探索过程中是否发现 `reference/MAPPING_PATTERNS.md` 中未记录的新映射模式，若有则按模板格式追加。

### Phase 5: 重试机制（覆盖率 < 90% 时触发）

**触发条件**：Phase 4 完成后，若 `NAPI_map_file` 覆盖率 < 90%，则自动触发重试。

**流程**：

1. 从 `impl_api.jsonl` 中筛选出 `NAPI_map_file` 为空或 `impl_api_name` 为空的所有 API
2. 按模块分组这些缺失 API
3. 为每组派发一个 Explore subagent，prompt 中**强调使用非标准搜索策略**：

```
以下模块的 API 在常规搜索（nm_modname、DECLARE_NAPI_FUNCTION）中未找到实现。
请在 DataBases/ 中使用更广泛的搜索策略查找。

模块: {{module_name}}（{n} 个未找到实现的 API）
API 列表: {api_list}

**必须尝试的搜索策略**（按优先级）：
1. 搜索 nm_modname 中去掉 @ohos. 前缀后的各种变体（如 xxx.yyy、application.Xxx、app.xxx）
2. 搜索 BindNativeFunction、BindNativeFunctionInObj、napi_wrap 等非宏注册模式
3. 搜索 napi_property_descriptor 中直接定义的属性数组（不使用 DECLARE_NAPI_FUNCTION 宏）
4. 搜索 .js 或 .abc 文件中的模块注册（纯 JS/ArkTS 模块）
5. 在 bundle.json 的 component.syscap 中搜索匹配，定位代码仓后手动搜索 API 名
6. 直接在代码仓中 grep API 方法名，查找任何可能的绑定点
7. 搜索 interfaces/kits/js/ 或 interfaces/kits/napi/ 下所有 .cpp 文件中的函数注册

对每个找到实现的 API，请同时记录你使用的搜索方法/模式（即你是怎么找到的）。
如果发现新的映射模式（不在 MAPPING_PATTERNS.md 中的），请特别标注。
```

4. 合并重试结果到 `impl_api.jsonl`
5. **汇报新发现的映射模式**：将重试过程中发现的新模式追加到 `reference/MAPPING_PATTERNS.md`

**终止条件**：重试最多 2 轮。若 2 轮后仍 < 95%，报告剩余缺失 API 并说明原因。

### Phase 6: 结果汇总

向用户报告：
- 提取的 API 总数和分布（按模块）
- 各层映射命中率统计（NAPI映射、Framework声明、业务实现）
- 新发现的映射模式（如有）
- 未能定位实现的 API 列表及可能原因
形成`api_extraction_report.md`保存至输出目录，内容包括上述统计和分析结果。

## 技术原理

### Kit 文件结构

每个 Kit 在 `api/interface_sdk-js/kits/@kit.{KitName}.d.ts` 中定义，这是一个聚合模块，通过 import 语句引用所有子模块：
```typescript
import xxx from '@ohos.xxx.yyy';
```

脚本解析这些 import 语句，找到每个子模块的声明文件（`.d.ts` 或 `.d.ets`），然后提取方法类型的 API。

### 典型实现链路

```
.d.ts 声明文件
    ↓ (NAPI 模块注册 nm_modname)
native_module.cpp — 模块入口，Init 函数
    ↓ (DECLARE_NAPI_FUNCTION / napi_create_function)
xxx_ability_napi.cpp — NAPI 函数实现，参数转换
    ↓ (调用 Framework 接口)
ability.h — Framework 接口声明
    ↓ (具体实现)
ability.cpp — 业务逻辑实现
    ↓ (可能通过 IPC)
ability_manager_proxy.cpp — Proxy/Stub IPC 通信
```

### 代码仓常见目录结构

```
{repo_name}/
├── frameworks/
│   ├── js/napi/          # NAPI 层（JS→C++ 桥接）
│   └── native/           # C++ 业务逻辑实现
├── interfaces/
│   ├── kits/native/      # 公开 Native API 头文件
│   ├── inner_api/        # 内部 API 头文件
│   └── kits/napi/        # 部分 NAPI 实现
├── services/             # 系统服务实现
└── bundle.json           # 部件配置（含 syscap）
```

## 映射模式知识库

历史映射模式记录在 `reference/MAPPING_PATTERNS.md` 中，包含：
- DECLARE_NAPI_FUNCTION 宏注册
- napi_create_function 动态注册
- nm_modname 模块名注册
- napi_define_class 类注册
- napi_define_properties 批量导出

每次运行后需检查并更新此文件。
