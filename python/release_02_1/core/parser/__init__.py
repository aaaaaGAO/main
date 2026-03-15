#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.parser：领域层解析器（门面）

将单行步骤文本解析为 CAPL 代码片段，供 CAN/CIN 等生成器使用。

导出符号说明：
- parse_step_line(line, ...) -> ParseResult
  解析一行步骤；需传入 io_mapping、config_enum、keyword_specs 等上下文。详见 step_parser。
- ParseResult : 具名元组，含 code_lines（生成的 CAPL 行列表）、original_line_full（原始行）。
- KeywordMatchError(line, func_token) : 关键字未匹配异常。
- StepSyntaxError : 步骤语法错误（参数不足或格式错误）。
- ClibMatchError(line, clib_name) : Clib 在配置表中未找到。
"""

from core.parser.step_parser import (
    ClibMatchError,
    KeywordMatchError,
    ParseResult,
    StepSyntaxError,
    parse_step_line,
)

__all__ = [
    "parse_step_line",
    "ParseResult",
    "KeywordMatchError",
    "StepSyntaxError",
    "ClibMatchError",
]

