# Audit Error Codes Agent Team 设计

## 概述

针对 HarmonyOS/OpenHarmony **部件（Component）**设计一个高效的 agent team，用于执行错误码白盒审核。

> **注意**：本设计以**部件**为分析单位。一个 Kit 可能包含多个部件，需分别对每个部件启动分析流程。

## Agent Team 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     Coordinator Agent (主控)                      │
│  - 负责任务调度和协调                                              │
│  - 汇总各agent的分析结果                                            │
│  - 生成最终报告                                                    │
└─────────────────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┬───────────┬───────────┐
        ↓           ↓           ↓           ↓           ↓
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  Error   │ │   API    │ │ Problem  │ │   Doc    │ │  Report  │
│  Code    │ │  Chain   │ │ Detector │ │ Validator│ │ Generator│
│ Analyzer │ │ Analyzer │ │          │ │          │ │          │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

## Agent 职责定义

### 1. Coordinator Agent (主控 Agent)

**职责：**
- 初始化审核环境
- 解析用户参数
- 分配任务给各 specialist agent
- 汇总分析结果
- 生成最终报告

**关键任务：**
1. 读取项目结构
2. 创建任务跟踪列表
3. 并行启动各 specialist agent
4. 收集并整合结果
5. 生成 `ERROR_CODE_ANALYSIS_REPORT.md`
6. 生成 `API_CALL_CHAIN_AND_EXCEPTION_REPORT.md`

### 2. Error Code Analyzer Agent (错误码分析专家)

**类型：** General Purpose Agent

**职责：**
- 查找并分析所有错误码定义文件
- 建立 C++ 层、JS/NAPI 层、NDK 层错误码清单
- 分析错误码映射函数和映射表
- 计算映射覆盖率

**关键搜索路径：**
```bash
# 错误码定义文件
**/*errno*.h
**/*error*.h
**/media_errors.h

# 映射函数
**/image_napi_utils.cpp (ERROR_CODE_MAP)
**/*error*.cpp
```

**输出：**
1. C++ 错误码清单（名称、值、说明）
2. JS/NAPI 错误码清单
3. NDK 错误码清单
4. 映射函数分析结果
5. 映射覆盖率统计

### 3. API Chain Analyzer Agent (API调用链分析专家)

**类型：** Explore Agent (thorough mode)

**职责：**
- 收集所有 API（Helper 函数、实例方法、NDK 层）
- 追踪主要 API 的完整调用链路
- 识别每一层的异常分支触发点
- 构建调用链路树

**关键搜索路径：**
```bash
# NAPI 层
frameworks/kits/js/common/*_napi.cpp

# Framework 层
frameworks/innerkitsimpl/**/*.cpp

# 搜索模式
DECLARE_NAPI_FUNCTION
napi_property_descriptor
```

**输出：**
1. API 清单（按类型分类）
2. 主要 API 的调用链路树
3. 异常分支汇总表

### 4. Problem Detector Agent (问题检测专家)

**类型：** General Purpose Agent

**职责：**
- 使用精确的 Grep 搜索检测5类常见问题
- 统计每个问题的精确数量
- 定位问题文件和行号

**检测目标：**

#### 问题1：错误码被转换为字符串（严重）
```bash
grep -rn "napi_throw_error.*to_string" frameworks/
grep -rn 'std::to_string.*errCode' frameworks/
grep -rn 'to_string(.*code' frameworks/
```

#### 问题2：错误码信息精度降低（严重）
```bash
grep -rn "return.*\?.*:.*ERR_" frameworks/
```

#### 问题3：异常分支未抛出错误码（中等）
```bash
grep -rn "if (.*!= OK)" frameworks/ | grep -v "SetError\|throw\|return.*ERR"
```

#### 问题4：使用非标准错误码（中等）
```bash
grep -rn "constexpr.*=-1[0-9]" frameworks/
grep -rn "ERROR.*-1[0-9][0-9]" frameworks/
```

#### 问题5：硬编码错误码值（中等）
```bash
grep -rn "{629800[0-9]" frameworks/
```

**输出：**
1. 问题1检测结果（精确数量、文件列表）
2. 问题2检测结果
3. 问题3检测结果
4. 问题4检测结果
5. 问题5检测结果

### 5. Documentation Validator Agent (文档验证专家)

**类型：** General Purpose Agent

**职责：**
- 解析 API 文档（./api_doc）
- 解析错误码文档（./error_code）
- 对比代码实际暴露的错误码与文档定义
- 验证一致性

**处理流程：**
1. 读取 `./api_doc` 目录下所有 `.md` 文件
2. 读取 `./error_code` 目录下所有 `.md` 文件
3. 提取文档中的错误码定义
4. 对比 Error Code Analyzer 的结果
5. 生成一致性分析报告

**输出：**
1. 文档中定义的错误码清单
2. 代码实际暴露的错误码清单
3. 一致性对比表
4. 未映射的错误码详细列表

### 6. Report Generator Agent (报告生成专家)

**类型：** 由 Coordinator Agent 兼任

**职责：**
- 汇总所有 agent 的分析结果
- 生成标准格式的审核报告
- 确保报告格式符合规范

**输出文件：**
1. `ERROR_CODE_ANALYSIS_MULTIMEDIA_IMAGE_FRAMEWORK_REPORT.md`
2. `API_CALL_CHAIN_MULTIMEDIA_IMAGE_FRAMEWORK_REPORT.md`

## 执行流程

### Phase 1: 初始化（Coordinator）
```
1. 解析用户参数
2. 创建任务跟踪
3. 验证文档路径
```

### Phase 2: 并行分析（所有 Specialist Agent 同时执行）
```
├─ Error Code Analyzer → 错误码清单 + 映射分析
├─ API Chain Analyzer → API清单 + 调用链路树
├─ Problem Detector → 5类问题检测结果
└─ Documentation Validator → 文档一致性分析
```

### Phase 3: 结果汇总（Coordinator）
```
1. 收集各 agent 的结果
2. 交叉验证数据一致性
3. 计算最终统计
```

### Phase 4: 报告生成（Coordinator）
```
1. 生成错误码问题分析报告
2. 生成API调用链路和异常分支报告
3. 验证报告完整性
```

## 关键搜索路径总结

### NAPI 层（JS 接口层）
```
frameworks/kits/js/common/
├── image_napi.cpp
├── image_source_napi.cpp
├── pixel_map_napi.cpp
├── image_packer_napi.cpp
├── image_receiver_napi.cpp
├── image_creator_napi.cpp
├── auxiliary_picture_napi.cpp
├── metadata_napi.cpp
└── image_napi_utils.cpp (错误码映射)
```

### Framework 层（C++ 实现）
```
frameworks/innerkitsimpl/
├── accessor/ (元数据处理)
├── codec/ (编解码)
├── common/ (通用功能)
├── converter/ (格式转换)
├── creator/ (ImageCreator)
├── receiver/ (ImageReceiver)
└── stream/ (流处理)
```

### 错误码定义
```
interfaces/inner_api/include/media_errors.h
frameworks/native/include/**/*error*.h
```

## 输出质量保证

### 精确量化要求
- ✅ 使用精确数字：268次、5处、2处
- ❌ 避免模糊描述："大量"、"多处"

### 问题分类明确
- 🔴 问题1：错误码被转换为字符串（严重）
- 🔴 问题2：错误码信息精度降低（严重）
- ⚠️ 问题3：异常分支未抛出错误码（中等）
- ⚠️ 问题4：使用非标准错误码（中等）
- ⚠️ 问题5：硬编码错误码值（中等）

### 开发者视角
- ✅ 关注暴露给 API 使用者的错误码
- ✅ 关注 JS/NAPI 层的错误处理
- ❌ 不过度关注 C++ 内部实现细节

### 报告不包含测试建议
- 只关注问题分析和修复建议
- 不提供测试用例或测试建议

## 执行时间估算

| Agent | 预计时间 | 并行度 |
|-------|---------|--------|
| Coordinator | 5分钟 | - |
| Error Code Analyzer | 10分钟 | 可并行 |
| API Chain Analyzer | 15分钟 | 可并行 |
| Problem Detector | 10分钟 | 可并行 |
| Documentation Validator | 10分钟 | 可并行 |
| **总计** | **~20分钟** | 5 agent 并行 |

## 使用方法

```bash
# 调用 skill（分析单个部件）
skill: audit-error-codes-new
args: component_path=/Users/spongbob/for_guance/api_dfx/DataBases/multimedia_image_framework
      api_doc_path=/path/to/api_doc
      api_error_doc_path=/path/to/error_code
      analyze_depth=thorough
```

> **注意**：若需分析整个 Kit（如 Image Kit），需对 Kit 下的每个 component 分别调用。Kit 与 Component 的映射关系见 `kit_compont.csv`。

## 版本历史

- v1.0 (2026-02-11): 初始设计，基于 multimedia_image_framework 项目
