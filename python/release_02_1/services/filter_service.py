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
from services.config_constants import FILTER_OPTIONS_UI_KEYS

FILTER_OPTIONS_SECTION = "FILTER_OPTIONS"
_FILTER_OPTION_KEYS = FILTER_OPTIONS_UI_KEYS


class FilterService:
    """筛选项服务：解析 config/filter_options.ini，为前端提供等级/平台/车型等下拉选项。"""

    @staticmethod
    def lines_from_ini_value(raw: str) -> List[str]:
        """将 ini 中某选项的多行文本拆成去空行后的字符串列表（筛选项用）。

        参数：
            raw — 配置中读出的原始字符串，可为空；按换行切分，忽略仅空白行。

        返回：非空行的列表；raw 为空或仅空白时返回 []。
        """
        if not raw:
            return []
        out: List[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped:
                out.append(stripped)
        return out

    @classmethod
    def parse_shaixuan_config(cls, base_dir: str) -> Dict[str, List[str]]:
        """解析 base_dir 下 config/filter_options.ini，返回等级/平台/车型/Target Version/UDS_ECU_qualifier 等筛选项字典。
        参数：base_dir — 工程根目录。
        返回：{"levels", "platforms", "models", "target_versions", "uds_ecu_qualifier"}；文件不存在时返回空列表。
        """
        filters: Dict[str, List[str]] = {dict_key: [] for dict_key, _ in _FILTER_OPTION_KEYS}
        filter_options_path = resolve_filter_options_path(base_dir)

        if not os.path.exists(filter_options_path):
            print(f"提示: {filter_options_path} 不存在，前端将显示空列表")
            return filters

        try:
            cp = configparser.ConfigParser(interpolation=None)
            cp.read(filter_options_path, encoding="utf-8-sig")
            if not cp.has_section(FILTER_OPTIONS_SECTION):
                return filters
            for dict_key, option_name in _FILTER_OPTION_KEYS:
                raw = cp.get(FILTER_OPTIONS_SECTION, option_name, fallback="").strip()
                filters[dict_key] = cls.lines_from_ini_value(raw)
        except Exception as error:
            print(f"读取 filter_options.ini 出现异常: {error}")

        return filters


# Backward-compatible module-level alias
parse_shaixuan_config = FilterService.parse_shaixuan_config
