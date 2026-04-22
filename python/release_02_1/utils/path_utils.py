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
from pathlib import Path

from infra.filesystem import (
    FIXED_CONFIG_CANDIDATE_NAMES,
    MAIN_CONFIG_CANDIDATE_NAMES,
    ProjectPaths,
    find_config_path as pathing_find_config_path,
    get_base_dir as pathing_get_base_dir,
    get_project_root as pathing_get_project_root,
    has_project_config_marker as pathing_has_project_config_marker,
    resolve_fixed_config_path as pathing_resolve_fixed_config_path,
    resolve_fixed_config_write_path as pathing_resolve_fixed_config_write_path,
    resolve_main_config_path as pathing_resolve_main_config_path,
    resolve_main_config_write_path as pathing_resolve_main_config_write_path,
    resolve_configured_path as pathing_resolve_configured_path,
    resolve_runtime_path as pathing_resolve_runtime_path,
    resolve_target_subdir as pathing_resolve_target_subdir,
)


def get_base_dir(reference_file: str | None = None) -> str:
    """获取运行基准目录。参数: reference_file — 参考文件路径，None 用 __file__。返回: 绝对路径。"""
    return pathing_get_base_dir(reference_file if reference_file is not None else __file__)


def find_config_path(base_dir: str, filename: str = "Configuration.ini") -> str | None:
    """在 base_dir 及 release/ 下查找配置文件。参数: base_dir — 基准目录；filename — 配置文件名。返回: 绝对路径或 None。"""
    return pathing_find_config_path(base_dir, filename)


def get_project_root(reference_file: str | None = None) -> str:
    """获取工程根目录（含主配置 / 固定配置标记文件的目录），统一路径解析逻辑。
    参数: reference_file — 建议传入调用方 __file__，None 时仅在打包环境下有效。
    返回: 工程根目录绝对路径。
    """
    return pathing_get_project_root(reference_file)


def has_project_config_marker(base_dir: str) -> bool:
    """判断目录下是否存在主配置 / 固定配置标记文件。"""
    return pathing_has_project_config_marker(base_dir)


def resolve_main_config_path(
    base_dir: str,
    *,
    config_path: str | None = None,
    config_filename: str | None = None,
) -> str:
    """解析当前主配置路径：config/Configuration.ini（或显式路径）。"""
    return pathing_resolve_main_config_path(
        base_dir,
        config_path=config_path,
        config_filename=config_filename,
    )


def resolve_fixed_config_path(
    base_dir: str,
    *,
    fixed_config_path: str | None = None,
    fixed_config_filename: str | None = None,
) -> str:
    """解析当前固定配置路径：config/FixedConfig.ini（或显式路径）。"""
    return pathing_resolve_fixed_config_path(
        base_dir,
        fixed_config_path=fixed_config_path,
        fixed_config_filename=fixed_config_filename,
    )


def resolve_main_config_write_path(base_dir: str) -> str:
    """Canonical main config save path: config/Configuration.ini."""
    return pathing_resolve_main_config_write_path(base_dir)


def resolve_fixed_config_write_path(base_dir: str) -> str:
    """Canonical fixed config save path: config/FixedConfig.ini."""
    return pathing_resolve_fixed_config_write_path(base_dir)


def resolve_configured_path(base_dir: str, configured_path: str) -> str:
    """将配置中的相对/绝对路径统一解析为绝对路径。"""
    return pathing_resolve_configured_path(base_dir, configured_path)


def resolve_runtime_path(base_dir: str | None, raw_path: str) -> str:
    """将运行期输入路径统一解析为绝对路径。"""
    return pathing_resolve_runtime_path(base_dir, raw_path)


def resolve_target_subdir(base_dir: str, configured_dir: str, subdir_name: str) -> str:
    """智能解析目标子目录（如 TESTmode / Configuration）：末级名匹配或其下同名子目录，不区分大小写。
    参数: base_dir — 工程根目录；configured_dir — 配置中的输出目录；subdir_name — 子目录名。
    返回: 子目录绝对路径。找不到抛 RuntimeError。
    """
    return pathing_resolve_target_subdir(base_dir, configured_dir, subdir_name)


# 旧调用名映射（CAN/CIN/XML 中曾用 _resolve_target_subdir_smart）
resolve_target_subdir_smart = resolve_target_subdir


def list_excel_files(excel_dir: str) -> list[str]:
    """
    列出目录下所有 Excel 文件路径（.xlsx/.xlsm/.xltx/.xltm）。
    形参：excel_dir - 输入目录绝对路径。
    返回：排序后的完整路径列表。
    """
    exts = (".xlsx", ".xlsm", ".xltx", ".xltm")
    files = []
    for name in os.listdir(excel_dir):
        if name.startswith("~$"):
            continue
        if name.lower().endswith(exts):
            files.append(os.path.join(excel_dir, name))
    return sorted(
        files,
        key=lambda file_path: os.path.basename(file_path).lower(),
    )


