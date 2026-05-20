#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径解析工具（供所有生成器复用）

- get_base_dir()          : 获取运行基准目录（支持 PyInstaller 打包）
- resolve_target_subdir() : 智能查找输出子目录（TESTmode / Configuration）
- find_config_path()      : 定位主配置文件
"""

from __future__ import annotations

import os

from infra.filesystem import ProjectPaths, RuntimePathResolver


# 旧调用名映射（CAN/CIN/XML 中曾用 _resolve_target_subdir_smart）
resolve_target_subdir_smart = RuntimePathResolver.resolve_target_subdir

# 兼容导出：统一映射到对象化入口
find_config_path = RuntimePathResolver.find_config_path
get_base_dir = ProjectPaths.get_base_dir
get_project_root = ProjectPaths.get_project_root
has_project_config_marker = ProjectPaths.has_project_config_marker
resolve_fixed_config_path = RuntimePathResolver.resolve_fixed_config_path
resolve_fixed_config_write_path = RuntimePathResolver.resolve_fixed_config_write_path
resolve_main_config_path = RuntimePathResolver.resolve_main_config_path
resolve_main_config_write_path = RuntimePathResolver.resolve_main_config_write_path
resolve_configured_path = RuntimePathResolver.resolve_configured_path
resolve_runtime_path = RuntimePathResolver.resolve_runtime_path
resolve_target_subdir = RuntimePathResolver.resolve_target_subdir


def list_excel_files(excel_dir: str) -> list[str]:
    """
    列出目录下所有 Excel 文件路径（.xlsx/.xlsm/.xltx/.xltm）。
    形参：excel_dir - 输入目录绝对路径。
    返回：排序后的完整路径列表。
    """
    return RuntimePathResolver.list_excel_files(excel_dir)


