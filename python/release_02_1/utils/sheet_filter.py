#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deprecated: 逻辑已迁移到 `utils.excel_io.ExcelUtility`。

本模块仅保留兼容导入路径，请新代码直接使用 `ExcelUtility.parse_selected_sheets`。
"""

from __future__ import annotations

from typing import Dict, Optional, Set

from utils.excel_io import ExcelUtility


def parse_selected_sheets(filter_str: Optional[str]) -> Optional[Dict[str, Set[str]]]:
    """兼容入口：转发到 ExcelUtility.parse_selected_sheets。"""
    return ExcelUtility.parse_selected_sheets(filter_str)
