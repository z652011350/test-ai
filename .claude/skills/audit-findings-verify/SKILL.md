---
name: audit-findings-verify
description: >
  校验 HarmonyOS/OpenHarmony API 审计发现（JSONL 格式）的准确性。
  逐条核查每条发现是否属实：读取声明文件验证 JSDoc 标签（@since、@systemapi、@permission），
  读取实现文件验证代码位置和问题真实性，对照规则定义判定发现是否为误报。
  输出过滤后的 JSONL 文件和校验报告。
  触发场景：校验审计结果、核查扫描发现、验证 findings 准确性、过滤误报。
---

## 参数

```json
{
  "findings_input": "JSONL 文件路径（待校验的审计发现）",
  "repo_base": "代码仓库基础目录（包含各部件仓库和声明文件的根目录）",
  "rule_file": "规则文件路径（可选，默认使用 api-level-scan 的 config/rule.json）",
  "out_path": "输出目录"
}
```

| 参数 | 必需 | 说明 |
|------|------|------|
| `findings_input` | 是 | JSONL 文件路径，每行一条审计发现（13 个字段） |
| `repo_base` | 是 | 代码仓库基础目录，包含各 OpenHarmony 部件仓库和 interface_sdk-js |
| `rule_file` | 否 | 规则 JSON 文件路径，默认使用 `api-level-scan/config/rule.json` |
| `out_path` | 是 | 输出目录 |

---

## 输入格式

每行一个 JSON 对象，包含 13 个字段：

```json
{"kit":"AbilityKit","部件":"bundlemanager_bundle_framework","编号":"APITEST.ERRORCODE.02.003","问题描述":"规则描述","发现详情说明":"[调用链 xxx] 问题详情","代码文件":"path/to/file.cpp","代码行位置":"4717","受影响的api":"getBundleInfoForSelfSync","api声明":"function getBundleInfoForSelfSync(bundleFlags: int): BundleInfo","声明文件位置":"@ohos.bundle.bundleManager.d.ts","修改建议":"修改建议","问题严重等级":"严重","影响的错误码":""}
```

---

## 校验原则

校验的核心目标是 **判定每条发现是否属实**。校验时遵循以下原则：

1. **声明文件优先**：涉及 JSDoc 标签（@since、@systemapi、@permission、@throws）的判定，必须从声明文件（.d.ts/.d.ets/.h）中实际读取，禁止推断
2. **精确匹配重载版本**：同一方法名的不同重载版本可能有不同的 JSDoc 标签，必须根据 `api声明` 字段精确匹配对应重载
3. **@since 版本号取字面值**：`@since 23` 就是 23，`@since 23 static` 仍然是 23，"static" 只表示 SDK 链接模式
4. **证据必须可验证**：代码文件路径和行号必须能在仓库中定位到实际代码
5. **规则前提条件必须满足**：每条规则都有前提条件（如 01.001 需要 @permission 标签），前提不满足则该发现属于误报

---

## 执行步骤

### Phase A：准备

#### Step 1. 加载规则

读取 `rule_file`（默认 `{{skill_path}}/../api-level-scan/config/rule.json`），建立规则 ID 到规则内容的映射。理解每条规则的 `id`、`description`、`instructions`。

重点关注以下规则的前提条件：

| 规则 ID | 前提条件 | 判定方法 |
|---------|---------|---------|
| 01.001 | API 的 JSDoc 中**确实存在** `@permission` 标签 | 读取声明文件验证 |
| 01.002 | API 的 JSDoc 中**确实存在** `@systemapi` 标签 | 读取声明文件验证 |
| 01.003 | API 的 JSDoc 中**最大的** `@since` 版本号 **>= 24** | 读取声明文件验证，版本号取字面数值 |
| 01.004 | API 存在真实设备硬件能力不支持场景 | 需分析实现代码 |
| 01.005 | API 存在模拟器不支持场景 | 需分析实现代码 |
| 其他规则 | 无特殊前提条件 | — |

#### Step 2. 读取待校验文件

读取 `findings_input`，逐行解析为 JSON 对象，记录总条数 N。

---

### Phase B：逐条校验

#### Step 3. 对每条发现执行校验

对 N 条发现中的每一条，按以下流程校验：

**3.1 基础校验**

- 检查 13 个必需字段是否完整（kit、部件、编号、问题描述、发现详情说明、代码文件、代码行位置、受影响的api、api声明、声明文件位置、修改建议、问题严重等级、影响的错误码）
- 检查 `编号` 是否在规则映射中存在
- 检查 `问题严重等级` 是否为 `严重`/`高`/`中`/`低` 之一

**3.2 规则前提条件校验（针对规则 01.001/01.002/01.003）**

对于规则 01.001、01.002、01.003 的发现，必须从声明文件验证前提条件：

a) **定位声明文件**
   - 根据 `声明文件位置` 字段，在 `{repo_base}` 中搜索对应文件
   - 常见路径模式：`api/interface_sdk-js/api/` 下的 `.d.ts` 或 `.d.ets` 文件

b) **定位目标 API 的 JSDoc 块**
   - 根据 `api声明` 字段，在声明文件中找到匹配的函数签名
   - 读取该签名上方的 `/** ... */` 注释块
   - 如果同一方法名有多个重载，必须精确匹配 `api声明` 对应的重载版本

c) **提取并验证标签**
   - 从 JSDoc 块中提取 `@since`、`@systemapi`、`@permission`、`@throws` 标签
   - 对于规则 01.001：验证 `@permission` 标签确实存在
   - 对于规则 01.002：验证 `@systemapi` 标签确实存在（注意区分同名方法的不同重载版本）
   - 对于规则 01.003：提取所有 `@since` 行，取最大版本号，验证是否 >= 24

d) **校验判定**
   - 前提条件不满足 → 标记为 **误报（false_positive）**
   - 前提条件满足 → 继续证据校验

**3.3 代码证据校验**

a) **验证代码文件存在**
   - 根据 `代码文件` 字段（可能为逗号分隔的多个文件），在 `{repo_base}` 中搜索每个文件
   - 如果文件不存在，标记为 **证据不足（ unverifiable）**

b) **验证代码行位置**
   - 读取对应文件，检查 `代码行位置` 指定的行号附近（±5 行）是否存在发现描述中提到的代码模式
   - 验证要点：
     - 发现描述提到的函数名是否存在
     - 发现描述提到的错误码或错误处理逻辑是否存在
     - 发现描述提到的代码模式（如 return nullptr、napi_throw_error 等）是否存在

c) **语义校验**
   - 检查发现描述中的结论是否与代码实际行为一致
   - 例如：发现称"静默返回 undefined"，需验证该分支确实未调用 throw/reject 相关函数

**3.4 交叉校验（针对发现间冲突）**

检查是否存在以下情况：
- 同一 API、同一规则有多条发现，内容相互矛盾
- 发现的 `api声明` 与 `受影响的api` 不匹配
- 发现的 `部件` 与 `代码文件` 路径不匹配

**3.5 输出校验结果**

对每条发现生成校验记录：

```json
{
  "original_index": 0,
  "rule_id": "APITEST.ERRORCODE.01.003",
  "affected_api": "getLaunchWantForBundleSync",
  "verdict": "confirmed",
  "reason": "声明文件 @ohos.bundle.bundleManager.d.ts 第59行附近，getLaunchWantForBundleSync 的 @since 24 版本确实声明了 @throws 401",
  "jsdoc_tags": {
    "since_max": 24,
    "has_permission": false,
    "has_systemapi": false,
    "throws_codes": ["201", "401", "17700001"]
  }
}
```

`verdict` 取值：
- `confirmed`：发现属实，问题确实存在
- `false_positive`：误报，规则前提条件不满足或问题不存在
- `unverifiable`：无法验证（代码文件缺失或声明文件无法定位），保守保留
- `partially_correct`：部分正确（如行号偏差但问题确实存在）

---

### Phase C：生成输出

#### Step 4. 合并输出

将校验结果分为三组：

- **confirmed + partially_correct**：保留到最终输出
- **false_positive**：排除，记录到误报列表
- **unverifiable**：保留到最终输出，但标记为需人工复核

生成以下文件到 `{out_path}/`：

| 文件 | 说明 |
|------|------|
| `verified_findings.jsonl` | 过滤后的 JSONL，仅包含 confirmed 和 partially_correct 的发现（保持原始 13 字段格式） |
| `false_positive_findings.jsonl` | 被判定为误报的发现，每行附加 `verdict` 和 `reason` 字段 |
| `verification_report.json` | 校验统计报告 |

**verification_report.json 结构**：

```json
{
  "input_file": "原始文件路径",
  "total_findings": 313,
  "confirmed": 280,
  "false_positive": 25,
  "unverifiable": 5,
  "partially_correct": 3,
  "false_positive_by_rule": {
    "APITEST.ERRORCODE.01.003": 20,
    "APITEST.ERRORCODE.01.002": 5
  },
  "verification_details": [
    {
      "original_index": 0,
      "rule_id": "...",
      "affected_api": "...",
      "verdict": "...",
      "reason": "..."
    }
  ]
}
```

#### Step 5. 打印摘要

输出校验摘要到对话：

```
校验完成：
- 总发现数: 313
- 确认属实: 280 (89.5%)
- 误报: 25 (8.0%)  ← 已过滤
  - 01.003: 20 条 (@since < 24)
  - 01.002: 5 条 (无 @systemapi 标签)
- 无法验证: 5 (1.6%)
- 部分正确: 3 (1.0%)
输出文件:
  - verified_findings.jsonl (280 条)
  - false_positive_findings.jsonl (25 条)
  - verification_report.json
```

---

## 执行顺序（严格按序）

1. 加载规则 — 读取 rule.json 建立规则映射
2. 读取待校验文件 — 逐行解析 JSONL
3. 逐条校验 — 基础校验 → 前提条件校验 → 证据校验 → 交叉校验
4. 合并输出 — 生成过滤后的 JSONL 和校验报告
5. 打印摘要 — 输出校验统计

---

## 关键校验细节

### @since 版本号判定规则

```
@since 9             → 版本号 9
@since 14 dynamic    → 版本号 14
@since 23 static     → 版本号 23（不是 24）
@since 24            → 版本号 24
@since 24 dynamic&static → 版本号 24

多个 @since 时取最大版本号作为判定依据
```

### @systemapi 标签判定规则

```
同一方法名的不同重载版本可能有不同标签：
- startAbilityByCall(want)              → 无 @systemapi
- startAbilityByCallWithAccount(...)    → 有 @systemapi
必须根据 api声明 字段精确匹配对应重载版本
禁止从实现代码中的 CHECK_IS_SYSTEM_APP 等宏反推标签存在
```

### 代码位置验证容差

- 行号允许 ±10 行偏差（代码可能经过修改）
- 函数名必须能在文件中找到（但允许重载匹配偏差）
- 关键代码模式（如 return nullptr、napi_throw）必须在行号附近存在

---

## 注意事项

1. **声明文件搜索路径**：`{repo_base}/api/interface_sdk-js/api/` 目录是常见的声明文件位置
2. **repo_base 结构**：可能包含多个子目录（DataBases、api 等），需灵活搜索
3. **校验结果以保守为原则**：无法验证的发现应保留而非删除
4. **处理大量发现时**：每校验 50 条将中间结果刷新到文件
5. **发现中的 `声明文件位置`** 字段通常只有文件名（如 `@ohos.bundle.bundleManager.d.ts`），需在 repo_base 中搜索完整路径
6. **发现中的 `代码文件`** 字段是相对路径（如 `bundlemanager_bundle_framework/interfaces/kits/js/...`），需拼接 repo_base

---

## 禁止事项

- 禁止在未读取声明文件的情况下判定 @since、@systemapi、@permission 等标签存在
- 禁止将 @since 23 xxxx 映射为 24
- 禁止从实现代码反推 JSDoc 标签（如 CHECK_IS_SYSTEM_APP → @systemapi）
- 禁止删除 unverifiable 的发现，应保留并标记
- 禁止跳过任何一条发现，必须逐条校验
