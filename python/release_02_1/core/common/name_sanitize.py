#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
名称清洗工具（供 CAN/CIN 生成器复用）

当前规则：
- Clib Name 中如果包含 '+' 或 '-'，在拼接 CAPL 导出/调用函数名时需要删除它们。
  例如：J_HBridge_FRHandleCtr+_Extract -> J_HBridge_FRHandleCtr_Extract
"""

from __future__ import annotations


def sanitize_clib_name(name: str) -> str:
    """删除 Clib 名称中所有 '+' 和 '-'，用于 CAPL 导出/调用函数名拼接。
    参数: name — 原始 Clib 名称。返回: 清洗后的字符串。
    """
    cleaned = str(name).strip()
    # 只按需求删除 +/-
    cleaned = cleaned.replace("+", "").replace("-", "")
    return cleaned
