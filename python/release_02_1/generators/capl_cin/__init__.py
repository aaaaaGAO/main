#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators.capl_cin：CAPL CIN 用例生成器

从 Excel Clib 步骤表生成 CIN 脚本，流程：读 Clib 步骤 -> 关键字翻译 -> 拼装 -> 写 .cin 文件。

导出符号与用途说明：
- CINGeneratorService(logger=None) : 总调度服务。参数 logger 为可选，用于进度与错误输出。
  run_legacy_pipeline(runtime: dict) -> str | None：执行生成；runtime 含 mapping_excel_path、sheet_names_str、
  input_excel_path、input_sheet、output_dir、output_cin_filename 等；返回生成文件路径或 None。
- CINEntrypointSupport : 入口支持，供外部调用时注入 runtime 与配置。
- CASEID_LOG_PATTERNS : 用例 ID 在日志中的匹配模式常量。
"""

from .constants import CASEID_LOG_PATTERNS
from .runtime import CINEntrypointSupport
from .service import CINGeneratorService

__all__ = ["CASEID_LOG_PATTERNS", "CINEntrypointSupport", "CINGeneratorService"]
