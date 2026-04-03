#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置聚合读取层（兼容入口）

真实实现位于 infra.config.config_access；本模块仅作兼容 re-export。
"""

from infra.config.config_access import (  # noqa: F401
    read_config,
    read_config_if_exists,
    read_config_tolerant_duplicates,
    read_fixed_config,
)

__all__ = [
    "read_config",
    "read_config_if_exists",
    "read_config_tolerant_duplicates",
    "read_fixed_config",
]
