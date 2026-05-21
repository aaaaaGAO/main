#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CIN 生成运行期 IO 与步骤解析。

负责 load_keyword_specs、read_clib_steps、render_step_lines、generate_content；
并提供 reset_runtime_state、setup_generator_logger、load_mapping_context，供任务编排与统一入口使用。
"""

from __future__ import annotations

import configparser
import importlib
import importlib.util
import os
from typing import Callable, ClassVar, Optional, Tuple

from infra.excel.workbook import ExcelService

from core.generator_logging import GeneratorLogger
from services.config_constants import DEFAULT_DOMAIN_LR_REAR

from .constants import CASEID_LOG_PATTERNS
from .runtime import CINEntrypointSupport

from core.error_module import ErrorModuleResolver
from core.parser import KeywordMatchError, StepParser, StepSyntaxError
from core.step_error_detail import StepErrorDetailBuilder, format_step_error_lines
from core.translator import (
    ConfigEnumParseError,
    IOMappingParseError,
    load_keyword_specs_from_excel,
)
from core.translator.config_enum import ConfigEnumContext
from core.translator.io_mapping import IOMappingContext
from utils.excel_io import StringUtility

ProgressFormatter = None
SubstringFilter = None
logger_module_name = "infra.logger" if importlib.util.find_spec("infra.logger") is not None else "utils.logger"
if importlib.util.find_spec(logger_module_name) is not None:
    logger_module = importlib.import_module(logger_module_name)
    ProgressFormatter = getattr(logger_module, "ProgressFormatter", None)
    SubstringFilter = getattr(logger_module, "SubstringFilter", None)

# 模块内保存上一次解析错误，供 render_step_lines 中 build_detail 使用（已迁入 CINRuntimeIOUtility）

class CINRuntimeIOUtility:
    """CIN 运行期 IO/步骤解析统一工具类。"""

    last_parse_error_state: ClassVar[dict] = {"type": None, "reason": ""}
    io_mapping_context: ClassVar[Optional[IOMappingContext]] = None
    config_enum_context: ClassVar[Optional[ConfigEnumContext]] = None

    @staticmethod
    def ignore_warning_message(_message: str) -> None:
        """默认忽略关键字读取警告回调。"""
        return None

    @staticmethod
    def create_progress_formatter(format_string: str) -> ProgressFormatter:
        """创建进度日志格式化器。"""
        return ProgressFormatter(format_string)

    @staticmethod
    def load_keyword_specs(
        excel_path: str,
        sheet_names: list[str],
        *,
        warn_callback: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """读取关键字-CAPL 映射表。"""
        return load_keyword_specs_from_excel(
            excel_path,
            sheet_names,
            warn_callback=warn_callback or CINRuntimeIOUtility.ignore_warning_message,
        )

    @staticmethod
    def read_clib_steps(excel_path: str, clib_sheet: Optional[str] = None) -> tuple[str, list]:
        """
        从 Clib Excel 读取 Name/Step 列，按 Name 聚合步骤。
        返回 (sheet_title, [(name_str, [(step_text, excel_row_num), ...]), ...])。
        """
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"找不到 Clib Excel 文件: {excel_path}")

        try:
            wb = ExcelService.open_workbook(excel_path, data_only=True, read_only=False)
        except Exception as error:
            raise ValueError(str(error)) from error

        ws = wb.active
        if clib_sheet and str(clib_sheet).strip():
            sheet_name = str(clib_sheet).strip()
            if sheet_name in wb.sheetnames:
                ws = wb[sheet_name]

        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        header = [str(header_cell).strip() if header_cell is not None else "" for header_cell in header_row]
        if not header:
            raise ValueError(f"[cin] 错误: 工作表 '{ws.title}' 没有表头")

        name_idx = step_idx = None
        for header_index, header_text in enumerate(header):
            h_lower = header_text.lower()
            if "name" in h_lower and name_idx is None and "project" not in h_lower:
                name_idx = header_index
            if "step" in h_lower and step_idx is None:
                step_idx = header_index
        if name_idx is None:
            name_idx = 2 if len(header) >= 2 and "project" in header[1].lower() else 1
        if step_idx is None:
            step_idx = (name_idx + 1) if name_idx is not None else 2

        ordered: list = []
        seen: dict = {}
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            name = row[name_idx] if len(row) > name_idx else None
            step_block = row[step_idx] if len(row) > step_idx else None
            if not name or not step_block:
                continue
            name_str = str(name).strip()
            if not name_str:
                continue
            if name_str not in seen:
                steps = []
                seen[name_str] = steps
                ordered.append((name_str, steps))
            else:
                steps = seen[name_str]
            for raw_line in str(step_block).splitlines():
                step_line_text = str(raw_line).rstrip("\n")
                if step_line_text.strip():
                    steps.append((step_line_text, row_idx))

        return ws.title, ordered

    @staticmethod
    def is_numeric_value(value_text: str) -> bool:
        """判断字符串是否可解析为数值。"""
        try:
            float(value_text)
            return True
        except ValueError:
            return False

    @staticmethod
    def apply_default_param_parsing(args: list[str]) -> list[str]:
        """对步骤参数应用默认字符串加引号策略。"""
        parsed = []
        for arg in args:
            parsed.append(arg if CINRuntimeIOUtility.is_numeric_value(arg) else f'"{arg}"')
        return parsed

    @staticmethod
    def parse_step_line_cin(
        line: str,
        keyword_specs: dict,
        *,
        io_mapping_ctx: Optional[IOMappingContext],
        config_enum_ctx: Optional[ConfigEnumContext],
        logger: Optional[object],
        name: Optional[str] = None,
    ) -> Optional[tuple[list[str], str]]:
        """CIN 模式下一行步骤解析，返回 (code_lines, original_line_full) 或 None。"""
        CINRuntimeIOUtility.last_parse_error_state["type"] = None
        CINRuntimeIOUtility.last_parse_error_state["reason"] = ""
        original = line.strip()
        if not original or original.startswith("//"):
            return None

        try:
            result = StepParser.parse_line(
                original,
                keyword_specs,
                mode="cin",
                io_mapping_ctx=io_mapping_ctx,
                config_enum_ctx=config_enum_ctx,
                sanitize_clib_name=StringUtility.sanitize_clib_name,
                default_param_parser=CINRuntimeIOUtility.apply_default_param_parsing,
            )
            if result is None:
                return None
            return (result.code_lines, result.original_line_full)
        except IOMappingParseError as exc:
            CINRuntimeIOUtility.last_parse_error_state["type"] = "iomapping_conflict" if "CONFLICT" in str(exc) else "iomapping"
            CINRuntimeIOUtility.last_parse_error_state["reason"] = str(exc)
            if logger:
                step_text = original.strip()
                reason = str(exc)
                fail_text = reason if reason.startswith("IO_mapping") else f"IO_mapping 表中{reason}"
                name_part = f"Clib_Name：{name}" if name else "Clib_Name：未知"
                err_mod = ErrorModuleResolver.resolve(fail_text)
                logger.error(f"错误模块【{err_mod}】 {name_part} 用例步骤：{step_text}  原因：{fail_text}")
            return None
        except ConfigEnumParseError as exc:
            CINRuntimeIOUtility.last_parse_error_state["type"] = "config_enum"
            CINRuntimeIOUtility.last_parse_error_state["reason"] = str(exc)
            if logger:
                step_text = original.strip()
                reason = str(exc)
                fail_text = reason if reason.startswith("CONFIG_ENUM") else f"CONFIG_ENUM 表中{reason}"
                name_part = f"Clib_Name：{name}" if name else "Clib_Name：未知"
                err_mod = ErrorModuleResolver.resolve(fail_text)
                logger.error(f"错误模块【{err_mod}】 {name_part} 用例步骤：{step_text}  原因：{fail_text}")
            return None
        except (KeywordMatchError, StepSyntaxError) as exc:
            CINRuntimeIOUtility.last_parse_error_state["type"] = "keyword" if isinstance(exc, KeywordMatchError) else "syntax"
            CINRuntimeIOUtility.last_parse_error_state["reason"] = str(exc)
            if logger and isinstance(exc, StepSyntaxError):
                fail_text = f"步骤语法错误: {exc}"
                name_part = f"Clib_Name：{name}" if name else "Clib_Name：未知"
                err_mod = ErrorModuleResolver.resolve(fail_text)
                logger.error(f"错误模块【{err_mod}】 {name_part} 用例步骤：{original.strip()}  原因：{fail_text}")
            return None
        return None

    @staticmethod
    def render_step_lines(
        raw_line: str,
        keyword_specs: dict,
        *,
        io_mapping_ctx: Optional[IOMappingContext],
        config_enum_ctx: Optional[ConfigEnumContext],
        logger: Optional[object] = None,
        source_id: Optional[str] = None,
        excel_name: Optional[str] = None,
        sheet_name: Optional[str] = None,
        name: Optional[str] = None,
        excel_row_num: Optional[int] = None,
    ) -> Optional[list[str]]:
        """将一行 Step 转为 0..N 行 CIN CAPL 代码（含注释与 [idx/total]）。"""
        original_line = str(raw_line).strip()
        if original_line.startswith("//"):
            return None

        result = CINRuntimeIOUtility.parse_step_line_cin(
            original_line,
            keyword_specs,
            io_mapping_ctx=io_mapping_ctx,
            config_enum_ctx=config_enum_ctx,
            logger=logger,
            name=name,
        )

        if result is None:
            err_type = CINRuntimeIOUtility.last_parse_error_state.get("type")
            err_reason = CINRuntimeIOUtility.last_parse_error_state.get("reason", "")
            if err_type == "iomapping_conflict":
                return None
            error_detail = StepErrorDetailBuilder.build_detail(
                err_type or "unknown",
                err_reason,
                original_line,
                keyword_specs,
            )
            return format_step_error_lines(original_line, error_detail, role_prefix="测试步骤")

        code_lines, original_line_full = result
        if not code_lines:
            return None

        out = []
        for idx, code in enumerate(code_lines, start=1):
            suffix = f" [{idx}/{len(code_lines)}]" if len(code_lines) > 1 else ""
            out.append(code.rstrip() + f" //测试步骤 {original_line_full}" + suffix)
        return out

    @staticmethod
    def generate_content(
        ordered_func_steps: list,
        include_files: Optional[list[str]] = None,
    ) -> tuple[str, list]:
        """将 (export_func_name, steps) 列表拼成 .cin 全文。"""
        lines = []
        error_records: list = []
        lines.append("/*@!Encoding:65001*/")
        lines.append("includes")
        lines.append("{")
        if include_files:
            for inc in include_files:
                lines.append(f'  #include "{inc}"')
        else:
            lines.append("  ")
        lines.append("}")
        lines.append("")
        lines.append("variables")
        lines.append("{")
        lines.append("  ")
        lines.append("}")
        lines.append("")

        for export_func_name, steps in ordered_func_steps:
            lines.append(f"export void {export_func_name}()")
            lines.append("{")
            teststep_content = None
            for step in steps or []:
                lines.append(step)
                if step.strip().startswith("teststep("):
                    teststep_content = step.strip()
                elif step.strip().startswith("teststepfail(") and teststep_content is not None:
                    error_records.append((export_func_name, teststep_content, step.strip()))
                    teststep_content = None
            lines.append("}")
            lines.append("")

        return "\n".join(lines), error_records

    @classmethod
    def reset_runtime_state(cls) -> None:
        """初始化/重置全局上下文状态，避免跨任务串状态。"""
        cls.io_mapping_context = None
        cls.config_enum_context = None

    @staticmethod
    def setup_generator_logger(base_dir: str) -> GeneratorLogger:
        """初始化 CIN 主日志管理器（generate_cin_from_excel.log），含 CASEID 过滤。"""
        return GeneratorLogger(
            base_dir,
            log_basename="generate_cin_from_excel.log",
            logger_name="generate_cin_from_excel",
            formatter_factory=CINRuntimeIOUtility.create_progress_formatter,
            file_filters=[SubstringFilter(CASEID_LOG_PATTERNS, include=False)],
        )

    @classmethod
    def load_mapping_context(
        cls,
        cfg: configparser.ConfigParser,
        base_dir: str,
        config_path: str,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
    ) -> Tuple[Optional[IOMappingContext], Optional[ConfigEnumContext]]:
        """按 domain 加载 io_mapping 与 Configuration 枚举上下文。"""
        cls.io_mapping_context, cls.config_enum_context = CINEntrypointSupport.load_mapping_context(
            cfg, base_dir=base_dir, config_path=config_path, domain=domain
        )
        return cls.io_mapping_context, cls.config_enum_context

    @staticmethod
    def read_clib_steps_entry(excel_path: str, clib_sheet: Optional[str] = None) -> tuple:
        """统一入口：从 Clib Excel 读取 Name/Step。"""
        return CINRuntimeIOUtility.read_clib_steps(excel_path, clib_sheet=clib_sheet)

