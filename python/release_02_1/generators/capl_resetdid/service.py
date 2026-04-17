#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ResetDid service 命名收口层（兼容转发到 capl_didinfo）。"""

from generators.capl_didinfo.service import DIDInfoGeneratorService as ResetDidGeneratorService

# 兼容旧类名，避免对外调用中断
DIDInfoGeneratorService = ResetDidGeneratorService

__all__ = ["ResetDidGeneratorService", "DIDInfoGeneratorService"]
