#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一 Excel 读写封装（供所有生成器复用）

- norm_str() / nfc_normalize() / split_input_lines() : 通用字符串与配置解析，保留在 utils
- ExcelService / merged_cell_value : openpyxl 底层封装已迁入 infra.excel.workbook，此处 re-export 保持兼容
- ColumnMapper : 表头列映射（委托 core.common.excel_header）
"""

from __future__ import annotations

import unicodedata
from typing import List, Tuple

from core.common.excel_header import ColumnMapper
from core.common.input_parser import split_input_lines as core_split_input_lines
from infra.excel.workbook import ExcelService, merged_cell_value


def norm_str(v) -> str:
    """安全地将任意值转为去首尾空白的字符串。参数: v — 任意值。返回: str。"""
    if v is None:
        return ""
    return str(v).strip()


def nfc_normalize(s: str) -> str:
    """对字符串做 Unicode NFC 归一化。参数: s — 字符串。返回: 归一化后字符串。"""
    if not s:
        return s
    return unicodedata.normalize("NFC", s)


def split_input_lines(text: str) -> List[Tuple[str, str]]:
    """解析 Inputs 配置多行格式（path | sheet1,sheet2）。参数: text — 配置文本。返回: [(path, sheets_str), ...]。"""
    return core_split_input_lines(text)


# ExcelService、merged_cell_value 已自 infra.excel.workbook 导入并 re-export，供既有调用方使用
