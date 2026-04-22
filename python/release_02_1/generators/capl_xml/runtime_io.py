#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML 生成：Excel 查找、用例解析、分组与 XML 内容生成。供 capl_xml.service 与 runtime 调用。
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import glob
import logging
from typing import Any, Optional

from core.common.sanitizer import sanitize_case_id
from core.case_filter import CaseFilter
from core.excel_header import (
    find_case_type_column_index_in_values,
    find_col_index_by_name_in_values,
    find_testcase_header_row,
)
from infra.excel.workbook import ExcelService

# 拼音支持（用于 XML testcase name 转拼音）
lazy_pinyin = None
_HAS_PYPINYIN = False
if importlib.util.find_spec("pypinyin") is not None:
    pypinyin_module = importlib.import_module("pypinyin")
    lazy_pinyin = getattr(pypinyin_module, "lazy_pinyin", None)
    _HAS_PYPINYIN = lazy_pinyin is not None

_RE_HAS_CHINESE = re.compile(r"[\u4e00-\u9fff]")
_PINYIN_WARNED: set[str] = set()

XML_TITLE = "Test Module"
XML_VERSION = "1.0"
XML_DESCRIPTION = "Generated from .can test cases"
_GROUP_KEY_SEP = "\x1f"


class XMLGenerationUtility:
    """XML Excel 解析与内容生成功能封装。"""
    pass


def is_history_sheet_name(sheet_name: str) -> bool:
    """判断是否为历史/修订工作表。"""
    normalized_name = str(sheet_name).strip()
    normalized_lower = normalized_name.lower()
    return (
        normalized_lower == "rev.hist"
        or "rev.hist" in normalized_lower
        or "变更历史" in normalized_name
    )


def find_excel_files(input_path: str) -> list[str]:
    """
    查找输入路径中的所有 Excel 文件（支持单文件或目录，递归子目录）。
    形参：input_path — 文件路径或文件夹路径（str）。
    返回值：list[str]，Excel 文件路径列表（已去重、排序，排除 ~$ 临时文件）。
    """
    excel_files = []
    if os.path.isfile(input_path):
        if input_path.lower().endswith(('.xlsx', '.xls')):
            excel_files.append(input_path)
    elif os.path.isdir(input_path):
        for ext in ['*.xlsx', '*.xls']:
            pattern = os.path.join(input_path, ext)
            excel_files.extend(glob.glob(pattern))
            pattern = os.path.join(input_path, '**', ext)
            excel_files.extend(glob.glob(pattern, recursive=True))
    else:
        raise FileNotFoundError(f"路径不存在: {input_path}")
    excel_files = [
        excel_file for excel_file in excel_files if not os.path.basename(excel_file).startswith('~$')
    ]
    excel_files = sorted(list(set(excel_files)))
    return excel_files


def escape_xml(text: Any) -> str:
    """
    转义 XML 特殊字符（& < > " '），用于写入属性/文本时避免非法字符。
    """
    if text is None:
        return ""
    text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def dump_sheet_head_preview(ws: Any, *, max_rows: int = 10, max_cols: int = 20) -> str:
    """打印/记录 sheet 前几行内容，便于定位“为什么被判定为无效表”。"""
    lines = []
    try:
        for row_idx, row_vals in enumerate(
            ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=True), start=1
        ):
            vals = []
            for cell_value in (row_vals[:max_cols] if row_vals else []):
                if cell_value is None:
                    vals.append("")
                else:
                    cell_text = (
                        str(cell_value).replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n").strip()
                    )
                    vals.append(cell_text)
            lines.append(f"    row{row_idx}: {vals}")
    except Exception as error:
        lines.append(f"    <读取失败>: {error}")
    return "\n".join(lines)


def contains_chinese(text: str) -> bool:
    """判断字符串是否包含中文字符。"""
    return bool(text and _RE_HAS_CHINESE.search(text))


def to_pinyin_if_needed(
    text: str,
    *,
    logger: Optional[logging.Logger] = None,
) -> str:
    """
    若包含中文则转拼音（供 XML capltestcase name 使用）；否则原样返回。
    """
    text_value = str(text) if text is not None else ""
    if not contains_chinese(text_value):
        return text_value
    if not _HAS_PYPINYIN or lazy_pinyin is None:
        if text_value not in _PINYIN_WARNED:
            _PINYIN_WARNED.add(text_value)
            print(f"[警告] 发现中文但未安装 pypinyin，无法转拼音：{text_value!r}")
            if logger:
                logger.warning("发现中文但未安装 pypinyin，无法转拼音：%r", text_value)
        return text_value
    pinyin_result = "".join(lazy_pinyin(text_value, errors=lambda non_chinese: list(non_chinese)))
    pinyin_result = re.sub(r"\s+", "_", pinyin_result).strip()
    return pinyin_result


def parse_testcases_from_sheet(
    ws: Any,
    *,
    allowed_levels=None,
    allowed_platforms=None,
    allowed_models=None,
    allowed_target_versions=None,
    sheet_name: Optional[str] = None,
    excel_name: Optional[str] = None,
    seen_case_ids: Optional[dict] = None,
    header_row_idx: int = 1,
    header_vals=None,
    logger: Optional[logging.Logger] = None,
    parse_logger: Optional[logging.Logger] = None,
    quiet_skip: bool = False,
) -> tuple[list[dict], dict]:
    """
    从单个工作表中解析测试用例（表头动态查找，等级/平台/车型/类型过滤，用例ID 清洗与同表去重）。
    返回 (testcases, sheet_stats)。
    """
    testcases = []
    display_name = sheet_name if sheet_name else ws.title
    excel_display = excel_name if excel_name else ""
    excel_short = os.path.basename(excel_display) if excel_display else ""
    if seen_case_ids is None:
        seen_case_ids = {}
    sheet_dup_count: dict[str, int] = {}

    total_cases_count = 0
    auto_test_count = 0
    skipped_count = 0
    case_filter = CaseFilter(
        allowed_levels=allowed_levels,
        allowed_platforms=allowed_platforms,
        allowed_models=allowed_models,
        allowed_target_versions=allowed_target_versions,
    )

    if header_vals is None:
        header_row_idx2, header_vals2, _ = find_testcase_header_row(
            ws, scan_rows=50, debug_sheet_name=display_name
        )
        if header_row_idx2 is None or not header_vals2:
            return testcases, {
                'total_cases': 0,
                'filtered_by_level': 0,
                'filtered_by_platform': 0,
                'filtered_by_model': 0,
                'filtered_by_type': 0,
                'filtered_by_target_version': 0,
            }
        header_row_idx = header_row_idx2
        header_vals = header_vals2

    case_type_col_idx = find_case_type_column_index_in_values(header_vals)
    case_id_col_idx = find_col_index_by_name_in_values(header_vals, ["用例ID", "用例id", "用例编号"])
    group_col_idx = find_col_index_by_name_in_values(header_vals, ["功能模块", "模块"])
    level_col_idx = find_col_index_by_name_in_values(header_vals, ["等级", "用例等级"])
    platform_col_idx = find_col_index_by_name_in_values(header_vals, ["平台", "Platform"])
    model_col_idx = find_col_index_by_name_in_values(header_vals, ["车型", "Model"])
    target_version_col_idx = find_col_index_by_name_in_values(
        header_vals, ["Target Version", "目标版本"]
    )
    # Target Version 缺列时不在此打 warning，仅 CAN 解析路径打一次，避免 CAN+XML 重复

    # 必填列仅用例ID；功能模块改为可选（XML 分组不再依赖功能模块）
    missing_cols = []
    if case_id_col_idx is None:
        missing_cols.append("用例ID")
    if missing_cols:
        sheet_label = f"{excel_short}/{display_name}" if excel_short else display_name
        err_msg = (
            f"[错误] 工作表「{sheet_label}」缺少必填列：{'、'.join(missing_cols)}，跳过本表生成"
        )
        if logger:
            logger.error(err_msg)
        else:
            print(err_msg)
        if parse_logger:
            parse_logger.error(
                "XML 用例表缺少必填列：excel=%s sheet=%s 缺少=%s",
                excel_short or excel_display or "",
                display_name,
                "、".join(missing_cols),
            )
        return [], {
            'total_cases': 0,
            'filtered_by_level': 0,
            'filtered_by_platform': 0,
            'filtered_by_model': 0,
            'filtered_by_type': 0,
            'filtered_by_target_version': 0,
        }

    # 可选筛选列：缺则读行时该维度默认通过；warning 仅在 CAN 解析路径打一次，避免 CAN+XML 重复

    data_start_row = int(header_row_idx) + 1
    for row_idx, row_vals in enumerate(
        ws.iter_rows(min_row=1, max_col=50, values_only=True), start=1
    ):
        if row_idx < data_start_row:
            continue
        if not row_vals or not any(row_vals):
            continue

        case_id_value = row_vals[case_id_col_idx] if len(row_vals) > case_id_col_idx else None
        if not case_id_value:
            continue

        raw_case_id_str = str(case_id_value).strip()
        case_id_str, _changed, _reason = sanitize_case_id(case_id_value)
        if not case_id_str:
            continue

        total_cases_count += 1

        group_cell_val = (
            row_vals[group_col_idx]
            if group_col_idx is not None and len(row_vals) > group_col_idx
            else None
        )
        group_name_for_log = str(group_cell_val).strip() if group_cell_val is not None else ""

        # 可选列：缺列时默认通过（ALL / 自动）
        level_cell_val = (
            row_vals[level_col_idx] if level_col_idx is not None and len(row_vals) > level_col_idx else None
        )
        level_norm = (
            (str(level_cell_val).strip() if level_cell_val is not None else "").upper()
            if level_col_idx is not None else "ALL"
        )
        platform_cell_val = (
            row_vals[platform_col_idx] if platform_col_idx is not None and len(row_vals) > platform_col_idx else None
        )
        platform_norm = (
            (str(platform_cell_val).strip() if platform_cell_val is not None else "").upper()
            if platform_col_idx is not None else "ALL"
        )
        model_cell_val = (
            row_vals[model_col_idx] if model_col_idx is not None and len(row_vals) > model_col_idx else None
        )
        model_norm = (
            (str(model_cell_val).strip() if model_cell_val is not None else "").upper()
            if model_col_idx is not None else "ALL"
        )
        case_type_value = (
            row_vals[case_type_col_idx] if case_type_col_idx is not None and len(row_vals) > case_type_col_idx else None
        )
        case_type_str = (
            str(case_type_value).strip() if case_type_value is not None else ""
        ) if case_type_col_idx is not None else "自动"
        target_version_cell = (
            row_vals[target_version_col_idx]
            if target_version_col_idx is not None and len(row_vals) > target_version_col_idx
            else None
        )
        target_version_str = (
            str(target_version_cell).strip() if target_version_cell is not None else ""
        ) if target_version_col_idx is not None else ""

        filtered, reason = case_filter.is_filtered(
            level_norm, platform_norm, model_norm, case_type_str, target_version=target_version_str
        )
        if filtered:
            skipped_count += 1
            if logger:
                logger.info(
                    "[跳过] 用例ID=%s, 功能模块=%s（%s）",
                    case_id_str, group_name_for_log, reason,
                )
            if not quiet_skip:
                print(f"[跳过] 用例ID={case_id_str}, 功能模块={group_name_for_log}（{reason}）")
            continue

        auto_test_count += 1

        prev = seen_case_ids.get(case_id_str)
        if prev is not None:
            prev_excel, prev_sheet, prev_row, prev_raw = prev
            if (prev_excel, prev_sheet, prev_row, prev_raw) != (
                excel_display, display_name, row_idx, raw_case_id_str
            ):
                dup_count = sheet_dup_count.get(case_id_str, 0) + 1
                sheet_dup_count[case_id_str] = dup_count
                case_id_str = f"{case_id_str}_{dup_count}"
        else:
            seen_case_ids[case_id_str] = (excel_display, display_name, row_idx, raw_case_id_str)

        testcase_name = case_id_str.replace("-", "_")
        group_name = str(group_cell_val).strip() if group_cell_val is not None else ""
        if not group_name:
            group_name = " "
        if not testcase_name:
            testcase_name = " "

        testcases.append({
            "name": testcase_name,
            "group": group_name,
            "raw_id": case_id_str,
            "sheet": display_name,
        })

    if quiet_skip and skipped_count > 0:
        try:
            st = case_filter.stats
            print(
                f"  [本表 '{display_name}'] 跳过 {skipped_count} 个用例"
                f"（等级={st.filtered_by_level} 平台={st.filtered_by_platform} "
                f"车型={st.filtered_by_model} Target Version={st.filtered_by_target_version} "
                f"类型={st.filtered_by_type}），通过 {len(testcases)} 个"
            )
        except Exception:
            pass

    st = case_filter.stats
    sheet_stats = {
        'total_cases': total_cases_count,
        'filtered_by_level': st.filtered_by_level,
        'filtered_by_platform': st.filtered_by_platform,
        'filtered_by_model': st.filtered_by_model,
        'filtered_by_type': st.filtered_by_type,
        'filtered_by_target_version': st.filtered_by_target_version,
    }
    return testcases, sheet_stats


def parse_testcases_from_excel(
    excel_path: str,
    *,
    allowed_levels=None,
    allowed_platforms=None,
    allowed_models=None,
    allowed_target_versions=None,
    seen_case_ids: Optional[dict] = None,
    excel_label: Optional[str] = None,
    allowed_sheet_names: Optional[list] = None,
    selected_filter: Optional[dict] = None,
    workbook_cache: Optional[dict] = None,
    logger: Optional[logging.Logger] = None,
    parse_logger: Optional[logging.Logger] = None,
    quiet_skip: bool = False,
) -> tuple[dict[str, list], dict]:
    """
    从用例设计 Excel 中解析所有测试用例（遍历工作表，跳过 Rev.Hist，表头校验后逐表调用 parse_testcases_from_sheet）。
    返回 (sheet_testcases_dict, stats_dict)。
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"找不到 Excel 文件: {excel_path}")

    normalized_excel_path = os.path.normcase(os.path.abspath(excel_path))
    cached_workbook = None
    should_close_workbook = workbook_cache is None
    if workbook_cache is not None:
        cached_workbook = workbook_cache.get(normalized_excel_path)

    try:
        print(f"  [正在打开工作簿] {os.path.basename(excel_path)}")
    except Exception:
        pass
    try:
        if cached_workbook is None:
            cached_workbook = ExcelService.open_workbook(
                excel_path,
                data_only=True,
                read_only=False,
            )
            if workbook_cache is not None:
                workbook_cache[normalized_excel_path] = cached_workbook
        wb = cached_workbook
    except Exception as error:
        error_msg = str(error)
        if 'decompressing' in error_msg.lower() or 'incorrect header' in error_msg.lower() or 'badzipfile' in error_msg.lower():
            raise ValueError(
                f"Excel 文件格式错误或文件已损坏: {excel_path}\n"
                f"错误详情: {error_msg}\n"
                "请检查：\n"
                "1. 文件是否是有效的 Excel 文件（.xlsx 格式）\n"
                "2. 文件是否已损坏\n"
                "3. 文件是否被其他程序占用\n"
                "4. 尝试用 Excel 打开文件并重新保存"
            ) from error
        raise ValueError(f"无法读取 Excel 文件: {excel_path}\n错误详情: {error_msg}") from error

    for _sn in wb.sheetnames:
        try:
            _ws = wb[_sn]
            if getattr(_ws, "_dimensions", None) is not None:
                _ws._dimensions = None
        except Exception:
            pass

    sheet_names = wb.sheetnames
    try:
        print(f"  [已打开工作簿] 工作表数: {len(sheet_names)}")
    except Exception:
        pass
    if allowed_sheet_names is not None and len(allowed_sheet_names) > 0:
        sheet_names = [
            sheet_name for sheet_name in sheet_names if sheet_name in allowed_sheet_names
        ]
    if selected_filter is not None:
        excel_name_lower = os.path.basename(excel_path).lower()
        if excel_name_lower not in selected_filter:
            sheet_names = []
        else:
            allowed_set = selected_filter[excel_name_lower]
            sheet_names = [
                sheet_name
                for sheet_name in sheet_names
                if str(sheet_name).strip().lower() in allowed_set
            ]

    sheet_testcases_dict = {}
    if excel_label is None:
        excel_label = os.path.basename(excel_path)

    stats = {
        'total_cases': 0,
        'filtered_by_level': 0,
        'filtered_by_platform': 0,
        'filtered_by_model': 0,
        'filtered_by_type': 0,
        'filtered_by_target_version': 0,
        'header_validation_failed': 0,
        'header_validation_details': [],
    }

    for sheet_name in sheet_names:
        if is_history_sheet_name(sheet_name):
            continue
        sheet_name_str = str(sheet_name).strip()

        ws = wb[sheet_name]
        try:
            if getattr(ws, "_dimensions", None) is not None:
                ws._dimensions = None
        except Exception:
            pass

        header_row_idx, header_vals, found_group_col = find_testcase_header_row(
            ws, scan_rows=50, debug_sheet_name=sheet_name_str
        )
        if header_row_idx is None or not header_vals:
            stats['header_validation_failed'] += 1
            stats['header_validation_details'].append({
                'sheet': sheet_name,
                'details': ["未在前50行内识别到表头（至少需包含'用例ID'列）"],
            })
            dump = dump_sheet_head_preview(ws, max_rows=10, max_cols=25)
            msg = f"\n跳过工作表 '{sheet_name}'（未找到有效的测试用例表头：用例ID列未识别）\n{dump}"
            print(msg)
            if logger:
                logger.info(msg)
            if parse_logger:
                parse_logger.error(
                    "XML 用例表未识别到表头（需包含用例ID）：excel=%s sheet=%s",
                    os.path.basename(excel_path),
                    str(sheet_name),
                )
            continue

        if not found_group_col:
            header_preview = []
            for header_cell in (header_vals[:25] if header_vals else []):
                if header_cell is None:
                    header_preview.append("")
                else:
                    cell_text = (
                        str(header_cell).replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n").strip()
                    )
                    header_preview.append(cell_text)
            case_id_idx = find_col_index_by_name_in_values(header_vals, ["用例ID", "用例id", "用例编号"])
            group_idx = find_col_index_by_name_in_values(header_vals, ["功能模块", "模块", "模块名称"])
            warn_msg = (
                f"[提示] 工作表 '{sheet_name}'：已识别到表头行=第{header_row_idx}行（用例ID列已识别），"
                f"但未识别到'功能模块/模块'列名，将回退到固定第3列读取功能模块。\n"
                f"  表头(前25列)={header_preview}\n"
                f"  识别结果: 用例ID列idx0={case_id_idx}, 功能模块列idx0={group_idx}"
            )
            print(warn_msg)

        if logger:
            logger.info("  处理表=%s", sheet_name_str)

        sheet_seen_ids = {}
        sheet_testcases, sheet_stats = parse_testcases_from_sheet(
            ws,
            allowed_levels=allowed_levels,
            allowed_platforms=allowed_platforms,
            allowed_models=allowed_models,
            allowed_target_versions=allowed_target_versions,
            sheet_name=sheet_name,
            excel_name=excel_label,
            seen_case_ids=sheet_seen_ids,
            header_row_idx=header_row_idx,
            header_vals=header_vals,
            logger=logger,
            parse_logger=parse_logger,
            quiet_skip=quiet_skip,
        )

        stats['total_cases'] += sheet_stats.get('total_cases', 0)
        stats['filtered_by_level'] += sheet_stats.get('filtered_by_level', 0)
        stats['filtered_by_platform'] += sheet_stats.get('filtered_by_platform', 0)
        stats['filtered_by_model'] += sheet_stats.get('filtered_by_model', 0)
        stats['filtered_by_target_version'] += sheet_stats.get('filtered_by_target_version', 0)
        stats['filtered_by_type'] += sheet_stats.get('filtered_by_type', 0)

        if sheet_testcases:
            sheet_testcases_dict[sheet_name] = sheet_testcases

    if should_close_workbook:
        wb.close()
    return sheet_testcases_dict, stats


def group_testcases_by_sheet_and_group(
    sheet_testcases_dict: dict[str, list],
) -> dict[str, dict[str, list]]:
    """
    先按工作表分组，每个工作表只保留一个 testgroup（不再按功能模块拆分）。
    返回 { 工作表名: { 分组名: [用例列表] } }。
    """
    result = {}
    for sheet_name, testcases in sheet_testcases_dict.items():
        sheet_group_name = str(sheet_name).strip() if sheet_name is not None else ""
        if not sheet_group_name:
            sheet_group_name = " "
        result[sheet_name] = {sheet_group_name: list(testcases)}
    return result


def generate_xml_content(
    excel_files_dict: dict,
    *,
    logger: Optional[logging.Logger] = None,
) -> str:
    """
    生成 XML 内容（两层 testgroup：Excel 文件 → Sheet，sheet 下直接挂 capltestcase；name 含中文时转拼音）。
    excel_files_dict: { Excel 文件路径: { 工作表名: { 分组名: [用例 dict 列表] } } }。
    返回完整 XML 字符串（UTF-8，testmodule 根节点）。
    """
    lines = []
    lines.append('<?xml version="1.0" encoding="utf-8" standalone="yes"?>')
    lines.append(f'<testmodule title="{escape_xml(XML_TITLE)}" version="{escape_xml(XML_VERSION)}">')
    lines.append(f'\t<description>{escape_xml(XML_DESCRIPTION)}</description>')

    excel_items = list(excel_files_dict.items())
    for excel_idx, (excel_name, sheet_groups_dict) in enumerate(excel_items, start=1):
        excel_title = os.path.splitext(os.path.basename(excel_name))[0]
        if not excel_title or not excel_title.strip():
            excel_title = " "
        lines.append(f'\t<testgroup title="{escape_xml(excel_title)}">')

        sheet_items = list(sheet_groups_dict.items())
        for sheet_idx, (sheet_name, group_dict) in enumerate(sheet_items, start=1):
            sheet_title = " " if not sheet_name or not sheet_name.strip() else sheet_name
            lines.append(f'\t\t<testgroup title="{escape_xml(sheet_title)}">')

            group_items = list(group_dict.items())
            for group_key, testcases in group_items:
                for testcase_item in testcases:
                    testcase_name = (
                        testcase_item["name"]
                        if testcase_item.get("name") and testcase_item["name"].strip()
                        else " "
                    )
                    testcase_name_pinyin = to_pinyin_if_needed(testcase_name, logger=logger)
                    lines.append(f'\t\t\t<capltestcase name="{escape_xml(testcase_name_pinyin)}">\t')
                    lines.append('\t\t\t</capltestcase>\t')
            lines.append('\t\t</testgroup>')
        lines.append('\t</testgroup>')
    lines.append('</testmodule>')
    return '\n'.join(lines)


XMLGenerationUtility.is_history_sheet_name = staticmethod(is_history_sheet_name)
XMLGenerationUtility.find_excel_files = staticmethod(find_excel_files)
XMLGenerationUtility.parse_testcases_from_sheet = staticmethod(parse_testcases_from_sheet)
XMLGenerationUtility.parse_testcases_from_excel = staticmethod(parse_testcases_from_excel)
XMLGenerationUtility.group_testcases_by_sheet_and_group = staticmethod(group_testcases_by_sheet_and_group)
XMLGenerationUtility.generate_xml_content = staticmethod(generate_xml_content)
