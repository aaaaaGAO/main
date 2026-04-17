#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由用例表生成的 `generated_from_cases_*.can` 与 Master 聚合文件（需求第6条拆分入口）。"""

from __future__ import annotations

import os
from glob import glob
from typing import Any, Iterable

from core.error_module import ErrorModuleResolver

from .excel_repo import CANExcelRepository
from .logging import log_progress_or_info
from .runtime_io import (
    build_ungenerated_reason as io_build_ungenerated_reason,
    sanitize_filename_part,
    write_can_text as io_write_can_text,
    write_sheet_can_log as io_write_sheet_can_log,
)


def translate_sheet_cases_in_place(cases: list[Any], translator: Any) -> None:
    """对单个 sheet 的用例就地翻译步骤（与旧 `run_legacy_pipeline` 内层逻辑一致）。"""
    for case in cases:
        for raw_step in case.raw_steps:
            translate_result = translator.translate(raw_step)
            case.steps.extend(translate_result.code_lines)
            case.error_records.extend(translate_result.errors)


def build_sorted_sheet_events(
    cases: list[Any],
    skip_events: Iterable[dict[str, Any]] | None,
) -> list[tuple[int | None, int, str, dict[str, Any]]]:
    """合并 skip 与 error 事件并按 (行号, 优先级) 排序。"""
    sheet_events: list[tuple[int | None, int, str, dict[str, Any]]] = []
    for skip_event in skip_events or []:
        sheet_events.append((skip_event.get("excel_row"), 0, "skip", skip_event))
    for case in cases:
        for error_record in case.error_records:
            row_for_sort = (
                error_record.excel_row
                if error_record.excel_row is not None
                else getattr(case, "excel_row", 0)
            )
            error_payload = {
                "case_id": case.case_id,
                "excel_row": row_for_sort,
                "raw_step": error_record.raw_step,
                "message": error_record.message,
            }
            sheet_events.append((row_for_sort, 1, "error", error_payload))
    sheet_events.sort(
        key=lambda event: ((event[0] if event[0] is not None else 10**9), event[1])
    )
    return sheet_events


def process_excel_for_generated_case_cans(
    *,
    excel_path: str,
    base_dir: str,
    allowed_levels: Any,
    allowed_platforms: Any,
    allowed_models: Any,
    allowed_target_versions: Any,
    selected_filter: dict[str, set[str]] | None,
    translator: Any,
    renderer: Any,
    testcases_dir: str,
    can_log_root: str,
    main_log_path: str,
    logger: Any,
    generated_can_files: list[str],
    excel_can_map: dict[str, list[str]],
    excel_stats_map: dict[str, dict],
) -> None:
    """处理单个输入 Excel：加载 sheet、翻译、写 per-sheet .can 与 sheet 日志，并累积到传入列表/映射。"""
    excel_name = os.path.basename(excel_path)
    log_progress_or_info(logger, f"解析 Excel 文件: {excel_name}")
    log_progress_or_info(logger, f"处理Excel={excel_name}")

    repository = CANExcelRepository(
        base_dir=base_dir,
        allowed_levels=allowed_levels,
        allowed_platforms=allowed_platforms,
        allowed_models=allowed_models,
        allowed_target_versions=allowed_target_versions,
        selected_filter=selected_filter,
    )
    sheet_cases_map, repository_stats = repository.load_cases(excel_path)
    excel_stats_map[excel_path] = repository_stats
    if not sheet_cases_map:
        reason = io_build_ungenerated_reason(repository_stats)
        logger.info(f"  警告: 文件 '{excel_name}' 中未找到任何测试用例（{reason}）")
        return

    skip_events_map = getattr(repository, "skip_events_map", {})

    for (excel_file_path, sheet_name), cases in sheet_cases_map.items():
        translate_sheet_cases_in_place(cases, translator)
        sheet_events = build_sorted_sheet_events(
            cases,
            skip_events_map.get((excel_file_path, sheet_name), []),
        )
        log_progress_or_info(logger, f"  处理Sheet={sheet_name}")
        log_sheet_events(logger, sheet_events)

        excel_name_inner = os.path.basename(excel_file_path)
        excel_basename = os.path.splitext(excel_name_inner)[0]
        can_filename = per_sheet_can_filename(excel_basename, sheet_name)
        log_progress_or_info(logger, f"生成文件: {can_filename} (用例数={len(cases)})")
        for handler in logger.handlers:
            try:
                handler.flush()
            except Exception:
                pass

        sheet_log_name = per_sheet_log_basename(excel_basename, sheet_name)
        sheet_log_path = os.path.join(can_log_root, sheet_log_name)
        try:
            io_write_sheet_can_log(
                sheet_log_path,
                excel_name=excel_name_inner,
                sheet_name=sheet_name,
                cases=cases,
                can_filename=can_filename,
                global_log_path=main_log_path,
            )
        except Exception:
            pass

        if cases:
            can_filepath = os.path.join(testcases_dir, can_filename)
            can_content = renderer.render_sheet_file(cases)
            io_write_can_text(can_filepath, can_content)
            generated_can_files.append(can_filename)
            excel_can_map.setdefault(excel_file_path, []).append(can_filename)


def log_sheet_events(logger: Any, sheet_events: list[tuple[int | None, int, str, dict[str, Any]]]) -> None:
    """将单 sheet 的 skip/error 事件写入 logger。"""
    for excel_row, _prio, event_kind, event_payload in sheet_events:
        if event_kind == "skip":
            logger.info(
                f"[跳过] 用例ID={event_payload['case_id']}, 功能模块={event_payload['group']}, 用例类型='{event_payload['case_type']}'（{event_payload['reason']}）"
            )
        elif event_kind == "error":
            error_module = ErrorModuleResolver.resolve(event_payload["message"])
            logger.error(
                f"错误模块【{error_module}】 用例ID={event_payload['case_id']} 行号：{excel_row}  用例步骤：{event_payload['raw_step']}  原因：{event_payload['message']}"
            )


def log_no_can_generated_summary(
    logger: Any,
    *,
    selected_filter: dict[str, set[str]] | None,
    excel_files: list[str],
    excel_stats_map: dict[str, dict],
) -> None:
    """未生成任何 .can 时的提示与按 Excel 汇总原因。"""
    logger.info("没有生成任何.can文件")
    if selected_filter:
        expected = ", ".join(sorted(selected_filter.keys()))
        logger.info(
            " 提示: 已配置 selected_sheets 时，只有这些文件名会被处理。请确认它们在 input_excel 目录下存在: %s",
            expected,
        )
    log_progress_or_info(logger, "未生成 .can 的 Excel 汇总")
    for excel_file_path in excel_files:
        excel_name_only = os.path.basename(excel_file_path)
        excel_stats = excel_stats_map.get(excel_file_path, {})
        reason = io_build_ungenerated_reason(excel_stats)
        log_progress_or_info(logger, f"  Excel={excel_name_only} → 未生成 .can，原因：{reason}")


def log_excel_generation_summaries(
    logger: Any,
    *,
    excel_files: list[str],
    excel_can_map: dict[str, list[str]],
    excel_stats_map: dict[str, dict],
) -> None:
    """目录模式与单文件模式下的生成结果汇总日志。"""
    if len(excel_files) > 1:
        log_progress_or_info(logger, "目录模式 CAN 生成汇总开始")
        for excel_file_path in excel_files:
            excel_name_only = os.path.basename(excel_file_path)
            can_list = excel_can_map.get(excel_file_path, [])
            if can_list:
                log_progress_or_info(
                    logger,
                    f"  Excel={excel_name_only} → 生成 {len(can_list)} 个 .can：{', '.join(can_list)}",
                )
        ungenerated = [p for p in excel_files if not excel_can_map.get(p)]
        if ungenerated:
            log_progress_or_info(logger, "未生成 .can 的 Excel 汇总")
            for excel_file_path in ungenerated:
                excel_name_only = os.path.basename(excel_file_path)
                excel_stats = excel_stats_map.get(excel_file_path, {})
                reason = io_build_ungenerated_reason(excel_stats)
                log_progress_or_info(
                    logger, f"  Excel={excel_name_only} → 未生成 .can，原因：{reason}"
                )
        log_progress_or_info(logger, "目录模式 CAN 生成汇总结束")
    elif len(excel_files) == 1:
        excel_file_path = excel_files[0]
        excel_name_only = os.path.basename(excel_file_path)
        can_list = excel_can_map.get(excel_file_path, [])
        if can_list:
            log_progress_or_info(
                logger,
                f"  Excel={excel_name_only} → 生成 {len(can_list)} 个 .can：{', '.join(can_list)}",
            )
        else:
            excel_stats = excel_stats_map.get(excel_file_path, {})
            reason = io_build_ungenerated_reason(excel_stats)
            log_progress_or_info(
                logger, f"  Excel={excel_name_only} → 未生成 .can，原因：{reason}"
            )


def per_sheet_can_filename(excel_basename: str, sheet_name: str) -> str:
    return (
        f"generated_from_cases_{sanitize_filename_part(excel_basename)}_"
        f"{sanitize_filename_part(sheet_name)}.can"
    )


def per_sheet_log_basename(excel_basename: str, sheet_name: str) -> str:
    return f"{sanitize_filename_part(excel_basename)}_{sanitize_filename_part(sheet_name)}.log"


def build_master_can_lines(
    *,
    generated_can_files: Iterable[str],
    secoc_qualifier: str,
    has_keyword_clib: bool,
    cin_output_filename: str | None,
) -> list[str]:
    lines = [
        "/*@!Encoding:936*/",
        "/*@!Encoding:936*/",
        "includes",
        "{",
        '  #include "..\\..\\..\\Public\\TESTmode\\TestMoudleControl\\TestMoudleControl_Swc.can"',
    ]
    secoc = (secoc_qualifier or "").strip()
    if secoc:
        lines.append(f'  #include "..\\..\\..\\Public\\ILNode\\SecOc\\CAN\\{secoc}.cin"')
    if has_keyword_clib and cin_output_filename:
        lines.append(f'  #include "{cin_output_filename}"')
    for can_filename in sorted(generated_can_files):
        lines.append(f'  #include "Testcases\\{can_filename}"')
    lines.append("}")
    return lines


def remove_stale_master_can_siblings(master_output_path: str) -> None:
    """删除与 master 同目录下其它 .can，避免历史 master 残留（保留当前文件名大小写匹配）。"""
    master_dir = os.path.dirname(master_output_path)
    current_master_name = os.path.basename(master_output_path)
    for stale_path in glob(os.path.join(master_dir, "*.can")):
        if os.path.basename(stale_path).lower() == current_master_name.lower():
            continue
        try:
            os.remove(stale_path)
        except OSError:
            pass


def write_master_can_aggregate_file(
    *,
    master_output_path: str,
    generated_can_files: Iterable[str],
    secoc_qualifier: str,
    has_keyword_clib: bool,
    cin_output_filename: str | None,
) -> None:
    """写入 Master `.can`（含 includes 聚合）；与原先 `run_legacy_pipeline` 尾部逻辑一致。"""
    master_lines = build_master_can_lines(
        generated_can_files=generated_can_files,
        secoc_qualifier=secoc_qualifier,
        has_keyword_clib=has_keyword_clib,
        cin_output_filename=cin_output_filename,
    )
    # 最安全模式：不自动删除同目录任何历史文件，仅覆盖当前 master。
    io_write_can_text(master_output_path, "\n".join(master_lines))
