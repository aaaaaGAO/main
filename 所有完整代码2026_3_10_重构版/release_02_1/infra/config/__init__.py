#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infra.config：配置 I/O 与解析（底层）

导出符号与参数说明：
- read_config(config_path: str) -> ConfigParser
  读取 Configuration.txt，保留选项名大小写。参数：config_path 为配置文件路径。
- read_config_tolerant_duplicates(config_path: str) -> ConfigParser
  同上，但对同节内重复选项去重后解析，避免 ConfigParser 报错。
- read_fixed_config(base_dir: str) -> dict[str, str]
  从 base_dir 下 FixedConfig.txt 的 [PATHS] 节读取固定配置。返回 key-value 字典。
- split_input_lines(text: str) -> list[str]
  将用户输入（多行/分号/逗号分隔）拆分为行列表，供解析器使用。
"""

from infra.config.config_access import (
    read_config,
    read_config_tolerant_duplicates,
    read_fixed_config,
)
from infra.config.input_parser import split_input_lines

__all__ = [
    "read_config",
    "read_config_tolerant_duplicates",
    "read_fixed_config",
    "split_input_lines",
]

