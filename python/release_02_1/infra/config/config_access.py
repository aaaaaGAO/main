#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置聚合读取层（底层 I/O）

统一 Configuration.txt + FixedConfig.txt 的读取能力，避免多套配置逻辑并存。
"""

from __future__ import annotations

import configparser
import os
from typing import List, Optional

_FIXED_KEYS = [
    "unified_mapping_excel",
    "mapping_sheets",
    "cin_mapping_sheet",
    "output_filename",
    "cin_output_filename",
    "xml_output_filename",
    "didinfo_output_filename",
    "didconfig_output_filename",
    "uart_output_filename",
    "uds_output_filename",
    "didinfo_variants",
    "mapping_excel",
    "cin_mapping_excel",
]


def read_config(config_path: str) -> configparser.ConfigParser:
    """读取 Configuration.txt，保留选项名大小写。参数: config_path — 配置文件路径。返回: ConfigParser。"""
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    with open(config_path, "r", encoding="utf-8", errors="replace") as f:
        cfg.read_file(f)
    return cfg


def read_config_tolerant_duplicates(config_path: str) -> configparser.ConfigParser:
    """读取 Configuration.txt，同节内重复选项去重后解析。参数: config_path — 配置文件路径。返回: ConfigParser。"""
    config = configparser.ConfigParser()
    config.optionxform = str
    with open(config_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    seen_options: dict[str, set[str]] = {}
    current_section: Optional[str] = None
    cleaned_lines: List[str] = []
    first_section_found = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1].strip()
            first_section_found = True
            current_section = section_name
            if section_name not in seen_options:
                seen_options[section_name] = set()
            cleaned_lines.append(line)
        elif not first_section_found:
            cleaned_lines.append(line)
        elif "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if current_section and key:
                key_lower = key.lower()
                if key_lower in seen_options.get(current_section, set()):
                    continue
                seen_options.setdefault(current_section, set()).add(key_lower)
            cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)
    config.read_string("".join(cleaned_lines), source=config_path)
    return config


def read_fixed_config(base_dir: str) -> dict[str, str]:
    """从 base_dir/config 下 FixedConfig.txt 的 [PATHS] 节读取固定配置项。参数: base_dir — 工程根目录。返回: {key: value} 字典。"""
    fixed_config_path = os.path.join(base_dir, "config", "FixedConfig.txt")
    fixed_config: dict[str, str] = {}

    if not os.path.exists(fixed_config_path):
        return fixed_config

    try:
        fixed_cfg = configparser.ConfigParser()
        fixed_cfg.optionxform = str
        fixed_cfg.read(fixed_config_path, encoding="utf-8")

        if fixed_cfg.has_section("PATHS"):
            for key in _FIXED_KEYS:
                if fixed_cfg.has_option("PATHS", key):
                    fixed_config[key] = fixed_cfg.get("PATHS", key)
    except Exception as e:
        print(f"警告: 读取固定配置文件失败: {e}")

    return fixed_config

