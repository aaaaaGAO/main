#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOA 相关 Excel 读写的公共工具。

本模块提供两类能力：
- Excel workbook 的缓存打开/关闭（支持跨生成器复用，避免重复 open）；
- Service_Deployment/Interface 常见“勾选标记”的统一识别。

供 `generators/capl_soa` 下的 SOA 生成器复用，避免各文件重复实现同一逻辑。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from infra.excel.workbook import ExcelService


CLIENT_MARKER_TEXTS: frozenset[str] = frozenset({"x", "×", "X"})


def normalize_cell_text(value: Any) -> str:
    """将任意单元格值标准化为去首尾空白的字符串。"""
    if value is None:
        return ""
    return str(value).strip()


def is_client_marker(value: Any) -> bool:
    """判断单元格是否表示“勾选”。

    规则：
    - 仅识别 `x` / `X` / `×`；
    - 其他（如 √/1/yes/true）均不视为勾选。
    """
    marker_text = normalize_cell_text(value)
    if not marker_text:
        return False
    return marker_text.casefold() in {item.casefold() for item in CLIENT_MARKER_TEXTS}


@dataclass(frozen=True)
class CachedWorkbook:
    """缓存打开 workbook 的结果容器。"""

    workbook: Any
    should_close: bool
    normalized_excel_path: str


def open_workbook_cached(excel_path: str, *, workbook_cache: dict[str, Any] | None) -> CachedWorkbook:
    """以可选缓存方式打开 Excel workbook。

    参数：
    - excel_path: Excel 路径（支持相对/绝对）。
    - workbook_cache: 可选 workbook 缓存；key 使用 normcase 后的绝对路径。

    返回：
    - CachedWorkbook: 含 workbook、是否需要调用方关闭、以及规范化后的路径 key。
    """
    absolute_excel = os.path.abspath(excel_path.strip())
    normalized_excel = os.path.normcase(absolute_excel)
    should_close = workbook_cache is None
    workbook = None
    if workbook_cache is not None:
        workbook = workbook_cache.get(normalized_excel)
    if workbook is None:
        workbook = ExcelService.open_workbook(normalized_excel, data_only=True, read_only=False)
        if workbook_cache is not None:
            workbook_cache[normalized_excel] = workbook
    return CachedWorkbook(workbook=workbook, should_close=should_close, normalized_excel_path=normalized_excel)

