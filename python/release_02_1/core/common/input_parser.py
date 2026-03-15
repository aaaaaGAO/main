#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多输入语法标准解析器（兼容入口）

真实实现位于 infra.config.input_parser；本模块仅作兼容 re-export。
"""

from infra.config.input_parser import split_input_lines  # noqa: F401

__all__ = [
    "split_input_lines",
]
