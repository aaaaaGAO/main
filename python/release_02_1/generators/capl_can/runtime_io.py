#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN 生成运行期 IO 与文件名工具。

从根目录脚本迁入：写 .can 文件、写 sheet 小日志、文件名 sanitize、未生成原因、关键字加载、Clib 校验器；
以及运行时状态重置、日志初始化、映射/Clib 上下文加载、兼容入口 legacy_read_cases。
供 CANGeneratorService.run_legacy_pipeline 与根目录编排脚本调用。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any, Callable, Optional, Tuple

from core.common.generation_summary import build_ungenerated_reason as _build_common_ungenerated_reason
from core.error_module import ErrorModuleResolver
from core.generator_config import GeneratorConfig
from core.generator_logging import GeneratorLogger
from core.mapping_context import MappingContext
from core.translator import load_keyword_specs_from_excel
from services.config_constants import DEFAULT_DOMAIN_LR_REAR, SECTION_CENTRAL

from .excel_repo import CANExcelRepository
from .runtime import CANEntrypointSupport
from .translator import CANStepTranslator

try:
    from pypinyin import lazy_pinyin  # type: ignore
    _HAS_PYPINYIN = True
except Exception:
    lazy_pinyin = None
    _HAS_PYPINYIN = False


def write_can_text(path: str, content: str) -> None:
    """将 CAPL 文本写入 .can 文件（编码 gb18030/cp936）。"""
    text = content.replace("\r\n", "\n").replace("\n", "\r\n")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "wb") as f:
            f.write(text.encode("gb18030", errors="replace"))
    except Exception:
        with open(path, "wb") as f:
            f.write(text.encode("cp936", errors="replace"))


def contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def to_pinyin_if_needed(text: str) -> str:
    text_value = str(text or "").strip()
    if not text_value or not contains_chinese(text_value):
        return text_value
    if not _HAS_PYPINYIN or lazy_pinyin is None:
        return text_value
    try:
        return "".join(lazy_pinyin(text_value, errors=lambda x: list(x)))
    except Exception:
        return text_value


def sanitize_filename_part(text: str) -> str:
    """把 Excel 文件名或 Sheet 名转成可做 .can/.log 文件名的安全片段。"""
    safe_text = to_pinyin_if_needed(str(text or "").strip())
    safe_text = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", safe_text)
    safe_text = re.sub(r"_+", "_", safe_text).strip("_")
    return safe_text or "unknown"


def build_ungenerated_reason(stats: dict) -> str:
    """根据统计构建「未生成 .can」的原因说明。"""
    return _build_common_ungenerated_reason(stats, generated_label=".can")


def load_keyword_specs(excel_path: str, sheet_names: list[str]) -> dict:
    """读取关键字-CAPL 映射表，返回 keyword_specs 字典。"""
    return load_keyword_specs_from_excel(
        excel_path,
        sheet_names,
        warn=lambda msg: None,
    )


def _validate_clib_name(clib_names_set: set[str], clib_name: str) -> bool:
    return bool(clib_name) and clib_name.strip().lower() in clib_names_set


def create_clib_validator(clib_names_set: Optional[set[str]]) -> Optional[Callable[[str], bool]]:
    """根据 Clib 名称集合生成校验函数；集合为空则返回 None。"""
    if not clib_names_set:
        return None
    return partial(_validate_clib_name, clib_names_set)


def _sheet_log_ts() -> str:
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S") + f",{now.microsecond // 1000:03d}"


def write_sheet_can_log(
    log_path: str,
    *,
    excel_name: str,
    sheet_name: str,
    cases: Any,
    can_filename: str,
    global_log_path: Optional[str] = None,
) -> None:
    """
    为单个 Sheet 写一份独立 CAN 生成日志。
    若提供 global_log_path 则优先从主日志截取片段；否则按 cases 内错误拼简化日志。
    """
    lines: list[str] = []

    if global_log_path and os.path.isfile(global_log_path):
        try:
            with open(global_log_path, "r", encoding="utf-8", errors="ignore") as src:
                all_lines = src.readlines()
            end_marker = f"生成文件: {can_filename}"
            end_idx = -1
            for i in range(len(all_lines) - 1, -1, -1):
                if end_marker in all_lines[i]:
                    end_idx = i
                    break
            if end_idx != -1:
                start_idx = -1
                sheet_marker = f"处理Sheet={sheet_name}"
                for j in range(end_idx, -1, -1):
                    if sheet_marker in all_lines[j]:
                        start_idx = j
                        break
                if start_idx == -1:
                    start_marker = f"处理Excel={excel_name}"
                    for j in range(end_idx, -1, -1):
                        if start_marker in all_lines[j]:
                            start_idx = j
                            break
                if start_idx != -1:
                    raw_lines = [ln.rstrip("\r\n") for ln in all_lines[start_idx : end_idx + 1]]
                    _re_parse_excel = re.compile(r"解析 Excel 文件:")
                    lines = [ln for ln in raw_lines if not _re_parse_excel.search(ln)]
        except Exception:
            pass

    if not lines:
        ts = _sheet_log_ts()
        lines.append(f"{ts}  处理Excel={excel_name}")
        fallback_errors: list[tuple[int, str]] = []
        for case in cases:
            for err in getattr(case, "error_records", []) or []:
                err_mod = ErrorModuleResolver.resolve(err.message)
                row = err.excel_row if err.excel_row is not None else getattr(case, "excel_row", 0)
                line = f"{ts} ERROR 错误模块【{err_mod}】 用例ID={case.case_id} 行号：{err.excel_row}  用例步骤：{err.raw_step}  原因：{err.message}"
                fallback_errors.append((row, line))
        fallback_errors.sort(key=lambda x: x[0])
        for _row, line in fallback_errors:
            lines.append(line)
        ts_end = _sheet_log_ts()
        lines.append(f"{ts_end}  生成文件: {can_filename} (用例数={len(cases)})")

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")


# ==================== 运行时上下文（通过 set/get 注入，避免散落模块级变量） ====================


@dataclass
class CANRuntimeContext:
    """CAN 生成运行期上下文，由编排层构造并注入，供 legacy_read_cases 等使用。"""

    io_mapping_ctx: Any
    config_enum_ctx: Any
    clib_names_set: Optional[set[str]] = None


_current_runtime_ctx: Optional[CANRuntimeContext] = None


def set_can_runtime_context(ctx: Optional[CANRuntimeContext]) -> None:
    """注入当前任务的 CAN 运行上下文，由 execute_workflow 在流水线开始时调用。
    参数：ctx — 上下文实例，None 表示清除。
    返回：无返回值。
    """
    global _current_runtime_ctx
    _current_runtime_ctx = ctx


def get_can_runtime_context() -> Optional[CANRuntimeContext]:
    """获取当前已注入的 CAN 运行上下文，供 legacy_read_cases 等读取。
    参数：无。
    返回：当前上下文或 None。
    """
    return _current_runtime_ctx


def reset_runtime_state() -> None:
    """初始化/重置运行时上下文状态，避免跨任务串状态。"""
    set_can_runtime_context(None)


def setup_generator_logger(base_dir: str) -> GeneratorLogger:
    """步骤 ①：初始化日志管理器，返回 GeneratorLogger，由调用方执行 .setup() 与 .clear()。"""
    return GeneratorLogger(
        base_dir,
        "generate_can_from_excel.log",
        logger_name="can_generator",
    )


def load_mapping_context(
    gconfig: GeneratorConfig,
    base_dir: str,
    *,
    domain: str = DEFAULT_DOMAIN_LR_REAR,
) -> Tuple[Any, Any]:
    """加载 IO 映射与配置枚举上下文并返回，由调用方注入到 CANRuntimeContext 或传入 Service。
    参数: gconfig — 生成器配置；base_dir — 工程根目录；domain — 域。
    返回: (io_mapping_ctx, config_enum_ctx)，CENTRAL 时为 (None, None)。
    """
    if domain == SECTION_CENTRAL:
        return None, None
    mapping_ctx = MappingContext.from_config(
        gconfig.raw_config,
        base_dir=base_dir,
        config_path=gconfig.config_path,
        domain=domain,
    )
    return mapping_ctx.io_mapping, mapping_ctx.config_enum


def load_clib_context(
    gconfig: GeneratorConfig,
    base_dir: str,
    *,
    domain: str = DEFAULT_DOMAIN_LR_REAR,
) -> set:
    """从 CIN Excel 加载 Clib 名称集合并返回，由调用方注入到 CANRuntimeContext 或传入 Service。
    参数: gconfig — 生成器配置；base_dir — 工程根目录；domain — 域。
    返回: Clib 名称集合（小写）。
    """
    cin_excel_path = CANEntrypointSupport.resolve_cin_excel_path(
        gconfig, base_dir, domain=domain
    )
    return (
        CANEntrypointSupport.load_clib_names_from_excel(cin_excel_path)
        if cin_excel_path
        else set()
    )


def legacy_read_cases(
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
    """兼容入口：读 Excel、筛选、步骤翻译，返回用例字典与统计。上下文优先使用传入的 runtime_context，否则使用 set_can_runtime_context 注入的当前上下文。
    参数: excel_path — 用例 Excel；keyword_specs — 关键字规格；allowed_levels/platforms/models — 筛选集合；seen_case_ids — 用例 ID 去重；clib_validator — Clib 校验函数；selected_filter — 表名->Sheet 勾选；runtime_context — 可选，不传则用 get_can_runtime_context()。
    返回: (sheet_cases 字典, stats 统计字典)。
    """
    del seen_case_ids
    ctx = runtime_context or get_can_runtime_context()
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
    validator = clib_validator or create_clib_validator(clib_set)
    translator = CANStepTranslator(
        io_mapping_ctx=io_ctx,
        config_enum_ctx=enum_ctx,
        keyword_specs=keyword_specs or {},
        clib_validator=validator,
    )
    out: dict = {}
    for key, case_list in sheet_cases.items():
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
        out[key] = rows
    return out, stats
