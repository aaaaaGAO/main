#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.common：通用能力层（供所有生成器复用）

子模块与导出符号说明：
- pathing      : get_base_dir(reference_file=None) -> 运行基准目录；
                 find_config_path(base_dir, filename='Configuration.ini') -> 主配置路径；
                 resolve_target_subdir(base_dir, configured_dir, subdir_name) -> 目标子目录。
- input_parser : split_input_lines(text) -> 多输入行解析（按换行/分号/逗号拆分）。
- sanitizer    : sanitize_case_id(case_id) -> 用例 ID 清洗（去空格、统一格式）。
- generation_summary : build_ungenerated_reason(...) -> 构建未生成原因说明。

本包不包含业务状态，仅提供纯函数/工具，供 core 与 generators 层调用。
"""

from core.common.pathing import find_config_path, get_base_dir, resolve_target_subdir
from core.common.input_parser import split_input_lines
from core.common.generation_summary import build_ungenerated_reason
from core.common.sanitizer import sanitize_case_id

__all__ = [
    "get_base_dir",
    "find_config_path",
    "resolve_target_subdir",
    "split_input_lines",
    "build_ungenerated_reason",
    "sanitize_case_id",
]
