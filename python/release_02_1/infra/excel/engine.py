#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel 读写引擎（底层）

硬核 openpyxl 封装位于 infra.excel.workbook；本模块作为统一入口对外暴露。
通用字符串处理保留在 utils.excel_io.StringUtility，由调用方按类方法使用。
"""

from __future__ import annotations

from infra.excel.workbook import ExcelService
from utils.excel_io import StringUtility

__all__ = [
    "StringUtility",
    "ExcelService",
]

