# Skill 使用示例

## audit-error-codes-new 使用示例

### 示例 1：基本使用（分析单个部件）

```
用户：使用 audit-error-codes-new skill 审核 /Users/spongbob/for_guance/api_dfx/DataBases/communication_netmanager_base

Claude：
✅ 开始执行 audit-error-codes-new skill

📂 部件路径: /Users/spongbob/for_guance/api_dfx/DataBases/communication_netmanager_base
📦 部件名称: communication_netmanager_base

[执行审核步骤...]

✅ 审核完成
📄 报告已保存至:
   - communication_netmanager_base_ERROR_CODE_ANALYSIS_REPORT.md
   - communication_netmanager_base_API_CALL_CHAIN_AND_EXCEPTION_REPORT.md
   - communication_netmanager_base_DOC_CONSISTENCY_REPORT.md

📊 分析统计：
   - API 总数: 45 个
   - 异常分支触发点: 128 个
   - 发现问题: 高优先级 3 个，中优先级 5 个，低优先级 2 个
```

### 示例 2：指定文档路径

```
用户：使用 audit-error-codes-new 审核 communication_netmanager_base
      API文档: /path/to/api_doc/
      错误码文档: /path/to/error_doc/

Claude：
✅ 开始执行 audit-error-codes-new skill

📂 部件路径: /path/to/communication_netmanager_base
📦 部件名称: communication_netmanager_base
📚 API文档: /path/to/api_doc/
📋 错误码文档: /path/to/error_doc/

[执行审核步骤，包括文档对比...]

✅ 审核完成
📄 报告已保存
📊 包含文档对比结果
```

### 示例 3：快速分析

```
用户：使用 audit-error-codes-new 以 medium 深度分析 /path/to/component

Claude：
✅ 开始执行 audit-error-codes-new skill（深度: medium）

📂 部件路径: /path/to/component
📊 分析深度: medium（快速扫描，重点检查常见问题）

[执行审核步骤...]

✅ 审核完成
📄 报告已保存
```

### 示例 4：分析大型部件

```
用户：使用 audit-error-codes-new 审核 /path/to/large_component，使用 thorough 模式

Claude：
✅ 开始执行 audit-error-codes-new skill（深度: thorough）

📂 部件路径: /path/to/large_component
📊 分析深度: thorough（完整分析所有 API 调用链路和异常分支）

⏳ 预计需要 5-10 分钟...

[使用 Explore 子代理进行深度分析...]

✅ 审核完成
📄 报告已保存

📊 详细统计：
   - API 总数: 156 个
   - 异常分支触发点: 542 个
   - 涉及文件: 89 个
   - 发现问题: 高优先级 8 个，中优先级 15 个，低优先级 6 个
```

### 示例 5：分析整个 Kit 的所有部件

当需要分析一个 Kit（如 Network Kit）时，需对每个部件分别调用：

```
# Network Kit 包含 3 个部件：
1. audit-error-codes-new component_path=/DataBases/communication_netmanager_base
2. audit-error-codes-new component_path=/DataBases/communication_netstack
3. audit-error-codes-new component_path=/DataBases/communication_netmanager_ext
```

Kit 与部件的映射关系定义在 `kit_compont.csv` 中。

### 示例 6：向后兼容调用（使用旧参数名）

```
用户：使用 audit-error-codes-new 审核 kit_path=/path/to/component

Claude：
⚠️ 注意：kit_path 参数已更名为 component_path，请后续使用新名称
✅ 开始执行 audit-error-codes-new skill

📂 部件路径: /path/to/component
...
```

## 预期输出

执行 skill 后会生成三个详细的 Markdown 报告：

### 1. ERROR_CODE_ANALYSIS_REPORT.md - 错误码问题分析报告

专注于错误码定义和问题发现，列出具体的代码位置和问题类型。

包含以下内容：

#### 一、错误码定义概览
- C++ Native 层错误码列表
- JS/NAPI 层错误码列表
- NDK 层错误码列表
- 错误码基准值计算说明

#### 二、发现的问题
每个问题包含：
- 文件位置和行号（带链接）
- 问题代码片段
- 问题描述
- 影响分析
- 严重程度标记（🔴严重 / ⚠️中等）
- 数量统计（精确数字）

**问题类型**：
- 错误码转字符串（严重）
- 错误码信息精度降低（严重）
- 错误码映射不完整（中等）

#### 三、错误码映射分析
- 映射流程图
- 映射完整性统计
- 已映射/未映射错误码列表

#### 四、问题位置汇总
- 按问题类型分类的问题清单

### 2. API_CALL_CHAIN_AND_EXCEPTION_REPORT.md - API 调用链路和异常分支报告

专注于 API 调用链路分析，追踪从 JavaScript 到 Native 层的完整调用路径。

包含以下内容：

#### 一、API 清单
- JS/NAPI 层 Helper 函数（静态方法）
- 实例方法
- 观察者方法
- NDK 层 API

#### 二、API 调用链路分析
对于每个 API：
1. **完整调用链路** - 从 JavaScript 到底层框架的树状结构
2. **异常分支汇总表** - 每一层的异常触发点

#### 三、异常分支统计
- 按错误码类型统计
- 按层级统计

#### 四、错误处理机制分析
- 错误码转换流程
- 错误码映射表
- 异步调用错误处理

#### 五、典型场景错误码流程
- 正常流程
- 参数错误流程
- 状态错误流程

### 3. DOC_CONSISTENCY_REPORT.md - 文档与代码一致性分析报告

专注于文档与代码的一致性对比，验证错误码定义是否一致。

包含以下内容：

#### 二、错误码文档对比
- 文档定义的错误码列表
- 代码中定义的错误码列表
- 一致性分析结果

#### 三、API 文档与代码一致性分析
- API 文档中的错误码引用
- 一致性评估

#### 四、错误码映射覆盖率分析
- 代码中错误码映射情况
- 已映射/未映射错误码清单

#### 五、错误消息一致性分析
- 文档中的错误消息
- 消息一致性评估

#### 六、文档与代码对比统计
- 一致性百分比
- 错误码映射覆盖率

#### 三、调用链路示例
```
JavaScript 应用
    ↓
[napi_xxx.cpp:行号] API_Name()
    ├─ [line:XX] ❌ 错误码 [401] - 参数数量不正确
    ↓
[helper_xxx.cpp:行号] HelperFunction()
    ├─ [line:XX] ❌ 错误码 [15500010] - 路径无效
    ↓
[impl_xxx.cpp:行号] InstanceMethod()
    ├─ [line:XX] ❌ 错误码 [15500027] - 对象已失效
    ↓
[storage_xxx.cpp:行号] StorageOperation()
    ├─ [line:XX] ❌ 错误码 [15500000] - 操作失败
```

#### 四、统计信息
- API 总数
- 异常分支触发点数量
- 涉及的错误码种类
- 问题分布（按严重程度）

## 技巧提示

### 1. 指定分析深度

根据需求选择合适的分析深度：

- **quick**: 快速扫描，只检查明显的错误码问题（1-3 分钟）
  - 适合：初步检查、CI/CD 集成

- **medium**: 中等分析，检查常见问题模式（5-10 分钟）
  - 适合：日常开发、代码审查

- **thorough**: 深度分析，完整的调用链路和异常分支分析（15-30 分钟）
  - 适合：发布前检查、详细审计、问题诊断

### 2. 提供文档路径

为了获得最准确的分析，建议提供完整的文档路径：

```
使用 audit-error-codes 审核 /path/to/kit
      API文档: /path/to/kit/docs/api.md
      错误码文档: /path/to/kit/docs/errors/
```

### 3. 分析特定模块

如果只想分析部件的某个模块：

```
使用 audit-error-codes-new 审核 /path/to/component 的 preferences 模块
```

### 4. 对比多个部件

```
使用 audit-error-codes-new 分别审核以下部件：
- /path/to/accessibility
- /path/to/preferences
- /path/to/multimedia
```

### 5. 定期审查

建议在以下情况下执行审核：
- 代码重构后
- 新增大量 API 后
- 收到用户错误反馈后
- 发布新版本前
- 进行安全审计时

## 常见问题

### Q: 审核需要多长时间？
**A**:
- quick 模式: 5-10 秒
- medium 模式: 1-3 分钟
- thorough 模式: 5-10 分钟（大型 kit 可能需要更长时间）

### Q: 报告会很大吗？
**A**:
- 错误码分析报告: 通常 500-2000 行
- 调用链路报告: 大型 kit 可能达到 10,000+ 行
- 文档一致性报告: 通常 500-1500 行
- 建议使用代码编辑器的搜索功能快速定位

### Q: 如果文档路径无法访问怎么办？
**A**:
- Skill 会跳过文档对比步骤
- 在报告中标注"需要人工验证"
- 不影响其他分析步骤

### Q: 可以只生成一个报告吗？
**A**:
- 当前版本总是生成三个报告
- 三个报告各有侧重，互相补充，提供完整的信息
- 可以根据需要选择阅读哪个报告：
  - ERROR_CODE_ANALYSIS_REPORT：关注错误码问题
  - API_CALL_CHAIN_AND_EXCEPTION_REPORT：关注 API 调用链路
  - DOC_CONSISTENCY_REPORT：关注文档一致性

### Q: 分析结果如何使用？
**A**:
1. **开发者**: 参考调用链路报告了解 API 的异常处理
2. **代码审查**: 使用错误码问题报告检查代码质量
3. **问题修复**: 根据问题报告定位代码问题并修复
4. **文档编写**: 使用文档一致性报告验证错误码文档与代码的一致性

**注意**: 报告只指出问题和位置，不提供修复建议。修复方案需要根据具体情况自行设计。

### Q: 能自定义检查项吗？
**A**:
- 可以直接修改 `.claude/skills/audit-error-codes.md` 文件
- 添加或修改检查步骤
- 调整报告格式

### Q: 如何解读报告中的问题标记？
**A**:
- 🔴 严重问题: 必须修复，影响 API 规范或导致错误丢失
- ⚠️ 中等问题: 建议修复，影响代码质量或错误处理准确性
- ✅ 正常: 符合规范，无需修改

## 高级用法

### 1. 结合其他工具

```
使用 audit-error-codes 审核 /path/to/kit，然后生成测试用例
```

### 2. 导出报告供其他工具使用

报告是 Markdown 格式，可以：
- 转换为 HTML: 使用 `pandoc` 或其他 Markdown 转 HTML 工具
- 导出为 PDF: 使用 Typora、VS Code 等工具
- 集成到 CI/CD: 解析 Markdown，提取问题统计

### 3. 批量分析

```
使用 audit-error-codes-new 批量分析以下目录下的所有部件：
/Users/spongbob/for_guance/api_dfx/DataBases/
```

### 4. 生成对比报告

```
使用 audit-error-codes-new 对比以下两个部件的错误码使用情况：
- /path/to/component/v1.0
- /path/to/component/v2.0
```

## 最佳实践

1. **定期审核**: 每次发布前执行 thorough 模式审核
2. **文档同步**: 保持代码和文档的一致性
3. **问题跟踪**: 将发现的问题添加到 issue tracker
4. **自动化集成**: 将 quick 模式集成到 CI/CD 流程
5. **团队共享**: 将报告分享给团队成员，共同改进代码质量
