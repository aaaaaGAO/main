#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径解析工具（底层）

- get_base_dir()     : 获取运行基准目录（兼容 PyInstaller 打包）
- find_config_path() : 定位主配置文件
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

MAIN_CONFIG_CANDIDATE_NAMES = ("Configuration.ini",)
FIXED_CONFIG_CANDIDATE_NAMES = ("FixedConfig.ini",)
FILTER_OPTIONS_FILENAME = "filter_options.ini"


def resolve_main_config_write_path(base_dir: str) -> str:
    """Canonical main config save path: always config/Configuration.ini."""
    config_dir = ProjectPaths.from_base_dir(base_dir).config_dir
    return os.path.abspath(os.path.join(config_dir, MAIN_CONFIG_CANDIDATE_NAMES[0]))


def resolve_fixed_config_write_path(base_dir: str) -> str:
    """Canonical fixed config save path: always config/FixedConfig.ini."""
    config_dir = ProjectPaths.from_base_dir(base_dir).config_dir
    return os.path.abspath(os.path.join(config_dir, FIXED_CONFIG_CANDIDATE_NAMES[0]))


def resolve_filter_options_path(base_dir: str) -> str:
    """工程根目录下筛选项路径：config/filter_options.ini。"""
    config_dir = ProjectPaths.from_base_dir(base_dir).config_dir
    return os.path.abspath(os.path.join(config_dir, FILTER_OPTIONS_FILENAME))


@dataclass(frozen=True)
class ProjectPaths:
    """工程根目录下的一组标准路径。"""

    base_dir: str
    config_filename: str = "Configuration.ini"
    fixed_config_filename: str = "FixedConfig.ini"

    @classmethod
    def from_base_dir(
        cls,
        base_dir: str,
        *,
        config_filename: str = "Configuration.ini",
        fixed_config_filename: str = "FixedConfig.ini",
    ) -> "ProjectPaths":
        return cls(
            base_dir=os.path.abspath(base_dir),
            config_filename=config_filename,
            fixed_config_filename=fixed_config_filename,
        )

    @property
    def config_dir(self) -> str:
        return os.path.join(self.base_dir, "config")

    @property
    def config_path(self) -> str:
        return os.path.join(self.config_dir, self.config_filename)

    @property
    def fixed_config_path(self) -> str:
        return os.path.join(self.config_dir, self.fixed_config_filename)


class RuntimePathResolver:
    """生成器 / Web 入口常用的运行时路径解析工具。"""

    @staticmethod
    def resolve_base_dir(reference_file: str, base_dir: str | None = None) -> str:
        """优先使用显式 base_dir；否则从 reference_file 推导工程根目录。"""
        if base_dir is not None:
            return os.path.abspath(base_dir)
        return get_project_root(reference_file)

    @staticmethod
    def resolve_config_path(base_dir: str, config_path: str | None = None) -> str:
        """优先使用显式 config_path；否则返回当前工程主配置路径。"""
        return resolve_main_config_path(base_dir, config_path=config_path)


def _build_candidate_names(
    preferred_name: str | None,
    default_names: tuple[str, ...],
) -> tuple[str, ...]:
    candidate_names: list[str] = []
    if preferred_name:
        candidate_names.append(preferred_name)
    candidate_names.extend(name for name in default_names if name not in candidate_names)
    return tuple(candidate_names)


def _resolve_config_file_path(
    base_dir: str,
    *,
    explicit_path: str | None,
    preferred_name: str | None,
    default_names: tuple[str, ...],
) -> str:
    if explicit_path is not None:
        return os.path.abspath(explicit_path)

    project_paths = ProjectPaths.from_base_dir(base_dir)
    candidate_names = _build_candidate_names(preferred_name, default_names)
    for candidate_name in candidate_names:
        candidate_path = os.path.join(project_paths.config_dir, candidate_name)
        if os.path.exists(candidate_path):
            return os.path.abspath(candidate_path)
    return os.path.join(project_paths.config_dir, candidate_names[0])


def resolve_main_config_path(
    base_dir: str,
    *,
    config_path: str | None = None,
    config_filename: str | None = None,
) -> str:
    """解析当前工程主配置路径：优先显式路径，其次 config/Configuration.ini。"""
    preferred_name = None if config_filename in (None, "Configuration.ini") else config_filename
    return _resolve_config_file_path(
        base_dir,
        explicit_path=config_path,
        preferred_name=preferred_name,
        default_names=MAIN_CONFIG_CANDIDATE_NAMES,
    )


def resolve_fixed_config_path(
    base_dir: str,
    *,
    fixed_config_path: str | None = None,
    fixed_config_filename: str | None = None,
) -> str:
    """解析当前工程固定配置路径：优先显式路径，其次 config/FixedConfig.ini。"""
    preferred_name = None if fixed_config_filename in (None, "FixedConfig.ini") else fixed_config_filename
    return _resolve_config_file_path(
        base_dir,
        explicit_path=fixed_config_path,
        preferred_name=preferred_name,
        default_names=FIXED_CONFIG_CANDIDATE_NAMES,
    )


def has_project_config_marker(base_dir: str) -> bool:
    """判断目录下是否存在主配置 / 固定配置 / 筛选项标记文件，用于识别工程根目录。"""
    config_dir = ProjectPaths.from_base_dir(base_dir).config_dir
    for candidate_name in MAIN_CONFIG_CANDIDATE_NAMES + FIXED_CONFIG_CANDIDATE_NAMES + (
        FILTER_OPTIONS_FILENAME,
    ):
        if os.path.isfile(os.path.join(config_dir, candidate_name)):
            return True
    return False


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
    """获取工程根目录（含 config 下主配置 / 固定配置的目录）。打包环境为 sys.executable 所在目录；开发环境从 reference_file 向上查找。
    参数: reference_file — 参考文件路径（建议传入调用方 __file__），None 时仅在 frozen 时有效。
    返回: 工程根目录绝对路径。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    if not reference_file:
        return get_base_dir(None)
    start = os.path.dirname(os.path.abspath(reference_file))
    for _ in range(10):
        if has_project_config_marker(start):
            return start
        parent = os.path.dirname(start)
        if parent == start:
            break
        start = parent
    return start


def find_config_path(base_dir: str, filename: str = "Configuration.ini") -> str | None:
    """在 base_dir/config 下查找配置文件。
    参数: base_dir — 基准目录；filename — 配置文件名（默认 Configuration.ini）。
    返回: 绝对路径，找不到为 None。
    """
    if filename == "Configuration.ini":
        path = resolve_main_config_path(base_dir)
    else:
        path = ProjectPaths.from_base_dir(base_dir, config_filename=filename).config_path
    if os.path.exists(path):
        return path
    return None


def resolve_configured_path(base_dir: str, configured_path: str) -> str:
    """将配置中的相对/绝对路径统一解析为绝对路径；空值返回空串。"""
    configured_path = (configured_path or "").strip()
    if not configured_path:
        return ""

    normalized_path = configured_path.replace("/", os.sep)
    if not os.path.isabs(normalized_path):
        normalized_path = os.path.join(base_dir, normalized_path)
    return os.path.normpath(os.path.abspath(normalized_path))


def resolve_named_subdir(
    base_dir: str,
    configured_dir: str,
    subdir_name: str,
    *,
    create_dir: bool = False,
) -> str | None:
    """解析配置目录下的目标子目录，兼容“已指向子目录”与“父目录下存在同名子目录”两种写法。"""
    root_dir = resolve_configured_path(base_dir, configured_dir)
    if not root_dir:
        return None

    resolved_subdir = None
    if os.path.basename(root_dir).lower() == subdir_name.lower():
        resolved_subdir = root_dir
    elif os.path.isdir(root_dir):
        for entry_name in os.listdir(root_dir):
            if entry_name.lower() == subdir_name.lower():
                candidate_path = os.path.join(root_dir, entry_name)
                if os.path.isdir(candidate_path):
                    resolved_subdir = candidate_path
                    break

    if resolved_subdir is None:
        resolved_subdir = os.path.join(root_dir, subdir_name)

    if create_dir:
        try:
            os.makedirs(resolved_subdir, exist_ok=True)
        except Exception:
            return None

    return os.path.abspath(resolved_subdir)


def resolve_target_subdir(base_dir: str, configured_dir: str, subdir_name: str) -> str:
    """解析目标子目录；找不到时抛出 RuntimeError，供生成器直接使用。"""
    resolved_subdir = resolve_named_subdir(
        base_dir,
        configured_dir,
        subdir_name,
        create_dir=False,
    )
    if resolved_subdir and os.path.isdir(resolved_subdir):
        return resolved_subdir

    error_msg = (
        f"错误：输出路径下不存在 {subdir_name} 目录: "
        f"{os.path.join(resolve_configured_path(base_dir, configured_dir), subdir_name)}\n请确保该目录存在后再运行。"
    )
    print(error_msg)
    raise RuntimeError(error_msg)

