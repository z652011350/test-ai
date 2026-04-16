---
date: 2026-04-16
topic: scripts-refactor
---

# Scripts 目录重构：提取公共模块 + 多后端支持

## Problem Frame

`scripts/` 下有 3 套扫描流程（component-scan、kit-scan、kit-scan-test），各自维护独立的 `claude_runner.py`、数据处理函数和 Kit 辅助函数。大量代码被复制粘贴（最多 3 份），导致修复 bug 需要同步多处、新增功能需要重复实现。当前所有流程均使用 Claude Code CLI（`claude -p`），需要新增 OpenCode CLI（`opencode run`）后端支持，使三套流程都能通过配置切换使用不同 Agent 后端。

## Requirements

**公共模块提取**

- R1. 将 JSONL 数据处理函数（`load_and_split_impl_api`、`load_matching_api_data`、`jsonl_to_xlsx`）提取到共享模块。这些函数当前在 kit-scan/`batch_pipeline.py` 和 kit-scan-test/`data_prepare.py` 中重复（2 处），test/`batch_test.py` 中也有同源实现（将在 R10 中随目录删除）。kit-scan/`batch_pipeline.py` 中的其余独有函数（`prepare_batches`、`build_scan_prompt`、`merge_batch_results`、`compute_kit_stats` 等）保留在 kit-scan 目录中
- R2. 将 Kit 辅助函数提取到共享模块，消除以下文件中的重复：`normalize_kit_name` 和 `resolve_kit_file` 在 kit-scan/`scan_kit.py` 和 kit-scan-test/`scan_kit.py` 中重复（2 处），`load_unique_kit_names` 在 kit-scan/`batch_scan_all.py` 和 kit-scan-test/`batch_scan_all.py` 中重复（2 处）
- R3. 将 3 个 `claude_runner.py` 的核心 subprocess 调用逻辑（Popen 构建、实时 stdout 读取、错误处理）提取到共享 runner 模块。各流程的领域专用函数（如 `build_skill_prompt`、`run_component_scan`、`run_batch_scan`、prompt 构建逻辑）保留在各自目录中。共享 runner 需统一当前三者的行为差异（stdout 实时打印开关、stderr 截断/完整输出、label 日志前缀参数），通过配置或参数控制
- R4. 去除重复的 `kit_compont.csv`，当前有 3 份副本（kit-scan/、kit-scan-test/、`.claude/skills/api-level-scan/assets/`），内容相同但排序不同。保留 `.claude/skills/api-level-scan/assets/` 下的副本作为权威版本（skill 脚本已硬编码引用此路径），删除 scripts/ 下的 2 份副本并更新引用路径。scope 内不修改 skill 文件本身

**多后端支持**

- R5. 新增 OpenCode CLI（`opencode run`）后端支持，使共享 runner 模块同时支持 Claude Code CLI 和 OpenCode CLI 两种后端，通过配置或参数切换
- R6. 两种后端各自保留其差异化的调用参数（Claude 使用 `--allowedTools`，OpenCode 依赖 `.opencode/opencode.json` 配置）

**重试策略**

- R7. 重试策略可配置：支持指数退避（component-scan 和 kit-scan 风格）和追加提示重试（kit-scan-test 风格）两种模式。共享 runner 的函数签名应统一为接受 `max_retries` 参数

**配置管理**

- R8. 引入配置文件（JSON 格式，使用标准库 `json` 模块）集中管理路径、重试策略、批量大小等参数，命令行参数可覆盖配置文件值
- R9. 配置文件中可指定默认后端类型（claude / opencode），单次运行可通过 CLI 参数覆盖

**清理**

- R10. 在 R1 公共模块提取完成并验证无独有逻辑需保留后，删除 `scripts/test/` 目录（早期原型，功能已被 kit-scan 和 kit-scan-test 覆盖）
- R11. 现有三套流程目录（component-scan、kit-scan、kit-scan-test）保留其目录结构，将其内部的以下文件改为导入共享模块：
  - **component-scan/**：`batch_scan.py`、`claude_runner.py`、`gen_csv.py`、`result_collector.py`（result_collector.py 无重复代码，但需导入共享 runner 以支持后端切换）
  - **kit-scan/**：`scan_kit.py`、`batch_scan_all.py`、`batch_pipeline.py`、`claude_runner.py`
  - **kit-scan-test/**：`scan_kit.py`、`batch_scan_all.py`、`data_prepare.py`、`claude_runner.py`

**Python 包结构**

- R12. 在 `scripts/` 和 `scripts/common/` 下添加 `__init__.py`，使 common 模块可通过 `from common import ...` 或 `from common.runner import ...` 被子目录中的脚本导入。各入口脚本在头部添加 `sys.path` 设置以确保模块可发现

## Success Criteria

- 所有重复代码合并到 `scripts/common/`，每个函数/类只有一份实现
- component-scan/、kit-scan/、kit-scan-test/ 中上述列出的所有文件改为导入 common 模块，不再包含重复逻辑
- 通过配置切换后端，一个命令即可用 claude 或 opencode 运行同一套流程
- 以下文件中的硬编码绝对路径移入配置文件：kit-scan/`batch_scan_all.py`、kit-scan-test/`batch_scan_all.py`、component-scan/`batch_scan.py`、component-scan/`gen_csv.py`。`__file__` 相对路径不属于硬编码绝对路径
- 重构后现有功能行为不变

## Scope Boundaries

- 不合并三套流程为统一流水线，保持各自独立的目录和入口
- 不修改各流程调用的 skill 内容（`/audit-error-codes-new`、`/kit-api-extract`、`/api-level-scan`、`/api-level-scan-test`）
- 不引入额外的 Python 依赖（openpyxl 保持可选依赖；使用 JSON 而非 YAML 以避免引入 pyyaml）
- 不修改 `.opencode/opencode.json` 的现有配置
- R3 仅提取核心 subprocess 调用层，领域专用函数和 prompt 构建逻辑保留在各自目录
- R4 不移动 `.claude/skills/api-level-scan/assets/kit_compont.csv`，仅删除 scripts/ 下的冗余副本并更新引用

## Key Decisions

- **工厂模式而非抽象基类**：用工厂函数按后端类型返回 runner 实现，避免为 2 种后端引入完整的类继承体系
- **配置文件 + CLI 覆盖**：JSON 配置文件作为默认值来源（使用标准库 `json` 模块，无需额外依赖），CLI 参数可覆盖
- **保留现有目录结构**：不改变用户熟悉的入口文件位置，降低迁移成本
- **OpenCode 为新增功能**：当前所有流程均使用 Claude CLI，OpenCode 后端需要从头实现调用逻辑
- **OpenCode 模型保持 minimax-m2.5-free**：不改变 `.opencode/opencode.json` 中的现有模型选择
- **CSV 权威副本位置**：保留 `.claude/skills/api-level-scan/assets/kit_compont.csv` 作为唯一权威版本，避免修改 skill 内的硬编码路径
- **sys.path 方式**：各入口脚本头部通过 `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` 实现跨目录导入，而非改为 python -m 运行方式

## Dependencies / Assumptions

- 假设 `claude` CLI 已安装在运行环境中；`opencode` CLI 需在启用 OpenCode 后端时安装
- 假设 Python >= 3.9（`subprocess.Popen`、`pathlib`、`concurrent.futures`、`list[str]` 类型注解均可用）
- `openpyxl` 仍为可选依赖（有则生成 XLSX，无则跳过）

## Next Steps

-> 直接进入实施规划与编码
