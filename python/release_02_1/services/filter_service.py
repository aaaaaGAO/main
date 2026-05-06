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
    def parse_filter_option_value(*, option_name: str, raw: str) -> List[str]:
        """解析筛选项字符串，兼容英文逗号与中文逗号，非法分隔符时报错。

        参数：
            option_name — 当前配置项名（用于错误信息定位）。
            raw — 配置中读出的原始字符串，可为空；支持单行或多行，元素间用 `,` / `，` 分隔。

        返回：去空白后的非空项列表；raw 为空或仅空白时返回 []。
        """
        if not raw:
            return []

        normalized = raw.strip()
        illegal_delimiters = ["。", "/", ";", "|", "\\"]
        for illegal in illegal_delimiters:
            if illegal in normalized:
                raise ValueError(
                    f"[FILTER_OPTIONS].{option_name} 包含非法分隔符 '{illegal}'；"
                    "请使用英文逗号(,)或中文逗号(，)分隔。"
                )

        # 兼容历史多行：先按行切分，再对每行按中英文逗号继续切分。
        parsed_items: List[str] = []
        for line in normalized.splitlines():
            segment = line.strip()
            if not segment:
                continue
            segment = segment.replace("，", ",")
            for token in segment.split(","):
                item = token.strip()
                if item:
                    parsed_items.append(item)
        return parsed_items

    @staticmethod
    def parse_shaixuan_config(base_dir: str) -> Dict[str, List[str]]:
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
                filters[dict_key] = FilterService.parse_filter_option_value(
                    option_name=option_name,
                    raw=raw,
                )
        except Exception as error:
            print(f"读取 filter_options.ini 出现异常: {error}")

        return filters


# Backward-compatible module-level alias
parse_shaixuan_config = FilterService.parse_shaixuan_config
