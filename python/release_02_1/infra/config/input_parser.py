#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多输入语法标准解析器（底层解析）

解析 "path | sheet1,sheet2" 多行配置格式。
"""

from __future__ import annotations

from typing import List, Tuple


def split_input_lines(text: str) -> List[Tuple[str, str]]:
    """解析 Inputs 配置多行格式（path | sheet1,sheet2 或 path）。
    参数: text — 配置文本，支持 # / ; 注释行。
    返回: [(path, sheets_str), ...]，sheets_str 可为空或 "*"。
    """
    out: List[Tuple[str, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "|" in line:
            p, s = [x.strip() for x in line.split("|", 1)]
        else:
            p, s = line.strip(), ""
        if p:
            out.append((p, s))
    return out

