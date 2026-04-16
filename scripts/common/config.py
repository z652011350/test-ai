"""
config.py - 配置管理共享模块

提供 JSON 配置文件加载和 CLI 参数覆盖功能。
配置优先级：CLI 参数 > 配置文件 > 默认值
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


# 默认配置
_DEFAULTS: Dict[str, Any] = {
    "backend": "claude",              # claude | opencode
    "max_retries": 3,
    "base_retry_delay": 10.0,
    "retry_strategy": "exponential",  # exponential | append_prompt
    "batch_size": 30,
    "max_parallel": 3,
    "allowed_tools": "Bash,Read,Edit,Find,Wc,Write,Search,Python,Grep,Glob,Agent",
    # 路径配置（无默认值，需通过配置文件或 CLI 提供）
    "js_decl_path": "",
    "c_decl_path": "",
    "repo_base": "",
    "out_path": "",
    "doc_path": "",
}


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    加载配置文件并与默认值合并。

    Args:
        config_path: 配置文件路径，为 None 则仅返回默认值

    Returns:
        合并后的配置字典
    """
    config = dict(_DEFAULTS)

    if config_path and config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        config.update({k: v for k, v in file_config.items() if v is not None and v != ""})

    return config


def merge_cli_overrides(config: Dict[str, Any], **overrides) -> Dict[str, Any]:
    """
    用 CLI 参数覆盖配置值。仅覆盖非 None、非空的值。

    Args:
        config: 当前配置字典
        **overrides: CLI 参数键值对

    Returns:
        更新后的配置字典
    """
    for key, value in overrides.items():
        if value is not None and value != "":
            config[key] = value
    return config


def find_config_file(start_dir: Optional[Path] = None) -> Optional[Path]:
    """
    从指定目录向上查找 scan_config.json 配置文件。

    Args:
        start_dir: 起始搜索目录

    Returns:
        找到的配置文件路径，未找到返回 None
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()
    for _ in range(10):  # 最多向上搜索 10 层
        candidate = current / "scan_config.json"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None
