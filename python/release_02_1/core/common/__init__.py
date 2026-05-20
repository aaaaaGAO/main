#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.common：通用能力层（供所有生成器复用）

本包保留“稳定导出入口”，避免上层调用感知底层模块迁移：
- split_input_lines / get_base_dir / find_config_path / resolve_target_subdir
  来自 infra 层。
- sanitize_case_id / split_input_lines 来自 utils 统一工具类，build_ungenerated_reason 来自本目录实现。

本包不包含业务状态，仅提供纯函数/工具，供 core 与 generators 层调用。
"""

from core.common.generation_summary import build_ungenerated_reason
from utils.excel_io import StringUtility
from infra.filesystem.pathing import ProjectPaths, RuntimePathResolver
from utils.excel_io import ExcelUtility

split_input_lines = ExcelUtility.split_input_lines
sanitize_case_id = StringUtility.sanitize_case_id
get_base_dir = ProjectPaths.get_base_dir
find_config_path = RuntimePathResolver.find_config_path
resolve_target_subdir = RuntimePathResolver.resolve_target_subdir

__all__ = [
    "get_base_dir",
    "find_config_path",
    "resolve_target_subdir",
    "split_input_lines",
    "build_ungenerated_reason",
    "sanitize_case_id",
]
