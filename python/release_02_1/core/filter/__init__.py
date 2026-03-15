#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.filter：领域层筛选器（门面）

导出符号说明：
- CaseFilter(allowed_levels=None, allowed_platforms=None, allowed_models=None)
  用例筛选器。参数均为可选集合：允许的等级(S/A/B/C)、平台、车型；None 或空表示该维度不过滤。
  过滤顺序：等级 -> 平台 -> 车型 -> 用例类型（自动测试）。通过 filter_row() 判断单行是否保留。
  内部 stats（FilterStats）记录各维度过滤计数。
"""

from core.case_filter import CaseFilter

__all__ = [
    "CaseFilter",
]

