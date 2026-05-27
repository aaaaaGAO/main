#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径解析工具（infra.filesystem.pathing）。

本模块负责统一解析工程根目录、主配置/固定配置路径与运行期相对路径，
并提供 output_dir 相关目录拼接能力，供 services/generators/web 共用。
对外只暴露 `ProjectPaths` 与 `RuntimePathResolver` 两个类，避免散落函数回归。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Iterable, Literal


class PathResolutionError(RuntimeError):
    """路径解析失败异常。"""


@dataclass(frozen=True)
class ProjectPaths:
    """工程根目录下的一组标准路径封装。"""

    base_dir: str
    config_filename: str = "Configuration.ini"
    fixed_config_filename: str = "FixedConfig.ini"
    filter_options_filename: str = "filter_options.ini"

    @classmethod
    def from_base_dir(
        cls,
        base_dir: str,
        *,
        config_filename: str = "Configuration.ini",
        fixed_config_filename: str = "FixedConfig.ini",
        filter_options_filename: str = "filter_options.ini",
    ) -> "ProjectPaths":
        """从工程根目录构造标准路径对象。"""
        return cls(
            base_dir=os.path.abspath(base_dir),
            config_filename=config_filename,
            fixed_config_filename=fixed_config_filename,
            filter_options_filename=filter_options_filename,
        )

    @property
    def config_dir(self) -> str:
        """返回 config 目录绝对路径。"""
        return os.path.join(self.base_dir, "config")

    @property
    def config_path(self) -> str:
        """返回主配置文件路径。"""
        return os.path.abspath(os.path.join(self.config_dir, self.config_filename))

    @property
    def fixed_config_path(self) -> str:
        """返回固定配置文件路径。"""
        return os.path.abspath(os.path.join(self.config_dir, self.fixed_config_filename))

    @property
    def filter_options_path(self) -> str:
        """返回筛选项配置文件路径。"""
        return os.path.abspath(os.path.join(self.config_dir, self.filter_options_filename))

    @staticmethod
    def build_candidate_names(
        preferred_name: str | None,
        default_names: tuple[str, ...],
    ) -> tuple[str, ...]:
        """构造候选文件名序列。"""
        candidate_names: list[str] = []
        if preferred_name:
            candidate_names.append(preferred_name)
        candidate_names.extend(name for name in default_names if name not in candidate_names)
        return tuple(candidate_names)

    @staticmethod
    def get_base_dir(reference_file: str | None = None) -> str:
        """获取运行基准目录（支持 PyInstaller）。"""
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        if reference_file:
            return os.path.dirname(os.path.abspath(reference_file))
        return os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def has_project_config_marker(cls, base_dir: str) -> bool:
        """判断目录下是否存在工程配置标记文件。"""
        project_paths = cls.from_base_dir(base_dir)
        candidate_names = (
            project_paths.config_filename,
            project_paths.fixed_config_filename,
            project_paths.filter_options_filename,
        )
        for candidate_name in candidate_names:
            if os.path.isfile(os.path.join(project_paths.config_dir, candidate_name)):
                return True
        return False

    @classmethod
    def get_project_root(cls, reference_file: str | None = None) -> str:
        """获取工程根目录（含 config 标记文件）。"""
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        if not reference_file:
            return cls.get_base_dir(None)
        current_dir = os.path.dirname(os.path.abspath(reference_file))
        for _ in range(10):
            if cls.has_project_config_marker(current_dir):
                return current_dir
            parent_dir = os.path.dirname(current_dir)
            if parent_dir == current_dir:
                break
            current_dir = parent_dir
        return current_dir


class RuntimePathResolver:
    """生成器 / Web 入口常用的运行时路径解析工具。"""

    MAIN_CONFIG_CANDIDATE_NAMES = ("Configuration.ini",)
    FIXED_CONFIG_CANDIDATE_NAMES = ("FixedConfig.ini",)
    FILTER_OPTIONS_FILENAME = "filter_options.ini"

    @staticmethod
    def resolve_base_dir(reference_file: str, base_dir: str | None = None) -> str:
        """优先使用显式 base_dir；否则从 reference_file 推导工程根目录。"""
        if base_dir is not None:
            return os.path.abspath(base_dir)
        return ProjectPaths.get_project_root(reference_file)

    # ==================== 配置路径解析（只读，不创建目录） ====================
    @staticmethod
    def resolve_config_file_path(
        base_dir: str,
        *,
        explicit_path: str | None,
        preferred_name: str | None,
        default_names: tuple[str, ...],
    ) -> str:
        """解析配置文件最终路径。"""
        if explicit_path is not None:
            return os.path.abspath(explicit_path)
        project_paths = ProjectPaths.from_base_dir(base_dir)
        candidate_names = ProjectPaths.build_candidate_names(preferred_name, default_names)
        for candidate_name in candidate_names:
            candidate_path = os.path.join(project_paths.config_dir, candidate_name)
            if os.path.exists(candidate_path):
                return os.path.abspath(candidate_path)
        return os.path.abspath(os.path.join(project_paths.config_dir, candidate_names[0]))

    @classmethod
    def resolve_main_config_path(
        cls,
        base_dir: str,
        *,
        config_path: str | None = None,
        config_filename: str | None = None,
    ) -> str:
        """解析当前工程主配置路径：优先显式路径，其次 config/Configuration.ini。"""
        preferred_name = None if config_filename in (None, "Configuration.ini") else config_filename
        return cls.resolve_config_file_path(
            base_dir,
            explicit_path=config_path,
            preferred_name=preferred_name,
            default_names=cls.MAIN_CONFIG_CANDIDATE_NAMES,
        )

    @classmethod
    def resolve_config_path(
        cls,
        base_dir: str,
        config_path: str | None = None,
    ) -> str:
        """兼容入口：解析主配置文件路径。

        参数：
            base_dir：工程根目录。
            config_path：可选显式主配置路径；为空时默认 `config/Configuration.ini`。

        返回：
            str：主配置文件绝对路径。
        """
        return cls.resolve_main_config_path(base_dir, config_path=config_path)

    @classmethod
    def resolve_fixed_config_path(
        cls,
        base_dir: str,
        *,
        fixed_config_path: str | None = None,
        fixed_config_filename: str | None = None,
    ) -> str:
        """解析当前工程固定配置路径：优先显式路径，其次 config/FixedConfig.ini。"""
        preferred_name = (
            None if fixed_config_filename in (None, "FixedConfig.ini") else fixed_config_filename
        )
        return cls.resolve_config_file_path(
            base_dir,
            explicit_path=fixed_config_path,
            preferred_name=preferred_name,
            default_names=cls.FIXED_CONFIG_CANDIDATE_NAMES,
        )

    @staticmethod
    def resolve_main_config_write_path(base_dir: str) -> str:
        """主配置保存路径：config/Configuration.ini。"""
        return ProjectPaths.from_base_dir(base_dir).config_path

    @staticmethod
    def resolve_fixed_config_write_path(base_dir: str) -> str:
        """固定配置保存路径：config/FixedConfig.ini。"""
        return ProjectPaths.from_base_dir(base_dir).fixed_config_path

    @staticmethod
    def resolve_filter_options_path(base_dir: str) -> str:
        """筛选项配置保存路径：config/filter_options.ini。"""
        return ProjectPaths.from_base_dir(base_dir).filter_options_path

    # ==================== 通用运行期路径解析（只读，不创建目录） ====================
    @classmethod
    def find_config_path(cls, base_dir: str, filename: str = "Configuration.ini") -> str | None:
        """在 base_dir/config 下查找配置文件，存在返回绝对路径。"""
        if filename == "Configuration.ini":
            file_path = cls.resolve_main_config_path(base_dir)
        else:
            file_path = ProjectPaths.from_base_dir(base_dir, config_filename=filename).config_path
        if os.path.exists(file_path):
            return file_path
        return None

    @staticmethod
    def resolve_configured_path(base_dir: str, configured_path: str) -> str:
        """将配置中的相对/绝对路径统一解析为绝对路径；空值返回空串。"""
        configured_path = (configured_path or "").strip()
        if not configured_path:
            return ""
        normalized_path = configured_path.replace("/", os.sep)
        if not os.path.isabs(normalized_path):
            normalized_path = os.path.join(base_dir, normalized_path)
        return os.path.normpath(os.path.abspath(normalized_path))

    @staticmethod
    def resolve_runtime_path(base_dir: str | None, raw_path: str) -> str:
        """将运行期输入路径统一解析为绝对路径。"""
        candidate = (raw_path or "").strip()
        if not candidate:
            return ""
        candidate = candidate.replace("/", os.sep)
        if os.path.isabs(candidate):
            return os.path.normpath(os.path.abspath(candidate))
        if base_dir:
            return os.path.normpath(os.path.abspath(os.path.join(base_dir, candidate)))
        return os.path.normpath(os.path.abspath(candidate))

    # ==================== 输出目录供给（按参数可能产生目录副作用） ====================
    @staticmethod
    def resolve_named_subdir(
        base_dir: str,
        configured_dir: str,
        subdir_name: str,
        *,
        create_dir: bool = False,
    ) -> str | None:
        """解析配置目录下的目标子目录。

        参数：
            create_dir：为 True 时会创建目录（副作用操作）。
        """
        root_dir = RuntimePathResolver.resolve_configured_path(base_dir, configured_dir)
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

    @staticmethod
    def resolve_target_subdir(base_dir: str, configured_dir: str, subdir_name: str) -> str:
        """解析目标子目录；找不到时抛出 `PathResolutionError`。"""
        resolved_subdir = RuntimePathResolver.resolve_named_subdir(
            base_dir,
            configured_dir,
            subdir_name,
            create_dir=False,
        )
        if resolved_subdir and os.path.isdir(resolved_subdir):
            return resolved_subdir
        target_path = os.path.join(
            RuntimePathResolver.resolve_configured_path(base_dir, configured_dir),
            subdir_name,
        )
        raise PathResolutionError(
            f"错误：输出路径下不存在 {subdir_name} 目录: {target_path}\n请确保该目录存在后再运行。"
        )

    @staticmethod
    def format_relative_parts_display(relative_parts: Iterable[str]) -> str:
        """将相对路径片段格式化为 Windows 风格展示串。"""
        return "\\".join(str(part) for part in relative_parts)

    @staticmethod
    def resolve_soa_public_anchor_dir(output_dir_abs: str, project_base_dir: str) -> str:
        """解析 SOA 生成物（public/Public）锚点目录。

        统一规则：
        - 以用户选择的 output_dir 绝对路径为基准；
        - 向上回退两级目录作为锚点目录；
        - 例如 output_dir=`a/b/c`，锚点目录即 `a`。
        """
        _ = project_base_dir
        output_norm = os.path.normpath(os.path.abspath(output_dir_abs))
        if not output_norm:
            raise PathResolutionError("错误：output_dir 为空，无法定位 public/Public 锚点目录。")
        parent_level_1 = os.path.dirname(output_norm)
        parent_level_2 = os.path.dirname(parent_level_1)
        if not parent_level_1 or not parent_level_2:
            raise PathResolutionError(f"错误：output_dir 层级不足，无法向上回退两级: {output_norm}")
        if parent_level_1 == output_norm or parent_level_2 == parent_level_1:
            raise PathResolutionError(f"错误：output_dir 层级不足，无法向上回退两级: {output_norm}")
        return parent_level_2

    @classmethod
    def build_missing_output_dir_message(
        cls,
        *,
        purpose: str,
        output_dir_abs: str,
        target_path: str,
        relative_parts: Iterable[str],
    ) -> str:
        """构造面向用户的路径缺失说明（供 SOA / CAN 等严格目录校验失败时展示）。"""
        rel_display = cls.format_relative_parts_display(relative_parts)
        return (
            f"{purpose}失败：缺少必需的输出目录。\n\n"
            f"您配置的输出路径：\n  {output_dir_abs}\n\n"
            f"SOA 目录解析规则：以 output_dir 向上回退两级后再拼接目标目录。\n\n"
            f"请预先创建以下目录（工具不会自动创建）：\n  {target_path}\n\n"
            f"（在向上两级后的锚点目录下拼接：{rel_display}）"
        )

    @classmethod
    def resolve_soa_output_dir_from_absolute(
        cls,
        output_dir_abs: str,
        project_base_dir: str,
        relative_parts: Iterable[str],
        *,
        required: bool = True,
        purpose: str | None = None,
        configured_output_dir: str | None = None,
    ) -> str:
        """按 SOA 规则从已解析的 output_dir 绝对路径拼接目标目录。"""
        relative_tuple = tuple(relative_parts)
        output_norm = os.path.normpath(os.path.abspath(output_dir_abs))
        if not output_norm or not os.path.isdir(output_norm):
            raise PathResolutionError(f"错误：output_dir 目录不存在: {output_dir_abs}")
        anchor_dir = cls.resolve_soa_public_anchor_dir(output_norm, project_base_dir)
        target_path = os.path.abspath(os.path.join(anchor_dir, *relative_tuple))
        if required and not os.path.isdir(target_path):
            label = purpose or "SOA 输出路径解析"
            raise PathResolutionError(
                cls.build_missing_output_dir_message(
                    purpose=label,
                    output_dir_abs=output_norm,
                    target_path=target_path,
                    relative_parts=relative_tuple,
                )
            )
        return target_path

    @classmethod
    def resolve_soa_output_dir_relative_path(
        cls,
        base_dir: str,
        configured_output_dir: str,
        relative_parts: Iterable[str],
        *,
        required: bool = True,
        purpose: str | None = None,
    ) -> str:
        """按 SOA 规则解析 public/Public 等输出目录（严格模式，不自动创建）。"""
        output_dir_abs = cls.resolve_configured_path(base_dir, configured_output_dir)
        return cls.resolve_soa_output_dir_from_absolute(
            output_dir_abs,
            base_dir,
            relative_parts,
            required=required,
            purpose=purpose,
            configured_output_dir=configured_output_dir,
        )

    @staticmethod
    def resolve_output_dir_relative_path(
        base_dir: str,
        configured_output_dir: str,
        relative_parts: Iterable[str],
        *,
        anchor_level: Literal["self", "parent"] = "self",
        create_dir: bool = False,
        required: bool = True,
        purpose: str | None = None,
    ) -> str:
        """按 output_dir 统一规则解析目标路径。

        参数：
            create_dir：为 True 时会创建目标目录（副作用操作）。
            required：为 True 且目录不存在时抛出异常。
            purpose：目录缺失时写入错误文案的用途说明（如「SOA Node 生成」）。
        """
        relative_tuple = tuple(relative_parts)
        output_dir_abs = RuntimePathResolver.resolve_configured_path(base_dir, configured_output_dir)
        if not output_dir_abs or not os.path.isdir(output_dir_abs):
            raise PathResolutionError(
                f"错误：output_dir 目录不存在: {output_dir_abs or configured_output_dir}"
            )
        anchor_dir = output_dir_abs if anchor_level == "self" else os.path.dirname(output_dir_abs)
        target_path = os.path.abspath(os.path.join(anchor_dir, *relative_tuple))
        if create_dir:
            os.makedirs(target_path, exist_ok=True)
        if required and not os.path.isdir(target_path):
            label = purpose or "输出路径解析"
            raise PathResolutionError(
                RuntimePathResolver.build_missing_output_dir_message(
                    purpose=label,
                    output_dir_abs=output_dir_abs,
                    target_path=target_path,
                    relative_parts=relative_tuple,
                )
            )
        return target_path

    @staticmethod
    def resolve_output_relative_dir(
        base_dir: str,
        configured_output_dir: str,
        relative_parts: tuple[str, ...],
        *,
        create_dir: bool = False,
    ) -> str:
        """在用户 output_dir 下按相对目录链解析目标目录。

        参数：
            create_dir：为 True 时会创建目标目录（副作用操作）。
        """
        output_dir_abs = RuntimePathResolver.resolve_configured_path(base_dir, configured_output_dir)
        if not output_dir_abs or not os.path.isdir(output_dir_abs):
            raise PathResolutionError(
                f"错误：output_dir 目录不存在: {output_dir_abs or configured_output_dir}"
            )
        target_dir = os.path.join(output_dir_abs, *relative_parts)
        if create_dir:
            os.makedirs(target_dir, exist_ok=True)
            return os.path.abspath(target_dir)
        if not os.path.isdir(target_dir):
            rel_hint = "/".join(relative_parts)
            raise PathResolutionError(f"错误：输出目录不存在: {target_dir}\n请确保已创建 {rel_hint}。")
        return os.path.abspath(target_dir)

    @staticmethod
    def list_excel_files(excel_dir: str) -> list[str]:
        """列出目录下的 Excel 文件（忽略临时文件），按文件名排序。"""
        exts = (".xlsx", ".xlsm", ".xltx", ".xltm")
        files = []
        for name in os.listdir(excel_dir):
            if name.startswith("~$"):
                continue
            if name.lower().endswith(exts):
                files.append(os.path.join(excel_dir, name))
        return sorted(files, key=lambda file_path: os.path.basename(file_path).lower())
