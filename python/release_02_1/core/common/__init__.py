#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.common：通用能力层（供所有生成器复用）

本包保留“稳定导出入口”，避免上层调用感知底层模块迁移：
- split_input_lines / get_base_dir / find_config_path / resolve_target_subdir
  来自 infra 层。
- sanitize_case_id / build_ungenerated_reason 来自本目录实现。

本包不包含业务状态，仅提供纯函数/工具，供 core 与 generators 层调用。
"""

from core.common.generation_summary import build_ungenerated_reason
from core.common.sanitizer import sanitize_case_id
from infra.config.input_parser import split_input_lines
from infra.filesystem.pathing import find_config_path, get_base_dir, resolve_target_subdir

__all__ = [
    "get_base_dir",
    "find_config_path",
    "resolve_target_subdir",
    "split_input_lines",
    "build_ungenerated_reason",
    "sanitize_case_id",
]
