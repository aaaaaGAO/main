#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDConfig 运行期委托：从 runtime_io 与公共模块取实现，供 DIDConfigGeneratorService 无 hooks 调用。
"""

from __future__ import annotations

from . import runtime_io as didconfig_runtime_io

resolve_base_dir = didconfig_runtime_io.resolve_base_dir
load_runtime = didconfig_runtime_io.load_runtime
init_logging = didconfig_runtime_io.init_logging
get_progress_level = didconfig_runtime_io.get_progress_level

__all__ = [
    "resolve_base_dir",
    "load_runtime",
    "init_logging",
    "get_progress_level",
]
