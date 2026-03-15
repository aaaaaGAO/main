#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML 运行期：解析根目录、加载配置、初始化日志，供 XMLGeneratorService 无 hooks 调用。

实现已迁入本包：配置与日志在本模块，Excel 查找/解析/分组/生成在 runtime_io。
入口在 generators.capl_xml.entrypoint.main。
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

from core.case_filter import CaseFilter
from core.generator_config import GeneratorConfig
from core.generator_logging import GeneratorLogger
from core.run_context import clear_run_logger as _clear_run_logger_impl
from utils.logger import PROGRESS_LEVEL
from utils.path_utils import resolve_target_subdir_smart
from utils.sheet_filter import parse_selected_sheets

from . import runtime_io as _io

# 模块级 logger 引用，供 clear_run_logger 与 parse/generate 传参使用
_logger: Optional[logging.Logger] = None
_parse_logger: Optional[logging.Logger] = None
_LOG_MANAGER: Optional[GeneratorLogger] = None


class _BlankLineFriendlyFormatter(logging.Formatter):
    """让 logger.info('') 写入真正空行；PROGRESS 只输出时间+消息。"""

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if msg == "":
            return ""
        if record.levelno == PROGRESS_LEVEL:
            old_name = record.levelname
            record.levelname = " "
            formatted = super().format(record)
            record.levelname = old_name
            return formatted.replace("  ", " ", 1) if "  " in formatted else formatted
        formatted = super().format(record)
        if msg.startswith("解析 Excel 文件:"):
            token = f" {record.levelname} "
            idx = formatted.find(token)
            if idx != -1:
                formatted = formatted.replace(token, " ", 1)
        return formatted


class _TeeToLogger:
    """把 print 输出转到 logger（并保留控制台输出）。"""

    def __init__(self, logger: logging.Logger, level: int, original: Any):
        self.logger = logger
        self.level = level
        self.original = original
        self._buf = ""
        self._in_progress = False

    def write(self, s: str) -> int:
        if self._in_progress:
            try:
                if self.original:
                    self.original.write(s)
            except Exception:
                pass
            return len(s)
        try:
            if self.original:
                self.original.write(s)
        except Exception:
            pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            msg = line.rstrip("\r")
            if not msg:
                continue
            stripped = msg.lstrip()
            import re as _re
            if _re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}', msg):
                continue
            if (
                stripped.startswith("所有文件生成完成！XML 文件已生成:")
                or stripped.startswith("[主程序] 目录模式 XML 生成汇总：")
                or stripped.startswith("[主程序] 未生成 XML 文件的 Excel 汇总：")
                or stripped.startswith("Excel=")
            ):
                continue
            if stripped.startswith("[正在打开工作簿]") or stripped.startswith("[已打开工作簿]"):
                continue
            if "[cin]" in msg or ".cin 文件已生成" in msg:
                continue
            try:
                self._in_progress = True
                if msg.startswith("[warn]") or msg.startswith("[dup]") or msg.startswith("[error]"):
                    self.logger.warning(msg)
                else:
                    self.logger.log(self.level, msg)
            finally:
                self._in_progress = False
        return len(s)

    def flush(self) -> None:
        try:
            if self.original:
                self.original.flush()
        except Exception:
            pass


def resolve_base_dir(base_dir: Optional[str]) -> str:
    """解析 XML 生成所用的工程根目录，统一使用 infra.filesystem.pathing.get_project_root。"""
    if base_dir is not None:
        return os.path.abspath(base_dir)
    from infra.filesystem.pathing import get_project_root
    return get_project_root(__file__)


def load_runtime_config(
    config_path: Optional[str],
    base_dir: str,
    domain: str = "LR_REAR",
) -> dict:
    """读取配置并解析输入/输出路径、过滤条件与勾选 sheet。"""
    gconfig = GeneratorConfig(
        base_dir,
        config_path=config_path,
        tolerant_duplicates=True,
    ).load()
    config_path_str = gconfig.config_path or os.path.join(base_dir, "config", "Configuration.txt")
    if not os.path.exists(config_path_str):
        raise FileNotFoundError(f"未找到配置文件: {config_path_str}")

    config = gconfig.raw_config

    def domain_candidates(*options: str) -> list:
        pairs = [(domain, option) for option in options]
        if domain == "LR_REAR":
            pairs.extend([("FILTER", option) for option in options])
            pairs.extend([("PATHS", option) for option in options])
            pairs.extend([("LR_REAR", option) for option in options])
        return pairs

    case_excel_file = gconfig.get_first(
        domain_candidates(
            "xml_input_excel",
            "Xml_Input_Excel",
            "input_excel",
            "Input_Excel",
            "input_excel_dir",
            "Input_Excel_Dir",
        )
    )
    if not case_excel_file:
        raise ValueError(
            "未配置 Xml_Input_Excel 或 xml_input_excel。\n"
            "请在 Configuration.txt 的当前域节中配置以下选项之一：\n"
            "  - Xml_Input_Excel 或 xml_input_excel：Excel 文件或文件夹路径"
        )

    output_xml_file = gconfig.get_fixed("xml_output_filename") or "Generated_Testcase.xml"
    output_dir = gconfig.get_first(
        domain_candidates(
            "Output_Dir_Xml",
            "output_dir_xml",
            "Output_Dir",
            "output_dir",
        )
    )
    if not output_dir:
        raise ValueError(
            "未在 Configuration.txt 的当前域节中找到 Output_Dir / output_dir 或 Output_Dir_Xml / output_dir_xml，"
            "请补充其中任意一个以指定 XML 输出目录。"
        )

    allowed_levels = None
    allowed_platforms = None
    allowed_models = None
    allowed_target_versions = None
    if config.has_section(domain) or (
        domain == "LR_REAR" and (config.has_section("FILTER") or config.has_section("LR_REAR"))
    ):
        case_levels_value = gconfig.get_first(domain_candidates("Case_Levels", "case_levels"))
        allowed_levels = CaseFilter.parse_levels(case_levels_value)
        if allowed_levels is not None:
            print(f"[xml] 等级过滤已启用: {sorted(allowed_levels)}")
        else:
            print(f"[xml] 等级过滤: 不过滤（ALL 或未配置，原始值={case_levels_value!r}）")

        case_platforms_value = gconfig.get_first(
            domain_candidates("Case_Platforms", "case_platforms")
        )
        allowed_platforms = CaseFilter.parse_platforms_or_models(case_platforms_value)
        if allowed_platforms is not None:
            print(f"[xml] 平台过滤已启用: {sorted(allowed_platforms)}")
        else:
            print(f"[xml] 平台过滤: 不过滤（ALL 或未配置，原始值={case_platforms_value!r}）")

        case_models_value = gconfig.get_first(domain_candidates("Case_Models", "case_models"))
        allowed_models = CaseFilter.parse_platforms_or_models(case_models_value)
        if allowed_models is not None:
            print(f"[xml] 车型过滤已启用: {sorted(allowed_models)}")
        else:
            print(f"[xml] 车型过滤: 不过滤（未配置，原始值={case_models_value!r}）")

        case_target_versions_value = (
            gconfig.get_first(domain_candidates("Case_Target_Versions", "case_target_versions")) or ""
        )
        try:
            from services.filter_service import parse_shaixuan_config
            fopts = parse_shaixuan_config(base_dir)
            all_target_versions = fopts.get("target_versions") or []
        except Exception:
            all_target_versions = []
        allowed_target_versions = CaseFilter.parse_target_versions(
            (case_target_versions_value or "").strip() or None, all_target_versions
        )
        if allowed_target_versions is not None:
            print(f"[xml] Target Version 过滤已启用: {sorted(allowed_target_versions)[:5]}{'...' if len(allowed_target_versions) > 5 else ''}")
        else:
            print(f"[xml] Target Version 过滤: 不过滤（未配置，原始值={case_target_versions_value!r}）")
    else:
        print("[xml] 等级过滤: 未找到当前域 / [FILTER] / [LR_REAR] 配置，不过滤")
        allowed_target_versions = None

    selected_sheets_str = gconfig.get_first(domain_candidates("selected_sheets"), fallback="")
    selected_filter = parse_selected_sheets(selected_sheets_str)

    if not os.path.isabs(case_excel_file):
        excel_path = os.path.join(base_dir, case_excel_file)
    else:
        excel_path = case_excel_file
    output_dir = resolve_target_subdir_smart(base_dir, output_dir, "TESTmode")
    output_xml_path = os.path.join(output_dir, output_xml_file)

    return {
        "config": config,
        "excel_path": excel_path,
        "output_xml_path": output_xml_path,
        "allowed_levels": allowed_levels,
        "allowed_platforms": allowed_platforms,
        "allowed_models": allowed_models,
        "allowed_target_versions": allowed_target_versions,
        "selected_filter": selected_filter,
    }


def init_runtime_logging(base_dir: str) -> tuple:
    """初始化 XML 主日志、解析表格日志与 Tee。返回 (logger, old_stdout, old_stderr)。"""
    global _logger, _parse_logger, _LOG_MANAGER
    if _LOG_MANAGER is not None:
        _LOG_MANAGER.clear()
    _LOG_MANAGER = GeneratorLogger(
        base_dir,
        log_basename="generate_xml_from_can.log",
        logger_name="generate_xml_from_can",
        formatter_factory=lambda s: _BlankLineFriendlyFormatter(s),
        console=False,
    )
    logger = _LOG_MANAGER.setup()

    class SafeStreamHandler(logging.StreamHandler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                super().emit(record)
            except UnicodeEncodeError:
                try:
                    msg = self.format(record)
                    msg_safe = msg.encode("gbk", errors="replace").decode("gbk", errors="replace")
                    if self.stream:
                        self.stream.write(msg_safe + self.terminator)
                        self.flush()
                except Exception:
                    pass

    fmt = _BlankLineFriendlyFormatter("%(asctime)s %(levelname)s %(message)s")
    ch = SafeStreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    _logger = logger
    try:
        from core.parse_table_loggers import get_testcases_parse_logger
        _parse_logger = get_testcases_parse_logger(base_dir)
    except Exception:
        _parse_logger = None

    old_stdout, old_stderr = sys.stdout, sys.stderr
    if sys.__stdout__ is not None and sys.__stderr__ is not None:
        sys.stdout = _TeeToLogger(logger, logging.INFO, sys.__stdout__)
        sys.stderr = _TeeToLogger(logger, logging.ERROR, sys.__stderr__)
    return logger, old_stdout, old_stderr


def get_quiet_skip() -> bool:
    """无 TTY 时不逐行打印 [跳过]，只打汇总。"""
    return not (sys.stdout and getattr(sys.stdout, "isatty", lambda: False)())


def find_excel_files(input_path: str) -> list[str]:
    return _io.find_excel_files(input_path)


def parse_testcases_from_excel(
    excel_path: str,
    *,
    allowed_levels=None,
    allowed_platforms=None,
    allowed_models=None,
    allowed_target_versions=None,
    seen_case_ids=None,
    excel_label=None,
    allowed_sheet_names=None,
    selected_filter=None,
) -> tuple:
    return _io.parse_testcases_from_excel(
        excel_path,
        allowed_levels=allowed_levels,
        allowed_platforms=allowed_platforms,
        allowed_models=allowed_models,
        allowed_target_versions=allowed_target_versions,
        seen_case_ids=seen_case_ids,
        excel_label=excel_label,
        allowed_sheet_names=allowed_sheet_names,
        selected_filter=selected_filter,
        logger=_logger,
        parse_logger=_parse_logger,
        quiet_skip=get_quiet_skip(),
    )


def group_testcases_by_sheet_and_group(sheet_testcases_dict: dict) -> dict:
    return _io.group_testcases_by_sheet_and_group(sheet_testcases_dict)


def generate_xml_content(excel_files_dict: dict) -> str:
    return _io.generate_xml_content(excel_files_dict, logger=_logger)


def clear_run_logger() -> None:
    global _logger
    _clear_run_logger_impl(_logger)
    _logger = None


def get_progress_level() -> int:
    return PROGRESS_LEVEL
