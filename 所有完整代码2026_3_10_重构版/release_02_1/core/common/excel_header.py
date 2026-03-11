#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
表头/列解析公共层（兼容入口）

真实实现位于 infra.excel.header；本模块仅作兼容 re-export。
"""

from infra.excel.header import (  # noqa: F401
    ColumnMapper,
    TestCaseHeaderResolver,
    find_header_row_and_col_indices,
)

__all__ = [
    "ColumnMapper",
    "find_header_row_and_col_indices",
    "TestCaseHeaderResolver",
]
