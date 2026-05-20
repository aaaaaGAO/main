#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""表头解析兼容出口。

本模块已收敛为 `infra.excel.header` 的兼容导出层，避免上层继续依赖代理函数。
新代码应直接从 `infra.excel.header` 导入 `TestCaseHeaderResolver`
与 `find_header_row_and_col_indices`。
"""

from __future__ import annotations

from infra.excel.header import (
    TestCaseHeaderResolver,
    find_header_row_and_col_indices,
)

__all__ = [
    "TestCaseHeaderResolver",
    "find_header_row_and_col_indices",
]
