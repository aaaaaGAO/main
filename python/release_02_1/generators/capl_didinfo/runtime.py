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

from core.generator_config import GeneratorConfig
from core.generator_logging import GeneratorLogger, LogSpecConfig
from core.run_context import clear_run_logger as clear_run_logger_impl
from infra.config.input_parser import split_input_lines
from services.config_constants import (
    LABEL_RESETDID_VALUE_CONFIG_TABLE,
    OPTION_DIDINFO_OUTPUT_DIR_CANDIDATES,
    OPTION_DIDINFO_INPUTS_CANDIDATES,
    OPTION_DIDINFO_VARIANTS_CANDIDATES,
    OPTION_OUTPUT_DIR,
    SECTION_DTC,
    SECTION_LR_REAR,
)
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

from .runtime_io import (
    find_header_row_and_cols as runtime_io_find_header_row_and_cols,
    find_variant_cols as runtime_io_find_variant_cols,
    generate_from_sheet as runtime_io_generate_from_sheet,
    pick_sheet_name as runtime_io_pick_sheet_name,
)

# DIDInfo 兼容策略白名单：仅允许在同一节内对这些历史别名键做 coalesce。
# 非白名单路径一律应走 get_required_from_section（缺失即报错）。
_DIDINFO_COALESCE_WHITELIST: set[tuple[str, ...]] = {
    tuple(reversed(OPTION_DIDINFO_OUTPUT_DIR_CANDIDATES)),
    tuple(reversed(OPTION_DIDINFO_VARIANTS_CANDIDATES)),
    tuple(reversed(OPTION_DIDINFO_INPUTS_CANDIDATES)),
}


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


def coalesce_didinfo_whitelisted_options(
    gconfig: GeneratorConfig,
    section_name: str,
    option_names: tuple[str, ...],
    *,
    fallback: str = "",
) -> str:
    """
    DIDInfo 专用同节别名兼容读取：仅允许白名单键集做 coalesce，防止兜底范围失控。
    """
    if option_names not in _DIDINFO_COALESCE_WHITELIST:
        raise RuntimeError(
            f"DIDInfo 配置读取拒绝非白名单 coalesce：[{section_name}] {option_names}"
        )
    return gconfig.coalesce_options_in_section(section_name, option_names, fallback=fallback)


def load_runtime_config(base_dir: str, domain: str | None = None) -> tuple:
    """读取 DIDInfo 配置，返回 (config_path, output_path, variant_names, inputs)。"""
    gconfig = GeneratorConfig(base_dir).load()
    didinfo_inputs_keys_hint = " / ".join(reversed(OPTION_DIDINFO_INPUTS_CANDIDATES))
    config_path_str = RuntimePathResolver.resolve_config_path(base_dir, gconfig.config_path)
    if not config_path_str or not os.path.exists(config_path_str):
        raise RuntimeError(
            f"未找到配置文件: {config_path_str or 'Configuration.ini'}"
        )

    config_path = Path(config_path_str)
    cfg = gconfig.raw_config
    effective_domain = domain or SECTION_LR_REAR
    if effective_domain not in (SECTION_DTC, SECTION_LR_REAR):
        raise ValueError(
            f"ResetDid/DIDInfo 仅支持 domain 为 {SECTION_LR_REAR!r} 或 {SECTION_DTC!r}，当前为 {effective_domain!r}"
        )

    if effective_domain == SECTION_DTC:
        if not cfg.has_section(SECTION_DTC):
            raise RuntimeError(f"配置文件缺少 [{SECTION_DTC}] 节")
        sec = SECTION_DTC
        output_filename = gconfig.get_fixed("didinfo_output_filename") or "DIDInfo.txt"
        output_dir_didinfo = coalesce_didinfo_whitelisted_options(
            gconfig,
            sec,
            tuple(reversed(OPTION_DIDINFO_OUTPUT_DIR_CANDIDATES)),
        ).strip()
        if not output_dir_didinfo:
            output_dir_didinfo = gconfig.get_required_from_section(sec, OPTION_OUTPUT_DIR)
        output_dir_abs = Path(resolve_configured_path(base_dir, output_dir_didinfo))
        config_dir_path = resolve_named_subdir(base_dir, output_dir_didinfo, "Configuration")
        if not config_dir_path:
            raise RuntimeError(
                f"错误：输出路径下不存在 Configuration 目录: {output_dir_abs / 'Configuration'}"
            )
        output_path = Path(config_dir_path) / output_filename
        variant_raw = (
            (gconfig.get_fixed("didinfo_variants") or "").strip()
            or coalesce_didinfo_whitelisted_options(
                gconfig,
                sec,
                tuple(reversed(OPTION_DIDINFO_VARIANTS_CANDIDATES)),
            )
        ).strip()
        variant_names = split_csv_values(
            variant_raw or "ACOSe,MY26,ID4 PA,CMP21A"
        )
        inputs_raw = coalesce_didinfo_whitelisted_options(
            gconfig,
            sec,
            tuple(reversed(OPTION_DIDINFO_INPUTS_CANDIDATES)),
        ).strip()
        if not inputs_raw:
            raise RuntimeError(
                f"未配置 {LABEL_RESETDID_VALUE_CONFIG_TABLE}：请在 [DTC] {didinfo_inputs_keys_hint} 中配置 Excel 路径"
            )
        inputs = list(iter_input_specs(inputs_raw))
        return config_path, output_path, variant_names, inputs

    if not cfg.has_section(SECTION_LR_REAR):
        raise RuntimeError(f"配置文件缺少 [{SECTION_LR_REAR}] 节")

    sec = SECTION_LR_REAR
    output_filename = gconfig.get_fixed("didinfo_output_filename") or "DIDInfo.txt"
    output_dir_didinfo = coalesce_didinfo_whitelisted_options(
        gconfig,
        sec,
        tuple(reversed(OPTION_DIDINFO_OUTPUT_DIR_CANDIDATES)),
    ).strip()
    if not output_dir_didinfo:
        output_dir_didinfo = gconfig.get_required_from_section(sec, OPTION_OUTPUT_DIR)
    if not output_dir_didinfo:
        raise RuntimeError(
            f"未配置 DIDInfo 输出目录：请在 [{SECTION_LR_REAR}] 配置 output_dir 或 output_dir_didinfo"
        )
    output_dir_abs = Path(resolve_configured_path(base_dir, output_dir_didinfo))
    config_dir_path = resolve_named_subdir(base_dir, output_dir_didinfo, "Configuration")
    if not config_dir_path:
        raise RuntimeError(
            f"错误：输出路径下不存在 Configuration 目录: {output_dir_abs / 'Configuration'}"
        )
    output_path = Path(config_dir_path) / output_filename
    variant_raw = (
        (gconfig.get_fixed("didinfo_variants") or "").strip()
        or coalesce_didinfo_whitelisted_options(
            gconfig,
            sec,
            tuple(reversed(OPTION_DIDINFO_VARIANTS_CANDIDATES)),
        )
    ).strip()
    variant_names = split_csv_values(
        variant_raw or "ACOSe,MY26,ID4 PA,CMP21A"
    )
    inputs_raw = coalesce_didinfo_whitelisted_options(
        gconfig,
        sec,
        tuple(reversed(OPTION_DIDINFO_INPUTS_CANDIDATES)),
    ).strip()
    if not inputs_raw:
        raise RuntimeError(
            f"未配置 {LABEL_RESETDID_VALUE_CONFIG_TABLE}：请在 [{SECTION_LR_REAR}] {didinfo_inputs_keys_hint} 中配置 Excel 路径"
        )
    inputs = list(iter_input_specs(inputs_raw))
    return config_path, output_path, variant_names, inputs


def strip_didinfo_tee_msg(msg: str) -> str:
    msg = re.sub(r"^\[(?:didinfo|resetdid)\]\s*(?:ERROR|INFO)\s*", "", msg, flags=re.I)
    msg = re.sub(r"^\[(?:didinfo|resetdid)\]\s*(?:错误|警告)\s*:\s*", "", msg, flags=re.I)
    msg = re.sub(r"^\[(?:错误|警告|error|warn)\]\s*:?\s*", "", msg, flags=re.I)
    return msg.strip()


class ExcelParseFriendlyFormatter(logging.Formatter):
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


def create_excel_parse_friendly_formatter(format_string: str) -> logging.Formatter:
    return ExcelParseFriendlyFormatter(format_string)


log_manager: GeneratorLogger | None = None


def init_runtime(base_dir: str) -> tuple:
    """初始化 DIDInfo 主日志与 Tee，返回 (logger, old_stdout, old_stderr)。"""
    global log_manager
    if log_manager is not None:
        log_manager.clear()
    log_manager = GeneratorLogger(
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
        formatter_factory=create_excel_parse_friendly_formatter,
    )
    logger = log_manager.setup()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    if sys.__stdout__ is not None and sys.__stderr__ is not None:
        sys.stdout = TeeToLogger(
            logger,
            logging.INFO,
            sys.__stdout__,
            error_prefixes=(
                "[resetdid] 错误",
                "[resetdid] ERROR",
                "[didinfo] 错误",
                "[didinfo] ERROR",
                "[错误]",
                "[error]",
            ),
            warning_prefixes=("[resetdid] 警告", "[didinfo] 警告", "[警告]", "[warn]"),
            msg_cleaner=strip_didinfo_tee_msg,
            use_reentry_guard=True,
        )
        sys.stderr = TeeToLogger(
            logger,
            logging.ERROR,
            sys.__stderr__,
            error_prefixes=(
                "[resetdid] 错误",
                "[resetdid] ERROR",
                "[didinfo] 错误",
                "[didinfo] ERROR",
                "[错误]",
                "[error]",
            ),
            warning_prefixes=("[resetdid] 警告", "[didinfo] 警告", "[警告]", "[warn]"),
            msg_cleaner=strip_didinfo_tee_msg,
            use_reentry_guard=True,
        )
    return logger, old_stdout, old_stderr


def clear_run_logger(logger_obj: Any) -> None:
    clear_run_logger_impl(logger_obj)
    global log_manager
    if log_manager is not None:
        log_manager.clear()
        log_manager = None


def get_progress_level() -> int:
    return PROGRESS_LEVEL


def pick_sheet_name(wb: Any, default_sheet: str | None) -> str:
    return runtime_io_pick_sheet_name(wb, default_sheet)


def find_header_row_and_cols(ws: Any) -> tuple:
    return runtime_io_find_header_row_and_cols(ws)


def find_variant_cols(ws: Any, header_row: int, variant_names: list[str]) -> dict[str, int]:
    return runtime_io_find_variant_cols(ws, header_row, variant_names)


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
    return runtime_io_generate_from_sheet(
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


class DIDInfoRuntimeUtility:
    """DIDInfo 运行期统一工具类入口。"""

    resolve_base_dir = staticmethod(resolve_base_dir)
    split_csv_values = staticmethod(split_csv_values)
    iter_input_specs = staticmethod(iter_input_specs)
    get_case_insensitive_path = staticmethod(get_case_insensitive_path)
    load_runtime_config = staticmethod(load_runtime_config)
    strip_didinfo_tee_msg = staticmethod(strip_didinfo_tee_msg)
    create_excel_parse_friendly_formatter = staticmethod(create_excel_parse_friendly_formatter)
    init_runtime = staticmethod(init_runtime)
    clear_run_logger = staticmethod(clear_run_logger)
    get_progress_level = staticmethod(get_progress_level)
    pick_sheet_name = staticmethod(pick_sheet_name)
    find_header_row_and_cols = staticmethod(find_header_row_and_cols)
    find_variant_cols = staticmethod(find_variant_cols)
    generate_from_sheet = staticmethod(generate_from_sheet)
