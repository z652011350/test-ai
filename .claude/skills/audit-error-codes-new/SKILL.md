---
name: audit-error-codes-new
description: 审核 HarmonyOS/OpenHarmony 部件的错误码使用情况，分析 API 调用链路和异常分支触发点。
---

# Audit Error Codes

审核 HarmonyOS/OpenHarmony 部件（Component）的错误码使用情况，分析 API 调用链路和异常分支触发点。

## 术语

| 术语 | 说明 | 示例 |
|------|------|------|
| **Kit** | 面向开发者的 API 聚合层，由声明文件 `@kit.{Name}.d.ts` 定义 | Network Kit, Ability Kit, Image Kit |
| **Component (部件)** | 实际的源码仓库，实现 Kit 的部分功能。**本 skill 的分析单位** | `communication_netmanager_base`, `communication_netstack` |
| **映射关系** | 1 Kit = 1~N Components，定义在 `kit_compont.csv` | Network Kit → [communication_netmanager_base, communication_netstack, communication_netmanager_ext] |

> **注意**：本 skill 以**部件（Component）**为单位进行分析。一个 Kit 可能包含多个部件，需分别对每个部件调用本 skill。

## 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `component_path` | 是 | 部件目录路径（如 `/path/to/DataBases/communication_netmanager_base/`） |
| `kit_name` | 否 | Kit 名称（如 `Network Kit`），用于报告标题。若未提供则从路径推断 |
| `api_doc_path` | 否 | API 参考文档文件、目录或 URL |
| `api_error_doc_path` | 否 | API 错误码文档文件、目录或 URL |
| `analyze_depth` | 否 | 分析深度 `quick`/`medium`/`thorough`，默认 `thorough` |
| `out_path` | 否 | 最终报告保存路径，默认为 `component_path` |

**向后兼容**：若用户传入 `kit_path` 参数，自动映射为 `component_path`，并输出提示："注意：kit_path 参数已更名为 component_path，请后续使用新名称"

## 执行步骤

### 1. 初始化审核环境

**参数规范化**：
- 若参数中存在 `kit_path` 但无 `component_path`，将 `kit_path` 值赋给 `component_path`，并输出提示："注意：kit_path 参数已更名为 component_path，请后续使用新名称"
- 从 `component_path` 路径推断 component_name 用于报告标题（如 `/DataBases/communication_netmanager_base/` → `communication_netmanager_base`）

使用 TaskWrite 创建任务列表，跟踪以下步骤：
- 探索代码库结构
- 收集 API 清单（使用脚本提取）
- 分析错误码定义
- 分析 API 调用链路
- 分析错误码映射
- 识别常见问题模式
- 对比文档一致性
- 生成审核报告

### 2. 处理文档参数

如果 `api_error_doc_path`或`api_doc_path` 是 URL，使用 GetDoc.py 获取文档，下载至`{{component_path}}/error_doc`或`{{component_path}}/api_doc`：
首先检查`{{component_path}}/error_doc`或`{{component_path}}/api_doc`是否存在，若存在则无需重新调用爬虫
如api_error_doc_path则
```bash
cd /path/to/skills/audit-error-codes-new/scripts
python3 GetDoc.py "<URL>" -o {{component_path}}/error_doc -f markdown -w 3
```
必须确保 error_doc 存在，且全部下载完成时进行后续的分析，(全部下载完成时，会在对应目录下生成**CATALOG.md**文件，该文件是下载的全部错误码的目录文件)
每次等待的时间以比例为2进行递增，从4开始，即等待时间序列如下
4, 8, 16, 32, 64, .... ,4^k
k为第k次检查文档是否下载完成。
在确定文档下载完成以后再执行以后步骤

### 3. 探索代码库结构

**并行搜索关键文件类型**：
- `**/*errno*.h`, `**/*error*.h` (错误码定义)
- `**/napi_*.cpp`, `**/entry_point*.cpp` (NAPI 层)
- `**/*_helper.cpp` (Helper 层)
- `**/*_impl.cpp`, `**/*_utils.cpp` (Framework 层)
- `**/ndk/include/*.h` (NDK 层)

### 4. 收集 API 清单（必须使用脚本）

⚠️ **重要**: 必须使用脚本提取 API 清单，手动分析会遗漏大量 API。

**JS/NAPI 层 API**:
```bash
python extract_js_napi_api.py {{component_path}} -o {{out_path}}/js_api.json
```
- 分类：async/sync 方法、observer 方法、实例方法

**NDK 层 API**:
```bash
python extract_ndk_api.py {{component_path}} -o {{out_path}}/ndk_api.json
```
- 提取以 `OH_` 开头的 C 函数和类型定义

**输出文件**: 将 JSON 文件保存到 out_path 路径下，供后续分析使用。

### 5. 分析错误码定义（详细表格输出）

⚠️ **重要**: 错误码必须以详细表格形式输出，**成功码（0）不是错误码**，不应计入错误码统计。

读取错误码头文件，建立完整清单：

#### 5.1 C++ Native 层错误码

输出表格格式：
| 错误码名称 | 值 | 错误消息原文 | 说明 |
|-----------|---|-------------|------|
| [示例] | [值] | [错误消息原文] | [说明] |

#### 5.2 JS/NAPI 层错误码

输出表格格式：
| 错误码名称 | 值 | 错误消息原文 | 说明 |
|-----------|---|-------------|------|
| [示例] | [值] | [错误消息原文] | [说明] |

#### 5.3 NDK 层错误码

输出表格格式：
| 错误码名称 | 值 | 错误消息原文 | 说明 |
|-----------|---|-------------|------|
| [示例] | [值] | [错误消息原文] | [说明] |

### 6. 分析 API 调用链路

大型部件的调用链路分析工作量较大，建议使用 Task (Explore 子代理)：

```bash
Task(subagent_type="Explore", prompt="分析 {component_path} 的全部 API 完整调用链路...")
```

**输出要求**:
- 每个 API 的完整调用链路图
- 每一层的异常分支触发点
- 每个异常分支的错误码

### 7. 分析错误码映射

查找映射函数和映射表：
- `GetJsErrorCode`, `QueryRetMsg`, `GetErrorCode`
- `JS_ERROR_MAPS`, `ERROR_CODE_MAPPING`, `g_errNumMap`, `g_errStringMap`

**统计映射覆盖率**：
```
映射覆盖率 = (已映射错误码数量 / Native 错误码总数) * 100%
```

### 8. 识别常见问题模式

使用 Grep 搜索以下问题模式：

| 问题类型 | 搜索模式 | 描述 |
|---------|----------|------|
| 错误码转字符串 | `napi_throw_error.*to_string` | 错误码被转换为字符串 |
| 错误码精度降低 | `return.*\?.*:.*ERR_` | 三元操作符简化错误判断 |
| 异常分支未抛出 | `if (.*!= OK)` + `return;` | 只记录日志未抛出错误 |
| 非标准错误码 | `constexpr.*=-1[0-9]` | 使用负数错误码 |
| 硬编码错误码 | `\{[0-9]{6,}` | 直接使用数字而非常量 |

### 9. 对比文档（如果提供）

**关键原则：从开发者视角出发**

- ✅ 应该对比：C++ 错误码 → JS/NAPI 错误码 → 暴露给开发者的错误码
- ❌ 不应该对比：C++ 内部实现错误码与文档定义（开发者看不到）

**检查项**：
- 暴露给开发者的错误码是否在文档中定义(不需要考虑**通用错误码**是否在文档中定义)
- 错误码值是否一致
- 错误消息是否一致

**通用错误码**
| error code | 中文错误说明 | error message | 错误描述 | 可能原因|  处理步骤 |
| ---------- | ------------- | ---------- | ------- | ------ | ------ |
| 201 | 权限校验失败 | Permission verification failed. The application does not have the permission required to call the API. | 权限校验失败，应用无权限使用该API，需要申请权限。| 该错误码表示权限校验失败，通常为没有权限，却调用了需要权限的API。 | 请检查是否有调用API的权限。 |
| 202 | 系统API权限校验失败 | Permission verification failed. A non-system application calls a system API. | 权限校验失败，非系统应用使用了系统API。 | 非系统应用，使用了系统API，请校验是否使用了系统API。 | 请检查是否调用了系统API，并且去掉。 |
| 203 | 企业管理策略禁止使用此系统功能 | This function is prohibited by enterprise management policies. | 企业管理策略禁止使用此系统功能。 | 试图操作已被设备管理应用禁用的系统功能。 | 请使用getDisallowedPolicy接口检查该系统功能是否被禁用，并使用setDisallowedPolicy接口解除禁用状态 |
| 401 | 参数检查失败 | Parameter error. Possible causes: 1. Mandatory parameters are left unspecified; 2. Incorrect parameter types; 3. Parameter verification failed. | 1.必填参数为空。2.参数类型不正确。3.参数校验失败。无论是同步还是异步接口，此类异常大部分都通过同步的方式抛出。 | 1. 必选参数没有传入 2. 参数类型错误 (Type Error) 3. 参数数量错误 (Argument Count Error) 4. 空参数错误 (Null Argument Error) 5. 参数格式错误 (Format Error) 6. 参数值范围错误 (Value Range Error) | 请检查必选参数是否传入，或者传入的参数类型是否错误。对于参数校验失败，阅读参数规格约束，按照可能原因进行排查。 |
| 801 | 该设备不支持此API | Capability not supported. Failed to call the API due to limited device capabilities. | 该设备不支持此API，因此无法正常调用。 | 可能出现该错误码的场景为：该设备已支持该API所属的Syscap，但是并不支持此API。 | 应避免在该设备上使用此API，或在代码中通过判断来规避异常场景下应用在不同设备上运行所产生的影响。 |



### 10. 深入分析错误码与错误信息

#### 10.1 分析多对一映射问题

重点关注映射到同一 JS 错误码的多个 Native 错误码：

1. **识别多对一映射**：找出所有映射到同一 JS 错误码的 Native 错误码集合
2. **分析触发场景**：每个 Native 错误码的具体触发条件
3. **评估开发者可处理性**：判断开发者是否可以根据错误信息采取针对性措施

#### 10.2 分析错误信息完整性

对于每个暴露给开发者的错误码，检查：

1. **错误信息是否明确**：是否说明了具体的失败原因
2. **开发者可操作性**：开发者是否可以根据错误信息采取行动
3. **是否需要区分场景**：同一错误码下是否需要不同的错误信息

#### 10.3 输出错误码确认表（必须输出）

必须输出以下格式的错误码/信息确认点表格：

| native错误码 | 异常位置错误信息 | 对应的js api错误码 | js错误信息 | 当前错误信息对开发者的影响 | 是否建议直接提供相关错误信息给开发者 |
| --------- | -------- | ------------ | ------ | ------------- | ------------------ |
| [错误码] | [错误信息] | [JS错误码] | [JS错误信息] | [影响描述] | [是/否/已足够] |

**填写说明**：
- **native错误码**：Native 层定义的错误码常量名和值
- **异常位置错误信息**：代码中设置的错误信息字符串
- **对应的js api错误码**：映射后的 JS 层错误码数值
- **js错误信息**：文档中定义的错误信息
- **当前错误信息对开发者的影响**：开发者能否根据错误信息定位问题
- **是否建议直接提供相关错误信息给开发者**：
  - **是**：建议在错误信息中提供更详细的说明
  - **否**：属于内部实现细节，开发者无法处理
  - **部分**：部分场景需要提供更详细信息
  - **已足够**：当前错误信息已足够清晰
  - **已提供**：代码中已提供详细错误信息，但可能需要独立错误码

### 11. 生成详细报告

生成四个报告文件（文件名包含 component_name 或 kit_name）：

1. **ERROR_CODE_ANALYSIS_REPORT.md** - 错误码问题分析报告
2. **API_CALL_CHAIN_AND_EXCEPTION_REPORT.md** - API 调用链路和异常分支报告
3. **DOC_CONSISTENCY_REPORT.md** - 文档与代码一致性分析报告
4. **ERROR_CODE_MESSAGE.md** - 错误码与错误信息深度分析报告

报告模板参考 `templates/` 目录。

### 12. 验证所有报告文件是否符合要求

#### 检查项
1. 验证输出报告格式是否符合要求
2. 验证报告文件中的内容是否在代码中真实存在，若存在不正确的内容请去除
3. 抽取代码仓中发现的所有问题，额外形成一个问题总结报告**ISSUE_REPORT**

## 常见问题模式

### 问题 1：错误码被转换为字符串

**特征代码**:
```cpp
napi_throw_error(env, std::to_string(errCode).c_str(), "error message");
```

**影响**:
- JavaScript 层接收到字符串类型错误码，违反 API 规范

### 问题 2：错误码信息精度降低

**特征代码**:
```cpp
return decodeRet ? SUCCESS : ERR_IMAGE_DATA_UNSUPPORT;
```

**影响**:
- 不同失败原因映射到同一错误码，开发者无法区分

### 问题 3：异常分支未抛出错误码

**特征代码**:
```cpp
if (ret != OK) {
    LOGE("operation failed");
    return;  // 错误丢失
}
```

### 问题 4：异常分支抛出错误码但无错误信息

## 检查清单

### API 清单收集
- [ ] 使用 extract_js_napi_api.py 提取 JS/NAPI API
- [ ] 使用 extract_ndk_api.py 提取 NDK API
- [ ] API 清单保存到 out_path

### 错误码分析
- [ ] 找到并分析了所有错误码定义文件
- [ ] 建立了完整的错误码清单（C++、JS、NDK层）
- [ ] **暴露给开发者的错误码表格**
- [ ] **Native → JS 错误码映射表格**
- [ ] **错误消息映射表格**
- [ ] 分析了错误码映射函数
- [ ] 统计了映射覆盖率

### 调用链路分析
- [ ] 基于 API 清单分析调用链路 (所有api)
- [ ] 追踪了每个 API 的完整调用链路
- [ ] 识别了每一层的异常分支触发点
- [ ] 记录了每个异常分支的错误码

### 问题识别
- [ ] 识别了所有"错误码转换为字符串"的问题（精确数量）
- [ ] 识别了所有"错误码信息精度降低"的问题（精确数量）
- [ ] 识别了所有"异常分支未抛出错误码"的问题（精确数量）
- [ ] 所有问题均需要可溯源，文件路径，行号，问题代码片段

### 文档对比
- [ ] 对比了 API 参考文档（如果提供）
- [ ] 对比了错误码文档（如果提供）
- [ ] 验证了**暴露给开发者**的错误码与文档的一致性

### 错误码与错误信息分析
- [ ] 分析了多对一映射问题（多个 Native 错误码映射到同一 JS 错误码）
- [ ] 评估了每个错误码的开发者可处理性
- [ ] 输出了错误码/信息确认表（标准格式）
- [ ] 提供了改进建议和优先级

### 报告生成
- [ ] 生成了 {component_name}_ERROR_CODE_ANALYSIS_REPORT.md
- [ ] 生成了 {component_name}_API_CALL_CHAIN_AND_EXCEPTION_REPORT.md
- [ ] 生成了 {component_name}_DOC_CONSISTENCY_REPORT.md
- [ ] 生成了 {component_name}_ERROR_CODE_MESSAGE.md(重点)
- [ ] 生成了 {component_name}_ISSUE_REPORT.md
- [ ] 报告包含完整的错误码表格
- [ ] 报告包含完整的问题分析和位置信息

## 注意事项

1. **成功码不是错误码**：成功码（通常为 0）不应计入错误码统计，不应出现在错误码表格中
2. **必须使用脚本提取 API**：手动分析会遗漏大量 API，必须使用 extract_js_napi_api.py 和 extract_ndk_api.py
3. **报告解耦**：只指出问题和位置，不提供修复建议
4. **精确量化**：使用精确数字（268次、15处），避免"大量"、"多处"、"10+"等模糊描述
5. **详细表格**：所有错误码必须以详细表格形式输出，不可省略
6. **开发者视角**：关注暴露给 API 使用者的错误码，而非 C++ 内部实现细节
7. **文档对比谨慎**：只有实际对比后才能下一致性结论

## 相关工具

- **Glob**: 查找文件模式
- **Grep**: 搜索代码内容
- **Read**: 读取文件内容
- **Task (Explore 子代理)**: 深度代码分析
- **Bash**: 执行命令（如 scripts/GetDoc.py）
- **Write**: 生成报告文件
- **extract_js_napi_api.py**: 提取 JS/NAPI API 清单
- **extract_ndk_api.py**: 提取 NDK API 清单

## 参考资源

- **报告模板**: [templates/ERROR_CODE_ANALYSIS_REPORT_TEMPLATE.md](templates/ERROR_CODE_ANALYSIS_REPORT_TEMPLATE.md)
- **报告模板**: [templates/API_CALL_CHAIN_AND_EXCEPTION_REPORT_TEMPLATE.md](templates/API_CALL_CHAIN_AND_EXCEPTION_REPORT_TEMPLATE.md)
- **报告模板**: [templates/DOC_CONSISTENCY_REPORT_TEMPLATE.md](templates/DOC_CONSISTENCY_REPORT_TEMPLATE.md)
- **使用示例**: [references/EXAMPLES.md](references/EXAMPLES.md)
- **经验总结**: [references/LESSONS_LEARNED.md](references/LESSONS_LEARNED.md)

## 版本历史

- v5.0 (2026-04-14): Kit/Component 概念修正
  - **修正**：`kit_path` 参数更名为 `component_path`，明确本 skill 以部件为单位分析
  - **新增**：术语表，区分 Kit（开发者 API 聚合层）和 Component（源码仓库）
  - **向后兼容**：`kit_path` 自动映射为 `component_path`

- v4.0 (2026-02-23): 基于 communication_netmanager_base 审核经验重构
  - **新增**：必须使用脚本提取 API 清单
  - **修正**：成功码（0）不是错误码，不计入统计
  - **改进**：API 数量基于脚本提取，更准确

- v3.0 (2026-02-13): 重大重构
  - **新增**：三份独立报告输出（解耦修复建议）
  - **新增**：DOC_CONSISTENCY_REPORT 专门用于文档一致性分析
  - **新增**：templates 目录存放报告模板
  - **改进**：强调开发者视角的错误码分析
  - **改进**：报告只指出问题位置，不提供修复建议
  - 基于 multimedia_audio_framework 审核经验总结：
    - 文档使用 GetDoc.py 下载，保存到项目目录
    - API 文档包含 19 个页面，错误码文档定义 7 个错误码
    - 错误码转字符串问题（2 处）严重影响 API 规范

- v2.3-v2.0: 见 references/LESSONS_LEARNED.md
