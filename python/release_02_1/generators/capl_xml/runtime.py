#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML 运行期：解析根目录、加载配置、初始化日志，供 XMLGeneratorService 无 hooks 调用。

实现已迁入本包：配置与日志在本模块，Excel 查找/解析/分组/生成在 runtime_io。
入口在 generators.capl_xml.entrypoint.run_generation。
"""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any, Optional

from core.case_filter import CaseFilter
from core.parse_table_loggers import get_testcases_parse_logger
from core.generator_config import GeneratorConfig
from core.generator_logging import GeneratorLogger
from core.run_context import clear_run_logger as clear_run_logger_impl
from services.config_constants import (
    DEFAULT_DOMAIN_LR_REAR,
    OPTION_INPUT_EXCEL,
    OPTION_OUTPUT_DIR,
    OPTION_SELECTED_SHEETS,
    OPTION_XML_INPUT_EXCEL,
    SECTION_CENTRAL,
    SECTION_DTC,
    SECTION_FILTER,
    SECTION_LR_REAR,
    XML_RUNTIME_KEY_ALLOWED_LEVELS,
    XML_RUNTIME_KEY_ALLOWED_MODELS,
    XML_RUNTIME_KEY_ALLOWED_PLATFORMS,
    XML_RUNTIME_KEY_ALLOWED_TARGET_VERSIONS,
    XML_RUNTIME_KEY_EXCEL_PATH,
    XML_RUNTIME_KEY_OUTPUT_XML_PATH,
    XML_RUNTIME_KEY_SELECTED_FILTER,
)
from utils.logger import PROGRESS_LEVEL
from utils.sheet_filter import parse_selected_sheets

from infra.filesystem.pathing import (
    RuntimePathResolver,
    resolve_output_dir_relative_path,
    resolve_runtime_path,
)
from services.filter_service import parse_shaixuan_config

from . import runtime_io

# 模块级 logger 引用，供 clear_run_logger 与 parse/generate 传参使用
_logger: Optional[logging.Logger] = None
_parse_logger: Optional[logging.Logger] = None
_LOG_MANAGER: Optional[GeneratorLogger] = None


class BlankLineFriendlyFormatter(logging.Formatter):
    """让 logger.info('') 写入真正空行；PROGRESS 只输出时间+消息。"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志并保留空行/进度日志语义。"""
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


class SafeStreamHandler(logging.StreamHandler):
    """控制台编码异常时降级为 gbk replace 输出，避免日志写控制台失败。"""

    def emit(self, record: logging.LogRecord) -> None:
        """安全写控制台日志。"""
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


class TeeToLogger:
    """把 print 输出转到 logger（并保留控制台输出）。"""

    def __init__(self, logger: logging.Logger, level: int, original: Any):
        self.logger = logger
        self.level = level
        self.original = original
        self.buffer_text = ""
        self.is_logging_in_progress = False

    def write(self, text_chunk: str) -> int:
        """写入文本并转发到 logger。"""
        if self.is_logging_in_progress:
            try:
                if self.original:
                    self.original.write(text_chunk)
            except Exception:
                pass
            return len(text_chunk)
        try:
            if self.original:
                self.original.write(text_chunk)
        except Exception:
            pass
        self.buffer_text += text_chunk
        while "\n" in self.buffer_text:
            line, self.buffer_text = self.buffer_text.split("\n", 1)
            msg = line.rstrip("\r")
            if not msg:
                continue
            stripped = msg.lstrip()
            if re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}', msg):
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
                self.is_logging_in_progress = True
                if msg.startswith("[warn]") or msg.startswith("[dup]") or msg.startswith("[error]"):
                    self.logger.warning(msg)
                else:
                    self.logger.log(self.level, msg)
            finally:
                self.is_logging_in_progress = False
        return len(text_chunk)

    def flush(self) -> None:
        """刷新底层输出流。"""
        try:
            if self.original:
                self.original.flush()
        except Exception:
            pass


def create_blank_line_friendly_formatter(format_string: str) -> logging.Formatter:
    """创建空行友好的日志格式化器。"""
    return BlankLineFriendlyFormatter(format_string)


def stream_has_isatty(stream_obj: Any) -> bool:
    """判断流对象是否实现 isatty。"""
    return bool(hasattr(stream_obj, "isatty"))


def stream_supports_tty(stream_obj: Any) -> bool:
    """判断流对象是否为 TTY。"""
    if not stream_obj or not stream_has_isatty(stream_obj):
        return False
    try:
        return bool(stream_obj.isatty())
    except Exception:
        return False


def resolve_base_dir(base_dir: Optional[str]) -> str:
    """解析 XML 生成所用的工程根目录。"""
    return RuntimePathResolver.resolve_base_dir(__file__, base_dir)


def load_runtime_config(
    config_path: Optional[str],
    base_dir: str,
    domain: str = DEFAULT_DOMAIN_LR_REAR,
) -> dict:
    """读取配置并解析输入/输出路径、过滤条件与勾选 sheet。"""
    gconfig = GeneratorConfig(
        base_dir,
        config_path=config_path,
        tolerant_duplicates=True,
    ).load()
    config_path_str = RuntimePathResolver.resolve_config_path(base_dir, gconfig.config_path)
    if not os.path.exists(config_path_str):
        raise FileNotFoundError(f"未找到配置文件: {config_path_str}")

    config = gconfig.raw_config

    if domain not in (SECTION_CENTRAL, SECTION_DTC, SECTION_LR_REAR):
        raise ValueError(
            f"XML 生成仅支持 domain 为 {SECTION_LR_REAR!r}、{SECTION_CENTRAL!r} 或 {SECTION_DTC!r}，当前为 {domain!r}"
        )

    if domain == SECTION_CENTRAL:
        # CENTRAL：优先 xml_input_excel；未配置时回退 input_excel（对应界面“测试用例/测试文件夹导入”）。
        case_excel_file = (
            gconfig.get_from_section(domain, OPTION_XML_INPUT_EXCEL, fallback="")
            or gconfig.get_from_section(domain, "Xml_Input_Excel", fallback="")
            or gconfig.get_from_section(domain, OPTION_INPUT_EXCEL, fallback="")
            or gconfig.get_from_section(domain, "Input_Excel", fallback="")
        ).strip()
        if not case_excel_file:
            raise ValueError(
                "未在 [CENTRAL] 配置 XML 输入路径：请配置 xml_input_excel，或使用 input_excel 作为回退。"
            )
    elif domain == SECTION_DTC:
        # DTC：与 RunValidator / 前端持久化一致，主用例表键名为 input_excel（与 CAN 同源）。
        case_excel_file = gconfig.get_required_from_section(domain, OPTION_INPUT_EXCEL)
    elif domain == SECTION_LR_REAR:
        # LR_REAR：仅 [LR_REAR] 内多键名并列，不读 [FILTER]/[PATHS]。
        case_excel_file = (
            gconfig.get_from_section(domain, OPTION_XML_INPUT_EXCEL, fallback="")
            or gconfig.get_from_section(domain, "Xml_Input_Excel", fallback="")
            or gconfig.get_from_section(domain, OPTION_INPUT_EXCEL, fallback="")
            or gconfig.get_from_section(domain, "Input_Excel", fallback="")
        ).strip()
        if not case_excel_file:
            raise ValueError(
                "未在 [LR_REAR] 配置 XML 输入路径：请配置 xml_input_excel 或 input_excel。"
            )

    output_xml_file = gconfig.get_fixed("xml_output_filename") or "Generated_Testcase.xml"
    if domain in (SECTION_CENTRAL, SECTION_DTC):
        output_dir = gconfig.get_required_from_section(domain, OPTION_OUTPUT_DIR)
    elif domain == SECTION_LR_REAR:
        output_dir = (
            gconfig.get_from_section(domain, "Output_Dir_Xml", fallback="")
            or gconfig.get_from_section(domain, "output_dir_xml", fallback="")
            or gconfig.get_from_section(domain, "Output_Dir", fallback="")
            or gconfig.get_from_section(domain, OPTION_OUTPUT_DIR, fallback="")
        ).strip()
        if not output_dir:
            raise ValueError(
                "未在 [LR_REAR] 配置 XML 输出目录：请配置 output_dir 或 Output_Dir_Xml / output_dir_xml。"
            )
    if not output_dir:
        raise ValueError(
            "未在当前主配置文件的当前域节中找到 Output_Dir / output_dir 或 Output_Dir_Xml / output_dir_xml，"
            "请补充其中任意一个以指定 XML 输出目录。"
        )

    allowed_levels = None
    allowed_platforms = None
    allowed_models = None
    allowed_target_versions = None
    if config.has_section(domain) or (
        domain == DEFAULT_DOMAIN_LR_REAR and (config.has_section(SECTION_FILTER) or config.has_section(SECTION_LR_REAR))
    ):
        case_levels_value = (
            gconfig.get_from_section(domain, "case_levels", fallback="")
            or gconfig.get_from_section(domain, "Case_Levels", fallback="")
        )
        allowed_levels = CaseFilter.parse_levels(case_levels_value)
        if allowed_levels is not None:
            print(f"[xml] 等级过滤已启用: {sorted(allowed_levels)}")
        else:
            print(f"[xml] 等级过滤: 不过滤（ALL 或未配置，原始值={case_levels_value!r}）")

        case_platforms_value = (
            gconfig.get_from_section(domain, "case_platforms", fallback="")
            or gconfig.get_from_section(domain, "Case_Platforms", fallback="")
        )
        allowed_platforms = CaseFilter.parse_platforms_or_models(case_platforms_value)
        if allowed_platforms is not None:
            print(f"[xml] 平台过滤已启用: {sorted(allowed_platforms)}")
        else:
            print(f"[xml] 平台过滤: 不过滤（ALL 或未配置，原始值={case_platforms_value!r}）")

        case_models_value = (
            gconfig.get_from_section(domain, "case_models", fallback="")
            or gconfig.get_from_section(domain, "Case_Models", fallback="")
        )
        allowed_models = CaseFilter.parse_platforms_or_models(case_models_value)
        if allowed_models is not None:
            print(f"[xml] 车型过滤已启用: {sorted(allowed_models)}")
        else:
            print(f"[xml] 车型过滤: 不过滤（未配置，原始值={case_models_value!r}）")

        case_target_versions_value = (
            gconfig.get_from_section(domain, "case_target_versions", fallback="")
            or gconfig.get_from_section(domain, "Case_Target_Versions", fallback="")
            or ""
        )
        try:
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

    selected_sheets_str = gconfig.get_from_section(domain, OPTION_SELECTED_SHEETS, fallback="")
    selected_filter = parse_selected_sheets(selected_sheets_str)

    excel_path = resolve_runtime_path(base_dir, case_excel_file)
    output_dir = resolve_output_dir_relative_path(
        base_dir,
        output_dir,
        ("TESTmode",),
        anchor_level="self",
        required=True,
    )
    output_xml_path = os.path.join(output_dir, output_xml_file)

    return {
        "config": config,
        XML_RUNTIME_KEY_EXCEL_PATH: excel_path,
        XML_RUNTIME_KEY_OUTPUT_XML_PATH: output_xml_path,
        XML_RUNTIME_KEY_ALLOWED_LEVELS: allowed_levels,
        XML_RUNTIME_KEY_ALLOWED_PLATFORMS: allowed_platforms,
        XML_RUNTIME_KEY_ALLOWED_MODELS: allowed_models,
        XML_RUNTIME_KEY_ALLOWED_TARGET_VERSIONS: allowed_target_versions,
        XML_RUNTIME_KEY_SELECTED_FILTER: selected_filter,
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
        formatter_factory=create_blank_line_friendly_formatter,
        console=False,
    )
    logger = _LOG_MANAGER.setup()

    fmt = BlankLineFriendlyFormatter("%(asctime)s %(levelname)s %(message)s")
    ch = SafeStreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    _logger = logger
    try:
        _parse_logger = get_testcases_parse_logger(base_dir)
    except Exception:
        _parse_logger = None

    old_stdout, old_stderr = sys.stdout, sys.stderr
    if sys.__stdout__ is not None and sys.__stderr__ is not None:
        sys.stdout = TeeToLogger(logger, logging.INFO, sys.__stdout__)
        sys.stderr = TeeToLogger(logger, logging.ERROR, sys.__stderr__)
    return logger, old_stdout, old_stderr


def get_quiet_skip() -> bool:
    """无 TTY 时不逐行打印 [跳过]，只打汇总。"""
    return not stream_supports_tty(sys.stdout)


class XMLRuntimeUtility:
    """XML 运行期配置/日志辅助统一工具类入口。"""

    @staticmethod
    def create_blank_line_friendly_formatter(*args: Any, **kwargs: Any) -> Any:
        return create_blank_line_friendly_formatter(*args, **kwargs)

    @staticmethod
    def stream_has_isatty(*args: Any, **kwargs: Any) -> Any:
        return stream_has_isatty(*args, **kwargs)

    @staticmethod
    def stream_supports_tty(*args: Any, **kwargs: Any) -> Any:
        return stream_supports_tty(*args, **kwargs)

    @staticmethod
    def resolve_base_dir(*args: Any, **kwargs: Any) -> Any:
        return resolve_base_dir(*args, **kwargs)

    @staticmethod
    def load_runtime_config(*args: Any, **kwargs: Any) -> Any:
        return load_runtime_config(*args, **kwargs)

    @staticmethod
    def init_runtime_logging(*args: Any, **kwargs: Any) -> Any:
        return init_runtime_logging(*args, **kwargs)

    @staticmethod
    def get_quiet_skip(*args: Any, **kwargs: Any) -> Any:
        return get_quiet_skip(*args, **kwargs)


class XMLRuntimeAPI:
    """XML 运行期对外解析与生成功能入口。"""

    @staticmethod
    def find_excel_files(input_path: str) -> list[str]:
        """查找输入路径下的 Excel 文件列表。"""
        return runtime_io.XMLGenerationUtility.find_excel_files(input_path)

    @staticmethod
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
        workbook_cache=None,
    ) -> tuple:
        """解析单个 Excel 为测试用例与统计结果。"""
        return runtime_io.XMLGenerationUtility.parse_testcases_from_excel(
            excel_path,
            allowed_levels=allowed_levels,
            allowed_platforms=allowed_platforms,
            allowed_models=allowed_models,
            allowed_target_versions=allowed_target_versions,
            seen_case_ids=seen_case_ids,
            excel_label=excel_label,
            allowed_sheet_names=allowed_sheet_names,
            selected_filter=selected_filter,
            workbook_cache=workbook_cache,
            logger=_logger,
            parse_logger=_parse_logger,
            quiet_skip=get_quiet_skip(),
        )

    @staticmethod
    def group_testcases_by_sheet_and_group(sheet_testcases_dict: dict) -> dict:
        """按 sheet 与功能组二次分组测试用例。"""
        return runtime_io.XMLGenerationUtility.group_testcases_by_sheet_and_group(sheet_testcases_dict)

    @staticmethod
    def generate_xml_content(excel_files_dict: dict) -> str:
        """根据分组后的数据生成 XML 文本。"""
        return runtime_io.XMLGenerationUtility.generate_xml_content(excel_files_dict, logger=_logger)


find_excel_files = XMLRuntimeAPI.find_excel_files
parse_testcases_from_excel = XMLRuntimeAPI.parse_testcases_from_excel
group_testcases_by_sheet_and_group = XMLRuntimeAPI.group_testcases_by_sheet_and_group
generate_xml_content = XMLRuntimeAPI.generate_xml_content


def clear_run_logger() -> None:
    """清理 XML 运行日志上下文。"""
    global _logger
    clear_run_logger_impl(_logger)
    _logger = None


def get_progress_level() -> int:
    """获取 XML 进度日志级别。"""
    return PROGRESS_LEVEL
