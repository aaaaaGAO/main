#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径解析工具（兼容入口）

真实实现位于 infra.filesystem.pathing；本模块仅作兼容 re-export。
"""

from infra.filesystem.pathing import find_config_path, get_base_dir, get_project_root  # noqa: F401

__all__ = [
    "get_base_dir",
    "find_config_path",
    "get_project_root",
]
