#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径解析工具（兼容入口）

真实实现位于 infra.filesystem.pathing；本模块仅作兼容 re-export。
"""

from infra.filesystem.pathing import (  # noqa: F401
    FIXED_CONFIG_CANDIDATE_NAMES,
    MAIN_CONFIG_CANDIDATE_NAMES,
    ProjectPaths,
    find_config_path,
    get_base_dir,
    get_project_root,
    has_project_config_marker,
    resolve_fixed_config_path,
    resolve_fixed_config_write_path,
    resolve_main_config_path,
    resolve_main_config_write_path,
    resolve_configured_path,
    resolve_named_subdir,
    resolve_target_subdir,
)

__all__ = [
    "MAIN_CONFIG_CANDIDATE_NAMES",
    "FIXED_CONFIG_CANDIDATE_NAMES",
    "ProjectPaths",
    "get_base_dir",
    "find_config_path",
    "get_project_root",
    "has_project_config_marker",
    "resolve_main_config_path",
    "resolve_main_config_write_path",
    "resolve_fixed_config_path",
    "resolve_fixed_config_write_path",
    "resolve_configured_path",
    "resolve_named_subdir",
    "resolve_target_subdir",
]
