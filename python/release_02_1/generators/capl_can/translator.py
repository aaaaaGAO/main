#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN 步骤翻译器：负责“人话步骤 -> CAPL”。
"""

from __future__ import annotations

from typing import Any

from core.translator import ConfigEnumParseError, IOMappingParseError
from core.common.name_sanitize import sanitize_clib_name
from core.parser import (
    ClibMatchError,
    KeywordMatchError,
    StepSyntaxError,
    parse_step_line,
)

from .models import CANRawStep, StepTranslateResult, TranslateError


class CANStepTranslator:
    """
    翻译官。

    TODO:
    - 迁移旧脚本里的 _describe_keyword_error_by_mapping 细化错误描述。
    - 迁移旧脚本里的 teststep/teststepfail 规则（含 Excel 行号注释）。
    """

    def __init__(
        self,
        *,
        io_mapping_ctx: Any = None,
        config_enum_ctx: Any = None,
        keyword_specs: dict[str, dict[str, object]] | None = None,
        clib_validator=None,
    ) -> None:
        self.io_mapping_ctx = io_mapping_ctx
        self.config_enum_ctx = config_enum_ctx
        self.keyword_specs = keyword_specs or {}
        self.clib_validator = clib_validator

    def translate(self, raw_step: CANRawStep) -> StepTranslateResult:
        line = (raw_step.content or "").strip()
        if not line:
            return StepTranslateResult()

        if not self.keyword_specs:
            # 骨架模式：尚未迁移旧关键字表时，不抛错，输出可见占位注释。
            return StepTranslateResult(
                code_lines=[f"  // TODO[translator]: 未配置 keyword_specs，原始步骤: {line}"],
                warnings=["keyword_specs 为空，使用 TODO 占位输出"],
            )

        try:
            result = parse_step_line(
                line,
                self.keyword_specs,
                mode="can",
                io_mapping_ctx=self.io_mapping_ctx,
                config_enum_ctx=self.config_enum_ctx,
                sanitize_clib_name=sanitize_clib_name,
                clib_validator=self.clib_validator,
            )
            if result is None:
                return StepTranslateResult()
            # 与 CIN 一致：根据来源列添加 //测试步骤 或 //预期结果 + 原始步骤
            role_prefix = "预期结果" if getattr(raw_step, "source", "step") == "expected" else "测试步骤"
            original = (raw_step.content or "").strip()
            suffix = f" // {role_prefix} {original}"
            new_lines = []
            for code in result.code_lines:
                line = code.rstrip()
                if line:
                    new_lines.append(line + suffix)
                else:
                    new_lines.append(line)
            return StepTranslateResult(code_lines=new_lines)
        except KeywordMatchError as e:
            return self._as_error(raw_step, "keyword", f"关键字匹配失败: {getattr(e, 'func_token', line)}")
        except IOMappingParseError as e:
            return self._as_error(raw_step, "iomapping", f"io_mapping 解析失败: {e}")
        except ConfigEnumParseError as e:
            return self._as_error(raw_step, "config_enum", f"Configuration 解析失败: {e}")
        except ClibMatchError as e:
            clib_name = getattr(e, "clib_name", "")
            return self._as_error(raw_step, "clib", f"clib表中没有{clib_name}")
        except StepSyntaxError as e:
            return self._as_error(raw_step, "syntax", f"步骤语法错误: {e}")
        except Exception as e:  # pragma: no cover
            return self._as_error(raw_step, "unknown", f"翻译异常: {e}")

    def _as_error(self, raw_step: CANRawStep, error_type: str, message: str) -> StepTranslateResult:
        escaped_step = raw_step.content.replace('"', '\\"')
        escaped_msg = message.replace('"', '\\"')
        # 根据来源标记是测试步骤还是预期结果（默认按测试步骤处理）
        if getattr(raw_step, "source", "step") == "expected":
            role_prefix = "预期结果"
        else:
            role_prefix = "测试步骤"
        return StepTranslateResult(
            code_lines=[
                # 先完整保留 Excel 中的原始内容，然后在第二段注释中标明是测试步骤/预期结果 + 错误原因
                f"  // {raw_step.content} // {role_prefix}{message}",
                f'  teststep("step","{escaped_step}");',
                f'  teststepfail("fail","{escaped_msg}");',
            ],
            errors=[
                TranslateError(
                    raw_step=raw_step.content,
                    message=message,
                    error_type=error_type,
                    excel_row=raw_step.excel_row,
                )
            ],
        )
