#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDConfig 运行期委托：从 runtime_io 与公共模块取实现，供 DIDConfigGeneratorService 无 hooks 调用。
"""

from __future__ import annotations

from core.excel_header import find_header_row_and_col_indices
from utils.excel_io import merged_cell_value, norm_str
from infra.filesystem import resolve_target_subdir

from .runtime_io import (
    get_progress_level,
    init_logging,
    load_runtime,
    resolve_base_dir,
)
