"""
claude_runner.py - Agent CLI 执行模块（kit-scan-test 版）

导入共享 runner 模块，使用追加提示重试策略。
支持通过配置切换 claude/opencode 后端。
"""

import sys
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.runner import (
    run_agent,
    DEFAULT_MAX_RETRIES,
)
from common.config import load_config, find_config_file

# 加载配置以获取后端类型
_config = load_config(find_config_file(Path(__file__).resolve().parent))
_backend = _config.get("backend", "claude")


def run_claude_command(prompt: str, max_retries: int = DEFAULT_MAX_RETRIES) -> Tuple[bool, str]:
    """
    执行 Agent CLI 命令，使用追加提示重试策略。
    后端类型通过配置文件或默认值决定（claude / opencode）。
    """
    return run_agent(
        prompt=prompt,
        backend=_backend,
        max_retries=max_retries,
        retry_strategy="append_prompt",
        realtime_print=True,
        stderr_limit=0,
    )
