# [Kit 名称] 错误码问题分析报告

## 一、错误码定义概览

### 1.1 C++ Native 层错误码

**定义文件**: [文件路径]

**错误码清单** (共 [N] 个):

| 错误码名称 | 值 | 错误消息原文 | 说明 |
|-----------|---|-------------|------|
| [示例] | [值] | [错误消息原文] | [说明] |

### 1.2 JS/NAPI 层错误码

**定义文件**: [文件路径]

**错误码清单**（共 [N] 个）:

| 错误码名称 | 值 | 错误消息原文 | 说明 |
|-----------|---|-------------|------|
| [示例] | [值] | [错误消息原文] | [说明] |


### 1.3 NDK 层错误码

**定义文件**: [文件路径]

**错误码清单**（共 [N] 个）:

| 错误码名称 | 值 | 错误消息原文 | 说明 |
|-----------|---|-------------|------|
| [示例] | [值] | [错误消息原文] | [说明] |

---

## 二、发现的问题

### 🔴 问题 1：错误码被转换为字符串（严重）

**问题描述**:
错误码被转换为字符串后传递给 `napi_throw_error`，导致 JavaScript 层接收到字符串类型错误码，违反 API 规范。

**问题位置**：

#### 1. [文件名] ([N] 处)

- [file_path:line_number](file_path#Lline_number)
```cpp
napi_throw_error(env, std::to_string(context->GetErrorCode()).c_str(), context->GetErrorMessage().c_str());
```

#### 2. [文件名] ([N] 处)

- [file_path:line_number](file_path#Lline_number)
```cpp
napi_throw_error(env, std::to_string(ret).c_str(), errorMsg.c_str());
```

**影响**:
- JavaScript 层接收到的错误码是字符串（如 "401"）而非数字（401）
- 违反 HarmonyOS API 规范
- 开发者需要进行类型转换，增加开发复杂度
- 与其他 Kit 行为不一致

**数量统计**:
- 发现 **[N] 处**

---

### 🔴 问题 2：错误码信息精度降低（严重）

**问题描述**:
使用三元操作符将多种不同失败原因统一映射到同一个错误码，导致错误信息精度降低。

**问题位置**：

数据大于等于5个时输出以下格式
| id | file_path | line_number | code|
|-----|---------|-----|-----|
| 1 | {{file_path}} | {{line_number}} | return GetAudioTime(timestamp, base) ? SUCCESS : ERR_OPERATION_FAILED;|

数量小于5个时输出以下格式
- [file_path:line_number](file_path#Lline_number)
```cpp
return GetAudioTime(timestamp, base) ? SUCCESS : ERR_OPERATION_FAILED;
```

**影响**:
- 开发者无法区分具体的失败原因
- 问题定位困难
- 所有失败情况返回相同的错误码

**数量统计**:
- 发现 **[N] 处**

---

### ⚠️ 问题 3：错误码映射不完整（中等）

**问题描述**:
Native 层定义了大量错误码，但只有少数错误码被正确映射到 JS 层，其余全部映射到通用的系统错误码。

**问题位置**:

- [file_path:line_number](file_path#Lline_number)
```cpp
default:
    code = NAPI_ERR_SYSTEM;  // [百分比]% 的错误码进入这里
    break;
```

**影响**:
- [N]/[M] ([百分比]%) 的 Native 错误码未正确映射
- 开发者只能接收到通用的系统错误码
- 无法区分具体的错误类型

**数量统计**:
- Native 错误码总数: [N] 个
- 已映射的错误码: [N] 个 ([百分比]%)
- 未映射的错误码: [N] 个 ([百分比]%)

---

### 问题4:....

### 问题5:....

## 三、错误码映射分析

### 3.1 映射流程

```
Native 层错误码
    ↓
ConvertErrorCode(int32_t &errorCode)
    ↓ g_errNumMap 查找
转换后错误码
    ↓ g_errStringMap 查找
错误消息
    ↓
std::to_string(code)  // ⚠️ 问题：转字符串
    ↓
napi_throw_error(env, stringCode, message)
    ↓
JavaScript 层接收字符串类型错误码  // ❌ 不符合规范
```

### 3.2 映射函数分析

**文件**: [文件路径]

**关键代码**:
```cpp
std::string ConvertErrorCode(int32_t &errorCode)
{
    std::string errmsg;
    if (g_errNumMap.find(errorCode) != g_errNumMap.end()) {
        errorCode = g_errNumMap.at(errorCode);
    }
    if (g_errStringMap.find(errorCode) != g_errStringMap.end()) {
        errmsg = g_errStringMap.at(errorCode);
    }
    return errmsg;
}
```

### 3.3 映射完整性统计

| 统计项 | 数量 | 百分比 |
|--------|------|--------|
| **Native 层错误码总数** | [N] 个 | [N]% |
| **JS 层已映射的错误码** | [N] 个 | [N]% |
| **JS 层未映射的错误码** | [N] 个 | [N]% |
| **NDK 层已映射的错误码** | [N] 个 | [N]% |

### 3.3 已映射的错误码列表 (JS 层)

| Native 错误码 | JS 层错误码 | 映射状态 |
|---------------|-------------|---------|
| [常量名] | [JS错误码值] | ✅已映射 |
| [常量名] | [JS错误码值] | 已映射 |
| [常量名] |  | ❌未映射 |

### 3.4 映射异常的关键错误码 (JS 层)

| Native 错误码 | 值 | 当前处理 |
|--------------|-----|---------|
| [常量名] | [值] | 映射为[JS错误码值] |
| [常量名] | [值] | 映射为[JS错误码值] |

---

## 四、问题位置汇总

| 问题类型 | 文件路径:行号 | 数量 |
|---------|---------------|------|
| 错误码转字符串 | [路径:行号] | [N] 处 |
| 错误码精度降低 | [路径:行号] | [N] 处 |
| 映射不完整 | [路径:行号] | [N] 处 |

**总计**: [N] 处

---

## 五、总结

| 统计项 | 数量 |
|--------|------|
| Native 层错误码总数 | [N] 个 |
| Js层错误码总数 |[N]个|
| 已映射的错误码 | [N] 个 |
| 错误消息映射 | [N] 个 |
| 暴露给开发者的错误码（不含 0） | [N] 个 |
| 错误码转字符串问题 | **[N] 处** |
| 错误码精度降低问题 | [N] 处 |
| 硬编码错误码问题 | [N] 处 |

---

**报告生成时间**: [日期]
**审核项目**: [Kit 名称]
**项目路径**: [路径]
