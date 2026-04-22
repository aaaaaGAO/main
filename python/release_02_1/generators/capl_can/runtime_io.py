#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN 生成运行期 IO 与文件名工具。

负责写 .can 文件、写 sheet 小日志、文件名 sanitize、未生成原因、关键字加载、Clib 校验器；
并提供运行时状态重置、日志初始化、映射/Clib 上下文加载、统一入口 read_cases。
供 CANGeneratorService.run_pipeline 与任务编排层调用。
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any, Callable, Optional, Tuple

from core.common.generation_summary import build_ungenerated_reason as common_build_ungenerated_reason
from core.error_module import ErrorModuleResolver
from core.generator_config import GeneratorConfig
from core.generator_logging import GeneratorLogger
from core.mapping_context import MappingContext
from core.translator import load_keyword_specs_from_excel
from services.config_constants import DEFAULT_DOMAIN_LR_REAR, SECTION_CENTRAL

from .excel_repo import CANExcelRepository
from .runtime import CANEntrypointSupport
from .translator import CANStepTranslator

lazy_pinyin = None
_HAS_PYPINYIN = False
if importlib.util.find_spec("pypinyin") is not None:
    pypinyin_module = importlib.import_module("pypinyin")
    lazy_pinyin = getattr(pypinyin_module, "lazy_pinyin", None)
    _HAS_PYPINYIN = lazy_pinyin is not None


@dataclass
class CANRuntimeContext:
    """CAN 生成运行期上下文，由编排层构造并注入，供用例读取流程使用。"""

    io_mapping_ctx: Any
    config_enum_ctx: Any
    clib_names_set: Optional[set[str]] = None


_current_runtime_ctx: Optional[CANRuntimeContext] = None


class CANRuntimeContextStore:
    """CAN 运行时上下文存取工具类。"""

    @staticmethod
    def set_context(ctx: Optional[CANRuntimeContext]) -> None:
        global _current_runtime_ctx
        _current_runtime_ctx = ctx

    @staticmethod
    def get_context() -> Optional[CANRuntimeContext]:
        return _current_runtime_ctx

    @staticmethod
    def reset() -> None:
        CANRuntimeContextStore.set_context(None)


class CANRuntimeIOUtility:
    """CAN 运行期 IO/上下文功能统一工具类入口。"""

    @staticmethod
    def write_can_text(file_path: str, content: str) -> None:
        text = content.replace("\r\n", "\n").replace("\n", "\r\n")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        try:
            with open(file_path, "wb") as binary_file:
                binary_file.write(text.encode("gb18030", errors="replace"))
        except Exception:
            with open(file_path, "wb") as binary_file:
                binary_file.write(text.encode("cp936", errors="replace"))

    @staticmethod
    def contains_chinese(text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text or ""))

    @staticmethod
    def to_pinyin_if_needed(text: str) -> str:
        text_value = str(text or "").strip()
        if not text_value or not CANRuntimeIOUtility.contains_chinese(text_value):
            return text_value
        if not _HAS_PYPINYIN or lazy_pinyin is None:
            return text_value
        try:
            return "".join(lazy_pinyin(text_value, errors=lambda non_chinese: list(non_chinese)))
        except Exception:
            return text_value

    @staticmethod
    def sanitize_filename_part(text: str) -> str:
        safe_text = CANRuntimeIOUtility.to_pinyin_if_needed(str(text or "").strip())
        safe_text = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", safe_text)
        safe_text = re.sub(r"_+", "_", safe_text).strip("_")
        return safe_text or "unknown"

    @staticmethod
    def build_ungenerated_reason(stats: dict) -> str:
        return common_build_ungenerated_reason(stats, generated_label=".can")

    @staticmethod
    def load_keyword_specs(excel_path: str, sheet_names: list[str]) -> dict:
        return load_keyword_specs_from_excel(
            excel_path,
            sheet_names,
            warn_callback=lambda msg: None,
        )

    @staticmethod
    def validate_clib_name(clib_names_set: set[str], clib_name: str) -> bool:
        return bool(clib_name) and clib_name.strip().lower() in clib_names_set

    @staticmethod
    def create_clib_validator(clib_names_set: Optional[set[str]]) -> Optional[Callable[[str], bool]]:
        if not clib_names_set:
            return None
        return partial(CANRuntimeIOUtility.validate_clib_name, clib_names_set)

    @staticmethod
    def sheet_log_ts() -> str:
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S") + f",{now.microsecond // 1000:03d}"

    @staticmethod
    def write_sheet_can_log(
        log_path: str,
        *,
        excel_name: str,
        sheet_name: str,
        cases: Any,
        can_filename: str,
        global_log_path: Optional[str] = None,
    ) -> None:
        lines: list[str] = []
        if global_log_path and os.path.isfile(global_log_path):
            try:
                with open(global_log_path, "r", encoding="utf-8", errors="ignore") as src:
                    all_lines = src.readlines()
                end_marker = f"生成文件: {can_filename}"
                end_idx = -1
                for reverse_line_index in range(len(all_lines) - 1, -1, -1):
                    if end_marker in all_lines[reverse_line_index]:
                        end_idx = reverse_line_index
                        break
                if end_idx != -1:
                    start_idx = -1
                    sheet_marker = f"处理Sheet={sheet_name}"
                    for scan_line_index in range(end_idx, -1, -1):
                        if sheet_marker in all_lines[scan_line_index]:
                            start_idx = scan_line_index
                            break
                    if start_idx == -1:
                        start_marker = f"处理Excel={excel_name}"
                        for scan_line_index in range(end_idx, -1, -1):
                            if start_marker in all_lines[scan_line_index]:
                                start_idx = scan_line_index
                                break
                    if start_idx != -1:
                        raw_lines = [ln.rstrip("\r\n") for ln in all_lines[start_idx : end_idx + 1]]
                        parse_excel_re = re.compile(r"解析 Excel 文件:")
                        lines = [ln for ln in raw_lines if not parse_excel_re.search(ln)]
            except Exception:
                pass

        if not lines:
            ts = CANRuntimeIOUtility.sheet_log_ts()
            lines.append(f"{ts}  处理Excel={excel_name}")
            fallback_errors: list[tuple[int, str]] = []
            for case in cases:
                for err in getattr(case, "error_records", []) or []:
                    err_mod = ErrorModuleResolver.resolve(err.message)
                    row = err.excel_row if err.excel_row is not None else getattr(case, "excel_row", 0)
                    line = f"{ts} ERROR 错误模块【{err_mod}】 用例ID={case.case_id} 行号：{err.excel_row}  用例步骤：{err.raw_step}  原因：{err.message}"
                    fallback_errors.append((row, line))
            fallback_errors.sort(key=lambda row_line_pair: row_line_pair[0])
            for _, log_line in fallback_errors:
                lines.append(log_line)
            ts_end = CANRuntimeIOUtility.sheet_log_ts()
            lines.append(f"{ts_end}  生成文件: {can_filename} (用例数={len(cases)})")

        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write("\n".join(lines))
            if lines:
                log_file.write("\n")

    @staticmethod
    def setup_generator_logger(base_dir: str) -> GeneratorLogger:
        return GeneratorLogger(
            base_dir,
            "generate_can_from_excel.log",
            logger_name="can_generator",
        )

    @staticmethod
    def load_mapping_context(
        gconfig: GeneratorConfig,
        base_dir: str,
        *,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
    ) -> Tuple[Any, Any]:
        if domain == SECTION_CENTRAL:
            return None, None
        mapping_ctx = MappingContext.from_config(
            gconfig.raw_config,
            base_dir=base_dir,
            config_path=gconfig.config_path,
            domain=domain,
        )
        return mapping_ctx.io_mapping, mapping_ctx.config_enum

    @staticmethod
    def load_clib_context(
        gconfig: GeneratorConfig,
        base_dir: str,
        *,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
    ) -> set:
        cin_excel_path = CANEntrypointSupport.resolve_cin_excel_path(
            gconfig, base_dir, domain=domain
        )
        return (
            CANEntrypointSupport.load_clib_names_from_excel(cin_excel_path)
            if cin_excel_path
            else set()
        )

    @staticmethod
    def read_cases(
        excel_path: str,
        keyword_specs: Optional[dict] = None,
        allowed_levels: Optional[set] = None,
        allowed_platforms: Optional[set] = None,
        allowed_models: Optional[set] = None,
        *,
        seen_case_ids: Optional[set] = None,
        clib_validator: Optional[Callable[[str], bool]] = None,
        selected_filter: Optional[dict] = None,
        runtime_context: Optional[CANRuntimeContext] = None,
    ) -> Tuple[dict, dict]:
        del seen_case_ids
        ctx = runtime_context or CANRuntimeContextStore.get_context()
        io_ctx = ctx.io_mapping_ctx if ctx else None
        enum_ctx = ctx.config_enum_ctx if ctx else None
        clib_set = ctx.clib_names_set if ctx else None

        repo = CANExcelRepository(
            base_dir=os.path.dirname(os.path.abspath(excel_path)),
            allowed_levels=allowed_levels,
            allowed_platforms=allowed_platforms,
            allowed_models=allowed_models,
            selected_filter=selected_filter,
        )
        sheet_cases, stats = repo.load_cases(excel_path)
        validator = clib_validator or CANRuntimeIOUtility.create_clib_validator(clib_set)
        translator = CANStepTranslator(
            io_mapping_ctx=io_ctx,
            config_enum_ctx=enum_ctx,
            keyword_specs=keyword_specs or {},
            clib_validator=validator,
        )
        out: dict = {}
        for item_key, case_list in sheet_cases.items():
            rows = []
            for case in case_list:
                steps = []
                errors = []
                for raw_step in case.raw_steps:
                    res = translator.translate(raw_step)
                    steps.extend(res.code_lines)
                    errors.extend(res.errors)
                case.steps = steps
                case.error_records = errors
                rows.append(
                    {
                        "case_id_raw": case.raw_id,
                        "case_id": case.case_id.replace("-", "_"),
                        "case_name": case.name,
                        "case_level": case.level,
                        "steps": case.steps,
                        "excel_filename": case.excel_name,
                        "sheet_name": case.sheet_name,
                        "excel_row": case.excel_row,
                    }
                )
            out[item_key] = rows
        return out, stats


