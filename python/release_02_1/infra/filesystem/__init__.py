#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infra.filesystem：路径与文件系统相关能力（底层）

导出符号与参数说明：
- ProjectPaths(base_dir, config_filename='Configuration.ini', fixed_config_filename='FixedConfig.ini')
  工程根目录下的一组标准路径封装，含 config_dir/config_path/fixed_config_path。
- get_base_dir(reference_file=None) -> str
  运行基准目录。打包时为 exe 所在目录；开发时为 reference_file 所在目录，None 则用本模块 __file__。
- get_project_root(reference_file=None) -> str
  工程根目录（含主配置 / 固定配置标记文件的目录）。打包时为 exe 所在目录；开发时从 reference_file 向上查找。
- find_config_path(base_dir: str, filename='Configuration.ini') -> str | None
  在 base_dir 及 base_dir/../release 下查找配置文件，返回找到的绝对路径，未找到返回 None。
- resolve_configured_path(base_dir: str, configured_path: str) -> str
  将配置中的相对/绝对路径统一解析为绝对路径。
- resolve_named_subdir(base_dir: str, configured_dir: str, subdir_name: str, create_dir=False) -> str | None
  解析配置目录下的目标子目录，兼容“父目录”与“已直接指向子目录”两种写法。
- resolve_target_subdir(base_dir: str, configured_dir: str, subdir_name: str) -> str
  解析目标子目录；找不到时抛出 RuntimeError，供生成器直接使用。
"""

from infra.filesystem.pathing import (
    FILTER_OPTIONS_FILENAME,
    FIXED_CONFIG_CANDIDATE_NAMES,
    MAIN_CONFIG_CANDIDATE_NAMES,
    ProjectPaths,
    RuntimePathResolver,
    find_config_path,
    get_base_dir,
    get_project_root,
    has_project_config_marker,
    resolve_filter_options_path,
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
    "FILTER_OPTIONS_FILENAME",
    "ProjectPaths",
    "RuntimePathResolver",
    "get_base_dir",
    "find_config_path",
    "get_project_root",
    "has_project_config_marker",
    "resolve_main_config_path",
    "resolve_main_config_write_path",
    "resolve_fixed_config_path",
    "resolve_fixed_config_write_path",
    "resolve_filter_options_path",
    "resolve_configured_path",
    "resolve_named_subdir",
    "resolve_target_subdir",
]

