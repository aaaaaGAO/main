#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径解析工具（底层）

- get_base_dir()     : 获取运行基准目录（兼容 PyInstaller 打包）
- find_config_path() : 定位 Configuration.txt
"""

from __future__ import annotations

import os
import sys


def get_base_dir(reference_file: str | None = None) -> str:
    """获取运行基准目录。打包环境为 sys.executable 所在目录；开发环境为 reference_file 所在目录。
    参数: reference_file — 参考文件路径，None 时用本模块 __file__。
    返回: 绝对路径字符串。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    if reference_file:
        return os.path.dirname(os.path.abspath(reference_file))
    return os.path.dirname(os.path.abspath(__file__))


def get_project_root(reference_file: str | None = None) -> str:
    """获取工程根目录（含 config/Configuration.txt 的目录）。打包环境为 sys.executable 所在目录；开发环境从 reference_file 向上查找。
    参数: reference_file — 参考文件路径（建议传入调用方 __file__），None 时仅在 frozen 时有效。
    返回: 工程根目录绝对路径。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    if not reference_file:
        return get_base_dir(None)
    start = os.path.dirname(os.path.abspath(reference_file))
    for _ in range(10):
        # 工程根目录标识：存在 config/Configuration.txt
        if os.path.isfile(os.path.join(start, "config", "Configuration.txt")):
            return start
        parent = os.path.dirname(start)
        if parent == start:
            break
        start = parent
    return start


def find_config_path(base_dir: str, filename: str = "Configuration.txt") -> str | None:
    """在 base_dir/config 下查找配置文件。
    参数: base_dir — 基准目录；filename — 配置文件名（默认 Configuration.txt）。
    返回: 绝对路径，找不到为 None。
    """
    path = os.path.abspath(os.path.join(base_dir, "config", filename))
    if os.path.exists(path):
        return path
    return None

