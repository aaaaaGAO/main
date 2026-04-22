#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置聚合读取层（底层 I/O）

统一主配置文件 + 固定配置文件的读取能力，避免多套配置逻辑并存。
"""

from __future__ import annotations

import configparser
import os
from typing import List, Optional

from infra.filesystem import resolve_fixed_config_path, resolve_runtime_path
from services.config_constants import PATHS_MERGED_PRESERVE_OPTION_NAMES, SECTION_PATHS


def read_config(config_path: str) -> configparser.ConfigParser:
    """读取主配置文件，保留选项名大小写。参数: config_path — 配置文件路径。返回: ConfigParser。"""
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    resolved_path = resolve_runtime_path(None, config_path)
    with open(resolved_path, "r", encoding="utf-8", errors="replace") as config_file:
        cfg.read_file(config_file)
    return cfg


def read_config_if_exists(config_path: str) -> configparser.ConfigParser:
    """读取存在的主配置文件；文件不存在时返回空 ConfigParser。"""
    config = configparser.ConfigParser()
    config.optionxform = str
    resolved_path = resolve_runtime_path(None, config_path)
    if not resolved_path or not os.path.exists(resolved_path):
        return config

    try:
        config.read(resolved_path, encoding="utf-8")
    except Exception:
        with open(resolved_path, "r", encoding="utf-8", errors="replace") as config_file:
            config.read_file(config_file)
    return config


def read_config_tolerant_duplicates(config_path: str) -> configparser.ConfigParser:
    """读取主配置文件，同节内重复选项去重后解析。参数: config_path — 配置文件路径。返回: ConfigParser。"""
    config = configparser.ConfigParser()
    config.optionxform = str
    resolved_path = resolve_runtime_path(None, config_path)
    with open(resolved_path, "r", encoding="utf-8", errors="replace") as config_file:
        lines = config_file.readlines()
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
            item_key = stripped.split("=", 1)[0].strip()
            if current_section and item_key:
                key_lower = item_key.lower()
                if key_lower in seen_options.get(current_section, set()):
                    continue
                seen_options.setdefault(current_section, set()).add(key_lower)
            cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)
    config.read_string("".join(cleaned_lines), source=resolved_path)
    return config


def read_fixed_config(base_dir: str) -> dict[str, str]:
    """从 base_dir/config 下固定配置文件的 [PATHS] 节读取固定配置项。参数: base_dir — 工程根目录。返回: {key: value} 字典。"""
    fixed_config_path = resolve_fixed_config_path(base_dir)
    fixed_config: dict[str, str] = {}

    if not os.path.exists(fixed_config_path):
        return fixed_config

    try:
        fixed_cfg = configparser.ConfigParser()
        fixed_cfg.optionxform = str
        fixed_cfg.read(fixed_config_path, encoding="utf-8")

        if fixed_cfg.has_section(SECTION_PATHS):
            for item_key in PATHS_MERGED_PRESERVE_OPTION_NAMES:
                if fixed_cfg.has_option(SECTION_PATHS, item_key):
                    fixed_config[item_key] = fixed_cfg.get(SECTION_PATHS, item_key)
    except Exception as error:
        print(f"警告: 读取固定配置文件失败: {error}")

    return fixed_config

