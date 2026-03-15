#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel 读写引擎（底层）

硬核 openpyxl 封装位于 infra.excel.workbook；本模块作为统一入口对外暴露。
nfc_normalize、norm_str 等通用字符串处理保留在 utils，此处 re-export 便于 infra 调用方一站式引用。
"""

from __future__ import annotations

from infra.excel.workbook import ExcelService, merged_cell_value
from utils.excel_io import nfc_normalize, norm_str

__all__ = [
    "ExcelService",
    "merged_cell_value",
    "nfc_normalize",
    "norm_str",
]

