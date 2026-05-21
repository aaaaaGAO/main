#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDConfig 运行期委托：从 runtime_io 取实现，供 DIDConfigGeneratorService 无 hooks 调用。
"""

from __future__ import annotations

from .runtime_io import DIDConfigRuntimeIOUtility

__all__ = ["DIDConfigRuntimeIOUtility"]
