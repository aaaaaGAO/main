#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN 用例生成上下文构建：
筛选条件 + translator/renderer 的构建（需求第6条，与编排解耦）。

仅从当前业务域节读取过滤项，逻辑与 CANGeneratorService.run_pipeline 的内联流程一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.case_filter import CaseFilter
from core.generator_config import GeneratorConfig
from services.config_constants import (
    FILTER_OPTION_CANDIDATES,
    OPTION_CASE_LEVELS,
    OPTION_CASE_MODELS,
    OPTION_CASE_PLATFORMS,
    OPTION_CASE_TARGET_VERSIONS,
    OPTION_SELECTED_SHEETS,
    SECTION_CENTRAL,
)
from services.filter_service import parse_shaixuan_config
from utils.sheet_filter import parse_selected_sheets

from .renderer import CANFileRenderer
from .runtime import CANEntrypointSupport
from .runtime_io import CANRuntimeIOUtility
from .translator import CANStepTranslator


def can_domain_filter_raw(
    gconfig: GeneratorConfig, domain: str, option_name: str
) -> str | None:
    """仅从当前业务域节读取用例过滤项（同节内标准键与 PascalCase 别名）。"""
    item_keys: tuple[str, ...] = FILTER_OPTION_CANDIDATES.get(option_name, (option_name,))
    for item_key in item_keys:
        raw = gconfig.get_from_section(domain, item_key, fallback="")
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


@dataclass(slots=True)
class GeneratedCasesRunContext:
    """供 process_excel_for_generated_case_cans 循环使用的筛选结果与翻译/渲染器。"""

    allowed_levels: Any
    allowed_platforms: Any
    allowed_models: Any
    allowed_target_versions: Any
    selected_filter: dict[str, set[str]] | None
    translator: CANStepTranslator
    renderer: CANFileRenderer


def build_generated_cases_run_context(
    *,
    gconfig: GeneratorConfig,
    base_dir: str,
    domain: str,
    runtime_paths: dict[str, Any],
    io_mapping_ctx: Any,
    config_enum_ctx: Any,
) -> GeneratedCasesRunContext:
    """
    组装 `run_pipeline` 中「generated_from_cases」流程所需的翻译器、渲染器与筛选项（等级/平台/车型/Target Version、勾选 sheet）。

    参数：
        gconfig — 已 load 的 `GeneratorConfig`；base_dir — 工程根；domain — 配置节/域名；
        runtime_paths — `CANEntrypointSupport.build_runtime_paths` 的返回值；io_mapping_ctx / config_enum_ctx —
        可为 None，由本函数内从 mapping 表加载或沿用传入上下文。

    返回：`GeneratedCasesRunContext` 数据类，供 `process_excel_for_generated_case_cans` 等使用。
    """
    allowed_levels = CaseFilter.parse_levels(
        can_domain_filter_raw(gconfig, domain, OPTION_CASE_LEVELS)
    )
    allowed_platforms = CaseFilter.parse_platforms_or_models(
        can_domain_filter_raw(gconfig, domain, OPTION_CASE_PLATFORMS)
    )
    allowed_models = CaseFilter.parse_platforms_or_models(
        can_domain_filter_raw(gconfig, domain, OPTION_CASE_MODELS)
    )
    case_target_versions_value = (
        can_domain_filter_raw(gconfig, domain, OPTION_CASE_TARGET_VERSIONS) or ""
    )
    try:
        filter_options = parse_shaixuan_config(base_dir)
        all_target_versions = filter_options.get("target_versions") or []
    except Exception:
        all_target_versions = []
    allowed_target_versions = CaseFilter.parse_target_versions(
        case_target_versions_value.strip() or None, all_target_versions
    )

    selected_sheets_str = (
        gconfig.get_from_section(domain, OPTION_SELECTED_SHEETS, fallback="")
        or gconfig.get_from_section(domain, "Selected_Sheets", fallback="")
    ).strip()
    selected_filter = parse_selected_sheets(selected_sheets_str)

    keyword_specs = CANRuntimeIOUtility.load_keyword_specs(
        runtime_paths["mapping_excel_path"], runtime_paths["sheet_names"]
    )
    if not keyword_specs:
        raise ValueError(
            f"未加载到关键字映射，请检查配置：{runtime_paths['mapping_excel_path']}"
        )

    cin_excel_path = CANEntrypointSupport.resolve_cin_excel_path(
        gconfig, base_dir, domain=domain
    )
    clib_names_set = (
        CANEntrypointSupport.load_clib_names_from_excel(cin_excel_path)
        if cin_excel_path
        else set()
    )
    clib_validator = CANRuntimeIOUtility.create_clib_validator(clib_names_set)
    translator = CANStepTranslator(
        io_mapping_ctx=io_mapping_ctx,
        config_enum_ctx=config_enum_ctx,
        keyword_specs=keyword_specs,
        clib_validator=clib_validator,
    )
    renderer = CANFileRenderer(
        include_files=[],
        central_sheet_soa_wrapper_enabled=(domain == SECTION_CENTRAL),
    )

    return GeneratedCasesRunContext(
        allowed_levels=allowed_levels,
        allowed_platforms=allowed_platforms,
        allowed_models=allowed_models,
        allowed_target_versions=allowed_target_versions,
        selected_filter=selected_filter,
        translator=translator,
        renderer=renderer,
    )


class GeneratedCasesContextUtility:
    """CAN 用例上下文构建统一工具类入口。"""

    can_domain_filter_raw = staticmethod(can_domain_filter_raw)
    build_generated_cases_run_context = staticmethod(build_generated_cases_run_context)
