#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infra.config：配置 I/O 与解析（底层）

导出符号与参数说明：
- ConfigAccessor.read_main(config_path: str) -> ConfigParser
  读取主配置文件，保留选项名大小写。参数：config_path 为配置文件路径。
- ConfigAccessor.read_main_if_exists(config_path: str) -> ConfigParser
  读取存在的主配置文件；不存在时返回空 ConfigParser。
- ConfigAccessor.read_main_tolerant_duplicates(config_path: str) -> ConfigParser
  同上，但对同节内重复选项去重后解析，避免 ConfigParser 报错。
- ConfigAccessor.read_fixed(base_dir: str) -> dict[str, str]
  从 base_dir 下固定配置文件的 [PATHS] 节读取固定配置。返回 key-value 字典。
- InputLineParser.split_input_lines(text: str) -> list[str]
  将用户输入（多行/分号/逗号分隔）拆分为行列表，供解析器使用。
"""

from infra.config.config_access import ConfigAccessor
from infra.config.input_parser import InputLineParser

read_config = ConfigAccessor.read_main
read_config_if_exists = ConfigAccessor.read_main_if_exists
read_config_tolerant_duplicates = ConfigAccessor.read_main_tolerant_duplicates
read_fixed_config = ConfigAccessor.read_fixed
split_input_lines = InputLineParser.split_input_lines

__all__ = [
    "ConfigAccessor",
    "InputLineParser",
    "read_config",
    "read_config_if_exists",
    "read_config_tolerant_duplicates",
    "read_fixed_config",
    "split_input_lines",
]
