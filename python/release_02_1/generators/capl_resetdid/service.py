#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ResetDid service 命名收口层（转发到 capl_didinfo）。"""

from generators.capl_didinfo.service import DIDInfoGeneratorService as ResetDidGeneratorService

# 同时导出 DIDInfoGeneratorService，统一现有调用入口
DIDInfoGeneratorService = ResetDidGeneratorService

__all__ = ["ResetDidGeneratorService", "DIDInfoGeneratorService"]
