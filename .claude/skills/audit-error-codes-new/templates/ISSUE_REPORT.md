# [Kit 名称] 问题总结报告

## 🔴 问题 1：错误码被转换为字符串（严重）

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

#### 2. [文件名] ([N] 处)

- [file_path:line_number](file_path#Lline_number)
```cpp
napi_throw_error(env, std::to_string(ret).c_str(), errorMsg.c_str());
```

**数量统计**:
- 共发现 **[N] 处**

## 🔴 问题 2：xxxx
**问题描述**:
xxxx
**问题位置**：

#### 1. [文件名] ([N] 处)
- [file_path:line_number](file_path#Lline_number)
```cpp
xxxx
```

#### 2. [文件名] ([N] 处)
- [file_path:line_number](file_path#Lline_number)
```cpp
xxxx
```

**数量统计**:
- 共发现 **[N] 处**

## 问题 3：......