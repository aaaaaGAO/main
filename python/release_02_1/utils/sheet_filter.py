#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sheet 勾选解析（供 CAN / XML 等生成器共用）。

解析前端传递的 'table1|sheet1,table1|sheet2' 格式，
返回 { table_key_lower: { sheet1, sheet2 } }，None 表示不过滤（生成全部）。
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Set


def parse_selected_sheets(filter_str: Optional[str]) -> Optional[Dict[str, Set[str]]]:
    """解析前端勾选传递的 'table1|sheet1,table1|sheet2' 格式。
    参数: filter_str — 勾选字符串，空或 None 表示不过滤。
    返回: { 表名小写: { sheet1, sheet2 }, ... } 或 None。
    """
    filter_map: Dict[str, Set[str]] = {}
    if not filter_str or not str(filter_str).strip():
        return None
    for selected_item in str(filter_str).split(","):
        if "|" not in selected_item:
            continue
        table, sheet = selected_item.split("|", 1)
        table_key = os.path.basename(str(table).strip()).lower()
        sheet_val = str(sheet).strip().lower()
        if not table_key or not sheet_val:
            continue
        filter_map.setdefault(table_key, set()).add(sheet_val)
    return filter_map if filter_map else None
