#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径解析工具（供所有生成器复用）

- get_base_dir()          : 获取运行基准目录（兼容 PyInstaller 打包）
- resolve_target_subdir() : 智能查找输出子目录（TESTmode / Configuration）
- find_config_path()      : 定位 Configuration.txt
"""

from __future__ import annotations

import os
from pathlib import Path

from core.common.pathing import find_config_path as _find_config_path
from core.common.pathing import get_base_dir as _get_base_dir
from core.common.pathing import get_project_root as _get_project_root


def get_base_dir(reference_file: str | None = None) -> str:
    """获取运行基准目录。参数: reference_file — 参考文件路径，None 用 __file__。返回: 绝对路径。"""
    return _get_base_dir(reference_file if reference_file is not None else __file__)


def find_config_path(base_dir: str, filename: str = "Configuration.txt") -> str | None:
    """在 base_dir 及 release/ 下查找配置文件。参数: base_dir — 基准目录；filename — 配置文件名。返回: 绝对路径或 None。"""
    return _find_config_path(base_dir, filename)


def get_project_root(reference_file: str | None = None) -> str:
    """获取工程根目录（含 Configuration.txt 的目录），统一路径解析逻辑。
    参数: reference_file — 建议传入调用方 __file__，None 时仅在打包环境下有效。
    返回: 工程根目录绝对路径。
    """
    return _get_project_root(reference_file)


def resolve_target_subdir(base_dir: str, configured_dir: str, subdir_name: str) -> str:
    """智能解析目标子目录（如 TESTmode / Configuration）：末级名匹配或其下同名子目录，不区分大小写。
    参数: base_dir — 工程根目录；configured_dir — 配置中的输出目录；subdir_name — 子目录名。
    返回: 子目录绝对路径。找不到抛 RuntimeError。
    """
    if not os.path.isabs(configured_dir):
        configured_dir = os.path.join(base_dir, configured_dir)
    configured_dir = os.path.abspath(configured_dir)

    if os.path.basename(configured_dir).lower() == subdir_name.lower():
        return configured_dir

    if os.path.isdir(configured_dir):
        for entry in os.listdir(configured_dir):
            if entry.lower() == subdir_name.lower():
                full_path = os.path.join(configured_dir, entry)
                if os.path.isdir(full_path):
                    return os.path.abspath(full_path)

    error_msg = (
        f"错误：输出路径下不存在 {subdir_name} 目录: "
        f"{os.path.join(configured_dir, subdir_name)}\n请确保该目录存在后再运行。"
    )
    print(error_msg)
    raise RuntimeError(error_msg)


# 兼容旧调用名（CAN/CIN/XML 中曾用 _resolve_target_subdir_smart）
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
    return sorted(files, key=lambda p: os.path.basename(p).lower())


