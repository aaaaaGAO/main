#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用例表表头定位与列索引查找（供 CAN / XML / DIDConfig / DIDInfo / UART 等生成器共用）。

委托 core.common.excel_header 统一实现。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.common.excel_header import (
    TestCaseHeaderResolver,
    find_header_row_and_col_indices as _find_header_row_and_col_indices,
)


def find_header_row_and_col_indices(
    ws: Any,
    column_aliases: Dict[str, List[str]],
    *,
    max_scan_rows: int = 30,
) -> Tuple[int, Dict[str, int], List[str]]:
    """通用表头查找：在前 max_scan_rows 行内按列别名字典定位表头行与列号。
    参数: ws — 工作表；column_aliases — 列名到别名列表的映射；max_scan_rows — 最大扫描行数。
    返回: (表头行号 1-based, 列别名->列索引 0-based, 缺失列列表)。
    """
    return _find_header_row_and_col_indices(
        ws, column_aliases, max_scan_rows=max_scan_rows
    )


def _find_testcase_header_row(ws, *, scan_rows: int = 50, debug_sheet_name: str = ""):
    """兼容别名：委托 TestCaseHeaderResolver.find_header_row。参数: ws — 工作表；scan_rows — 扫描行数；debug_sheet_name — 调试用表名。返回: 表头行号（1-based）或 -1。"""
    return TestCaseHeaderResolver.find_header_row(
        ws, scan_rows=scan_rows, max_col=50, debug_sheet_name=debug_sheet_name
    )


def _find_col_index_by_name_in_values(header_vals, search_keywords):
    """兼容别名：委托 TestCaseHeaderResolver.find_col_index。参数: header_vals — 表头行单元格值序列；search_keywords — 列名或别名。返回: 列索引（0-based）或 -1。"""
    kw = search_keywords if isinstance(search_keywords, (list, tuple)) else (search_keywords,)
    return TestCaseHeaderResolver.find_col_index(header_vals, tuple(kw))


def _find_case_type_column_index_in_values(header_vals):
    """兼容别名：委托 TestCaseHeaderResolver.find_case_type_column_index。参数: header_vals — 表头行单元格值序列。返回: 用例类型列索引（0-based）或 -1。"""
    return TestCaseHeaderResolver.find_case_type_column_index(header_vals)


__all__ = [
    "TestCaseHeaderResolver",
    "find_header_row_and_col_indices",
    "_find_testcase_header_row",
    "_find_col_index_by_name_in_values",
    "_find_case_type_column_index_in_values",
]
