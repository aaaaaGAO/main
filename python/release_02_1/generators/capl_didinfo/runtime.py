#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDInfo 运行期：解析根目录、加载配置、初始化日志，供 DIDInfoGeneratorService 无 hooks 调用。

表头/Sheet 解析与生成逻辑在 runtime_io 中；本模块负责 resolve_base_dir、load_runtime_config、
init_runtime、clear_run_logger、get_progress_level，以及对外暴露 pick_sheet_name、find_header_row_and_cols、
find_variant_cols、generate_from_sheet（委托 runtime_io）。
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from core.common.input_parser import split_input_lines
from core.generator_config import GeneratorConfig
from core.generator_logging import GeneratorLogger, LogSpecConfig
from core.run_context import clear_run_logger as _clear_run_logger_impl
from services.config_constants import (
    OPTION_DIDINFO_INPUTS_CANDIDATES,
    OPTION_OUTPUT_DIR_CANDIDATES,
    PATHS_DIDINFO_INPUT_OPTION_CANDIDATES,
    PATHS_DIDINFO_OUTPUT_DIR_OPTION_CANDIDATES,
    SECTION_LR_REAR,
    SECTION_PATHS,
)
from utils.excel_io import norm_str
from utils.logger import (
    PROGRESS_LEVEL,
    ExcludeSubstringsFilter,
    TeeToLogger,
)
from infra.filesystem.pathing import (
    RuntimePathResolver,
    resolve_configured_path,
    resolve_named_subdir,
)

from . import runtime_io as _io


def resolve_base_dir() -> str:
    """解析 DIDInfo 运行根目录（项目根）。"""
    return RuntimePathResolver.resolve_base_dir(__file__)


def split_csv_values(csv_text: str) -> list[str]:
    return [item.strip() for item in (csv_text or "").split(",") if item.strip()]


def iter_input_specs(raw: str) -> Iterable[tuple[str, list[str] | None]]:
    for path_text, sheet_text in split_input_lines(raw):
        if not sheet_text:
            yield (path_text, None)
        elif sheet_text.strip() == "*":
            yield (path_text, ["*"])
        else:
            yield (path_text, split_csv_values(sheet_text))


def get_case_insensitive_path(parent: Any, target_name: str) -> Path | None:
    """在目录下按大小写不敏感方式查找子目录。"""
    parent_path = Path(parent)
    if not parent_path.is_dir():
        return None
    for entry in parent_path.iterdir():
        if entry.is_dir() and entry.name.lower() == target_name.lower():
            return entry
    return None


def load_runtime_config(base_dir: str) -> tuple:
    """读取 DIDInfo 配置，返回 (config_path, output_path, variant_names, inputs)。"""
    gconfig = GeneratorConfig(base_dir).load()
    config_path_str = RuntimePathResolver.resolve_config_path(base_dir, gconfig.config_path)
    if not config_path_str or not os.path.exists(config_path_str):
        raise RuntimeError(
            f"未找到配置文件: {config_path_str or 'Configuration.ini'}"
        )

    config_path = Path(config_path_str)
    cfg = gconfig.raw_config

    if SECTION_LR_REAR in cfg or SECTION_PATHS in cfg:
        output_filename = gconfig.get_fixed("didinfo_output_filename") or "DIDInfo.txt"
        output_dir_didinfo = gconfig.get_first(
            [
                (SECTION_LR_REAR, "output_dir_didinfo"),
                (SECTION_LR_REAR, "Output_Dir_Didinfo"),
            ]
            + [(SECTION_LR_REAR, option_name) for option_name in OPTION_OUTPUT_DIR_CANDIDATES]
            + [(SECTION_PATHS, option_name) for option_name in PATHS_DIDINFO_OUTPUT_DIR_OPTION_CANDIDATES]
        )
        if not output_dir_didinfo:
            output_dir_didinfo = gconfig.get_first(
                [(SECTION_PATHS, option_name) for option_name in OPTION_OUTPUT_DIR_CANDIDATES],
                fallback="./output",
            )
        output_dir_abs = Path(resolve_configured_path(base_dir, output_dir_didinfo))
        config_dir_path = resolve_named_subdir(base_dir, output_dir_didinfo, "Configuration")
        if not config_dir_path:
            raise RuntimeError(
                f"错误：输出路径下不存在 Configuration 目录: {output_dir_abs / 'Configuration'}"
            )
        output_path = Path(config_dir_path) / output_filename
        variant_names = split_csv_values(
            gconfig.get_fixed("didinfo_variants")
            or gconfig.get_first(
                [(SECTION_PATHS, "didinfo_variants"), (SECTION_PATHS, "Didinfo_Variants")],
                fallback="ACOSe,MY26,ID4 PA,CMP21A",
            )
        )
        inputs_raw = gconfig.get_first(
            [(SECTION_LR_REAR, option_name) for option_name in OPTION_DIDINFO_INPUTS_CANDIDATES]
            + [(SECTION_PATHS, option_name) for option_name in PATHS_DIDINFO_INPUT_OPTION_CANDIDATES[:2]]
        )
        if not inputs_raw:
            didinfo_input_excel = gconfig.get_first(
                [(SECTION_PATHS, option_name) for option_name in PATHS_DIDINFO_INPUT_OPTION_CANDIDATES[2:]]
            )
            if didinfo_input_excel:
                inputs_raw = f"{didinfo_input_excel} | *"
        # 将 didinfo_inputs / didinfo_input_excel 解析为输入列表；若最终没有任何有效输入，则视为“未配置 ResetDid_Value 配置表”
        inputs = list(iter_input_specs(inputs_raw))
        if not inputs:
            raise RuntimeError(
                f"未配置 ResetDid_Value 配置表：请在 [{SECTION_LR_REAR}].didinfo_inputs 或 [{SECTION_PATHS}].didinfo_input_excel 中配置 Excel 路径"
            )
    elif "DIDINFO" in cfg:
        config_base = config_path.parent
        output_file = cfg["DIDINFO"].get("Output_File", "").strip()
        output_path = (
            Path(output_file)
            if os.path.isabs(output_file)
            else (config_base / Path(output_file)).resolve()
        )
        variant_names = split_csv_values(cfg["DIDINFO"].get("Variants", ""))
        inputs = list(iter_input_specs(cfg["DIDINFO"].get("Inputs", "")))
    else:
        raise RuntimeError(f"配置文件缺少 [{SECTION_PATHS}] 或 [DIDINFO] 段")

    return config_path, output_path, variant_names, inputs


def strip_didinfo_tee_msg(msg: str) -> str:
    msg = re.sub(r"^\[didinfo\]\s*(?:ERROR|INFO)\s*", "", msg, flags=re.I)
    msg = re.sub(r"^\[didinfo\]\s*(?:错误|警告)\s*:\s*", "", msg)
    msg = re.sub(r"^\[(?:错误|警告|error|warn)\]\s*:?\s*", "", msg, flags=re.I)
    return msg.strip()


class _ExcelParseFriendlyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.levelno == PROGRESS_LEVEL:
            old_name = record.levelname
            record.levelname = " "
            formatted = super().format(record)
            record.levelname = old_name
            return formatted.replace("  ", " ", 1) if "  " in formatted else formatted
        formatted = super().format(record)
        if msg.startswith("解析 Excel 文件:"):
            token = f" {record.levelname} "
            if token in formatted:
                formatted = formatted.replace(token, " ", 1)
        return formatted


_log_mgr: GeneratorLogger | None = None


def init_runtime(base_dir: str) -> tuple:
    """初始化 DIDInfo 主日志与 Tee，返回 (logger, old_stdout, old_stderr)。"""
    global _log_mgr
    if _log_mgr is not None:
        _log_mgr.clear()
    _log_mgr = GeneratorLogger(
        base_dir,
        logger_name="generate_didinfo_from_excel",
        log_specs=[
            LogSpecConfig(
                subdir="parse",
                basename="ResetDID_Matrix.log",
                file_filters=[ExcludeSubstringsFilter("已生成:")],
                progress_filters=[ExcludeSubstringsFilter("已生成:")],
            ),
            LogSpecConfig(subdir="gen", basename="generate_didinfo_from_excel.log"),
        ],
        formatter_factory=lambda s: _ExcelParseFriendlyFormatter(s),
    )
    logger = _log_mgr.setup()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    if sys.__stdout__ is not None and sys.__stderr__ is not None:
        sys.stdout = TeeToLogger(
            logger,
            logging.INFO,
            sys.__stdout__,
            error_prefixes=("[didinfo] 错误", "[didinfo] ERROR", "[错误]", "[error]"),
            warning_prefixes=("[didinfo] 警告", "[警告]", "[warn]"),
            msg_cleaner=strip_didinfo_tee_msg,
            use_reentry_guard=True,
        )
        sys.stderr = TeeToLogger(
            logger,
            logging.ERROR,
            sys.__stderr__,
            error_prefixes=("[didinfo] 错误", "[didinfo] ERROR", "[错误]", "[error]"),
            warning_prefixes=("[didinfo] 警告", "[警告]", "[warn]"),
            msg_cleaner=strip_didinfo_tee_msg,
            use_reentry_guard=True,
        )
    return logger, old_stdout, old_stderr


def clear_run_logger(logger_obj: Any) -> None:
    _clear_run_logger_impl(logger_obj)
    global _log_mgr
    if _log_mgr is not None:
        _log_mgr.clear()
        _log_mgr = None


def get_progress_level() -> int:
    return PROGRESS_LEVEL


def pick_sheet_name(wb: Any, default_sheet: str | None) -> str:
    return _io.pick_sheet_name(wb, default_sheet)


def find_header_row_and_cols(ws: Any) -> tuple:
    return _io.find_header_row_and_cols(ws)


def find_variant_cols(ws: Any, header_row: int, variant_names: list[str]) -> dict[str, int]:
    return _io.find_variant_cols(ws, header_row, variant_names)


def generate_from_sheet(
    ws: Any,
    *,
    excel_name: str,
    variant_name: str,
    variant_col: int,
    sheet_name: str,
    last_sheet_name: str | None = None,
    last_variant_name: str | None = None,
    last_did: str | None = None,
    last_len: int | None = None,
) -> tuple:
    return _io.generate_from_sheet(
        ws,
        excel_name=excel_name,
        variant_name=variant_name,
        variant_col=variant_col,
        sheet_name=sheet_name,
        last_sheet_name=last_sheet_name,
        last_variant_name=last_variant_name,
        last_did=last_did,
        last_len=last_len,
    )
