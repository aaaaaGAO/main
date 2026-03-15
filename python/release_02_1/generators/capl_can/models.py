#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN 生成器领域模型（重构骨架）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CANRawStep:
    """Excel 原始步骤行（尚未翻译为 CAPL）。"""

    content: str
    source: str = "step"
    excel_row: int = 0


@dataclass(slots=True)
class TranslateError:
    """单条步骤翻译错误。"""

    raw_step: str
    message: str
    error_type: str = "unknown"
    excel_row: int = 0


@dataclass(slots=True)
class StepTranslateResult:
    """翻译器返回值：代码行 + 错误 + 告警。"""

    code_lines: list[str] = field(default_factory=list)
    errors: list[TranslateError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


@dataclass(slots=True)
class CANTestCase:
    """
    CAN 用例聚合对象。

    说明：
    - raw_steps：Excel 原始行，供 translator 消费
    - steps：翻译后 CAPL 代码行，供 renderer 消费
    """

    case_id: str
    name: str
    level: str
    raw_id: str = ""
    case_id_had_issues: bool = False  # True=清洗过/重复，生成时加 teststep("warning",...)
    case_id_issue_type: str = ""  # "sanitized"=空格/非法字符清洗, "duplicate"=重复改名为id_1/id_2
    duplicate_original_id: str = ""  # 仅当 duplicate 时：原始 case_id（改名前的）
    excel_row: int = 0
    excel_name: str = ""
    sheet_name: str = ""
    platform: str = ""
    model: str = ""
    case_type: str = ""
    raw_steps: list[CANRawStep] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    error_records: list[TranslateError] = field(default_factory=list)
    target_path: str = ""
