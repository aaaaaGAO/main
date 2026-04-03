#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
筛选项服务：解析 config/filter_options.ini，为前端提供等级/平台/车型等下拉选项。

从原 app.py 中的 parse_shaixuan_config 拆出，便于在新旧入口之间复用。
"""

from __future__ import annotations

import configparser
import os
from typing import Dict, List

from infra.filesystem.pathing import resolve_filter_options_path

FILTER_OPTIONS_SECTION = "FILTER_OPTIONS"
_FILTER_OPTION_KEYS = (
    ("levels", "levels"),
    ("platforms", "platforms"),
    ("models", "models"),
    ("target_versions", "target_versions"),
    ("uds_ecu_qualifier", "uds_ecu_qualifier"),
)


def _lines_from_ini_value(raw: str) -> List[str]:
    if not raw:
        return []
    out: List[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if s:
            out.append(s)
    return out


def parse_shaixuan_config(base_dir: str) -> Dict[str, List[str]]:
    """解析 base_dir 下 config/filter_options.ini，返回等级/平台/车型/Target Version/UDS_ECU_qualifier 等筛选项字典。
    参数：base_dir — 工程根目录。
    返回：{"levels", "platforms", "models", "target_versions", "uds_ecu_qualifier"}；文件不存在时返回空列表。
    """
    filters: Dict[str, List[str]] = {
        "levels": [],
        "platforms": [],
        "models": [],
        "target_versions": [],
        "uds_ecu_qualifier": [],
    }
    path = resolve_filter_options_path(base_dir)

    if not os.path.exists(path):
        print(f"提示: {path} 不存在，前端将显示空列表")
        return filters

    try:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(path, encoding="utf-8-sig")
        if not cp.has_section(FILTER_OPTIONS_SECTION):
            return filters
        for dict_key, option_name in _FILTER_OPTION_KEYS:
            raw = cp.get(FILTER_OPTIONS_SECTION, option_name, fallback="").strip()
            filters[dict_key] = _lines_from_ini_value(raw)
    except Exception as error:
        print(f"读取 filter_options.ini 出现异常: {error}")

    return filters
