#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UART 运行期委托：从 runtime_io 取实现，供 UARTGeneratorService 无 hooks 调用。
"""

from __future__ import annotations

from .runtime_io import UARTExcelParser, UARTRuntimeIOUtility

__all__ = [
    "UARTRuntimeIOUtility",
    "UARTExcelParser",
]
