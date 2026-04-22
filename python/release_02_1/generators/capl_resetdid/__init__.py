#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators.capl_resetdid：ResetDid_Value 生成器（命名收口层）。

说明：
- 对外使用 ResetDid 命名，满足需求 3 的术语一致性。
- 运行实现沿用 capl_didinfo，避免历史链路回归。
"""

from generators.capl_didinfo.service import DIDInfoGeneratorService as ResetDidGeneratorService

# 同时导出 DIDInfoGeneratorService，统一现有调用入口
DIDInfoGeneratorService = ResetDidGeneratorService

__all__ = ["ResetDidGeneratorService", "DIDInfoGeneratorService"]
