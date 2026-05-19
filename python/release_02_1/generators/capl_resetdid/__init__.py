#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators.capl_resetdid：ResetDid_Value（DID 矩阵）生成器。

- ``ResetDidGeneratorService``：生成服务入口；构造参数与 ``run_pipeline`` 见 service 模块。
"""

from __future__ import annotations

from .service import ResetDidGeneratorService

__all__ = ["ResetDidGeneratorService"]
