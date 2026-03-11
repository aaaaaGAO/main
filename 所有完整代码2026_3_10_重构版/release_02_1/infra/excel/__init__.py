#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infra.excel：Excel 引擎与表头解析（底层）

提供 Excel 读写与表头列索引解析能力，具体实现位于本包内子模块；
本包当前不对外导出符号，调用方通过 infra 命名空间或具体 generator 使用的
ExcelService / 表头解析器 引用。后续若需统一入口，可在此 __all__ 中导出。
"""

__all__ = []

