#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAN Excel 读取仓储模块。

负责解析工作簿、识别表头、筛选用例并输出 CAN 生成所需的结构化数据。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

from core.common.sanitizer import sanitize_case_id
from core.parse_table_loggers import get_caseid_clean_dup_logger, get_testcases_parse_logger
from utils.excel_io import ExcelService, ColumnMapper, norm_str

from core.case_filter import CaseFilter
from core.excel_header import (
    find_case_type_column_index_in_values,
    find_col_index_by_name_in_values,
    find_testcase_header_row,
)

from .models import CANRawStep, CANTestCase

# 表头/数据扫描列数：与 XML 一致并支持“大灯高度调节”等表头靠右的表格（用例ID 可能在 50 列之后）
CAN_SHEET_MAX_COL = 80


@dataclass(slots=True)
class RepoStats:
    """CAN 用例读取统计信息。

    参数：
        各字段分别表示总用例数、按过滤条件被筛掉的数量及表头校验失败信息。

    返回：
        作为统计载体供仓储层汇总与上层展示使用。
    """
    total_cases: int = 0
    filtered_by_level: int = 0
    filtered_by_platform: int = 0
    filtered_by_model: int = 0
    filtered_by_type: int = 0
    filtered_by_target_version: int = 0
    header_validation_failed: int = 0
    header_validation_details: list[dict] = None

    def __post_init__(self) -> None:
        if self.header_validation_details is None:
            self.header_validation_details = []

    def to_dict(self) -> dict:
        """导出统计信息字典。

        参数：无。
        返回：包含全部统计字段的 `dict`。
        """
        return {
            "total_cases": self.total_cases,
            "filtered_by_level": self.filtered_by_level,
            "filtered_by_platform": self.filtered_by_platform,
            "filtered_by_model": self.filtered_by_model,
            "filtered_by_type": self.filtered_by_type,
            "filtered_by_target_version": self.filtered_by_target_version,
            "header_validation_failed": self.header_validation_failed,
            "header_validation_details": self.header_validation_details,
        }


class CANExcelRepository:
    """CAN Excel 仓储：负责读取 Excel 并产出 CANTestCase 数据。"""
    def __init__(
        self,
        base_dir: str,
        config=None,
        *,
        allowed_levels: set[str] | None = None,
        allowed_platforms: set[str] | None = None,
        allowed_models: set[str] | None = None,
        allowed_target_versions: set[str] | None = None,
        selected_filter: dict[str, set[str]] | None = None,
    ) -> None:
        self.base_dir = base_dir
        self.config = config
        self.case_filter = CaseFilter(
            allowed_levels=allowed_levels,
            allowed_platforms=allowed_platforms,
            allowed_models=allowed_models,
            allowed_target_versions=allowed_target_versions,
        )
        self.selected_filter = selected_filter
        self.stats = RepoStats()
        # 每个 sheet 内被过滤用例的“跳过”事件，供外层按用例顺序统一输出日志
        # key: (excel_path, sheet_name) -> list[{"excel_row", "case_id", "group", "case_type", "reason"}]
        self.skip_events_map: dict[tuple[str, str], list[dict]] = {}

    def load_cases(
        self,
        excel_path: str,
        *,
        workbook_cache: dict[str, object] | None = None,
    ) -> tuple[dict[tuple[str, str], list[CANTestCase]], dict]:
        """加载整个 Excel 的 CAN 用例。

        参数：
            excel_path：目标 Excel 路径。
            workbook_cache：可选工作簿缓存，用于复用已打开 workbook。

        返回：
            `(sheet_cases_map, stats_dict)`，分别为按 sheet 分组的用例与统计信息。
        """
        # 与 XML 生成脚本保持一致：使用 read_only=False，方便多次 iter_rows，
        # 并让 ExcelService 内部的 _dimensions 重置逻辑生效，避免只读到 A 列。
        normalized_excel_path = os.path.normcase(os.path.abspath(excel_path))
        workbook_obj = None
        should_close_workbook = workbook_cache is None
        if workbook_cache is not None:
            workbook_obj = workbook_cache.get(normalized_excel_path)
        if workbook_obj is None:
            workbook_obj = ExcelService.open_workbook(excel_path, read_only=False, data_only=True)
            if workbook_cache is not None:
                workbook_cache[normalized_excel_path] = workbook_obj
        wb = workbook_obj
        excel_name = os.path.basename(excel_path)
        excel_name_lower = excel_name.lower()
        out: dict[tuple[str, str], list[CANTestCase]] = {}
        try:
            for sheet_name in wb.sheetnames:
                if str(sheet_name).strip().lower() == "rev.hist":
                    continue
                if self.selected_filter is not None:
                    if excel_name_lower not in self.selected_filter:
                        continue
                    # 与 XML 一致：用 strip().lower() 匹配，避免 "TC " 等带空格 sheet 名被误跳过
                    sheet_key = str(sheet_name).strip().lower()
                    if sheet_key not in self.selected_filter.get(excel_name_lower, set()):
                        continue
                ws = wb[sheet_name]
                cases = self.load_sheet_cases(ws, excel_path, excel_name)
                # 有通过用例或虽无通过但有跳过事件时都加入，便于 CAN 日志与 XML 一致（处理Sheet/跳过逐条）
                if cases or self.skip_events_map.get((excel_path, sheet_name)):
                    out[(excel_path, sheet_name)] = cases
        finally:
            if should_close_workbook:
                wb.close()
        # 合并 CaseFilter 的过滤统计到 RepoStats
        self.stats.filtered_by_level += self.case_filter.stats.filtered_by_level
        self.stats.filtered_by_platform += self.case_filter.stats.filtered_by_platform
        self.stats.filtered_by_model += self.case_filter.stats.filtered_by_model
        self.stats.filtered_by_type += self.case_filter.stats.filtered_by_type
        self.stats.filtered_by_target_version += self.case_filter.stats.filtered_by_target_version
        return out, self.stats.to_dict()

    def load_sheet_cases(self, ws, excel_path: str, excel_name: str) -> list[CANTestCase]:
        """从单个工作表加载并过滤用例。

        Args:
            ws: 当前 Excel 工作表对象。
            excel_path: Excel 文件绝对路径。
            excel_name: Excel 文件名（用于日志展示）。

        Returns:
            list[CANTestCase]: 通过筛选并解析成功的用例列表。
        """
        sheet_name = str(ws.title)

        # 1. 使用 XML 的表头扫描逻辑，在前 50 行内定位真正的表头行
        header_row_idx, header_vals, _found_group = find_testcase_header_row(
            ws, scan_rows=50, debug_sheet_name=sheet_name
        )
        if header_row_idx is None or not header_vals:
            # 与 XML 含义对齐：在前 50 行内未识别到包含“用例ID”的表头
            self.stats.header_validation_failed += 1
            self.stats.header_validation_details.append(
                {
                    "sheet": sheet_name,
                    "details": ["未在前50行内识别到表头（至少需包含'用例ID'列）"],
                }
            )
            return []

        # 2. 使用 XML 的列索引发现逻辑，查找各业务列的位置（0-based）
        case_type_col_idx = find_case_type_column_index_in_values(header_vals)
        case_id_col_idx = find_col_index_by_name_in_values(
            header_vals, ["用例ID", "用例id", "用例编号", "用例 ID"]
        )
        group_col_idx = find_col_index_by_name_in_values(header_vals, ["功能模块", "模块", "模块名称"])
        level_col_idx = find_col_index_by_name_in_values(header_vals, ["等级", "用例等级"])
        platform_col_idx = find_col_index_by_name_in_values(header_vals, ["平台", "Platform"])
        model_col_idx = find_col_index_by_name_in_values(header_vals, ["车型", "Model"])
        target_version_col_idx = find_col_index_by_name_in_values(
            header_vals, ["Target Version", "目标版本"]
        )

        # 用例名称/步骤/预期：CAN 生成必填列
        case_name_col_idx = find_col_index_by_name_in_values(
            header_vals, ["用例名称", "用例名", "name", "标题"]
        )
        step_col_idx = find_col_index_by_name_in_values(
            header_vals, ["测试步骤", "步骤", "step", "Step"]
        )
        expected_col_idx = find_col_index_by_name_in_values(
            header_vals, ["预期结果", "预期", "结果", "expect", "expected"]
        )

        # 3. 必填列检查：CAN 生成必须「用例ID」「用例名称」「测试步骤」「预期结果」；功能模块/等级/平台/车型/用例类型为可选
        missing_cols: list[str] = []
        if case_id_col_idx is None:
            missing_cols.append("用例ID")
        if case_name_col_idx is None:
            missing_cols.append("用例名称")
        if step_col_idx is None:
            missing_cols.append("测试步骤")
        if expected_col_idx is None:
            missing_cols.append("预期结果")
        if missing_cols:
            self.stats.header_validation_failed += 1
            self.stats.header_validation_details.append(
                {
                    "sheet": sheet_name,
                    "details": [f"缺少必填列：{'、'.join(missing_cols)}"],
                }
            )
            return []

        # 可选列：缺则写入 TestCases.log warning；功能模块缺则跳过日志里显示「-」，筛选列缺则默认通过
        testcases_log = get_testcases_parse_logger(self.base_dir)
        if group_col_idx is None:
            testcases_log.warning(
                "表头不包含功能模块列，跳过用例时日志中功能模块显示为「-」：excel=%s sheet=%s",
                excel_name, sheet_name,
            )
        if level_col_idx is None:
            testcases_log.warning(
                "表头不包含等级列，默认等级均符合要求：excel=%s sheet=%s",
                excel_name, sheet_name,
            )
        if platform_col_idx is None:
            testcases_log.warning(
                "表头不包含平台列，默认平台均符合要求：excel=%s sheet=%s",
                excel_name, sheet_name,
            )
        if model_col_idx is None:
            testcases_log.warning(
                "表头不包含车型列，默认车型均符合要求：excel=%s sheet=%s",
                excel_name, sheet_name,
            )
        if case_type_col_idx is None:
            testcases_log.warning(
                "表头不包含用例类型列，默认用例类型均符合要求：excel=%s sheet=%s",
                excel_name, sheet_name,
            )
        if target_version_col_idx is None:
            testcases_log.warning(
                "表头不包含Target Version列，默认Target Version均符合要求：excel=%s sheet=%s",
                excel_name, sheet_name,
            )

        # 4. 按 CAN 原有语义遍历数据行：同一用例可跨多行，case_id 只在首行出现
        cases: list[CANTestCase] = []
        current_case: CANTestCase | None = None
        skipping_case = False
        sheet_seen_ids: dict[str, tuple[str, str, int, str]] = {}
        sheet_dup_count: dict[str, int] = {}  # case_id -> 重复次数（第2次=1→id_1，第3次=2→id_2）
        sheet_key = (excel_path, sheet_name)
        skip_events: list[dict] = []

        data_start_row = int(header_row_idx) + 1
        for row_idx, row_vals in enumerate(
            ws.iter_rows(min_row=1, max_col=CAN_SHEET_MAX_COL, values_only=True),
            start=1,
        ):
            # 表头之前的行跳过
            if row_idx < data_start_row:
                continue
            # 空行直接跳过
            if not row_vals or not any(row_vals):
                continue

            # 新用例起始行：有非空的用例ID
            case_id_cell = row_vals[case_id_col_idx] if len(row_vals) > case_id_col_idx else None
            case_id_value = norm_str(case_id_cell)
            has_new_case = case_id_value != ""

            if has_new_case:
                if current_case is not None:
                    cases.append(current_case)

                raw_case_id = case_id_value
                case_id, changed, reason = sanitize_case_id(raw_case_id)
                if not case_id:
                    _log_caseid = get_caseid_clean_dup_logger(self.base_dir)
                    _log_caseid.warning(
                        "用例ID为空，跳过：excel=%s sheet=%s row=%s raw=%r",
                        excel_name, sheet_name, row_idx, raw_case_id,
                    )
                    current_case = None
                    skipping_case = True
                    continue

                case_id_had_issues = changed
                case_id_issue_type = "sanitized" if changed else ""
                duplicate_original_id = ""
                if changed:
                    _log_caseid = get_caseid_clean_dup_logger(self.base_dir)
                    _log_caseid.warning(
                        "[warn] 用例ID清洗：表=%s/%s 行=%s raw=%r -> cleaned=%r（%s，已做处理）",
                        excel_name, sheet_name, row_idx, raw_case_id, case_id, reason,
                    )
                    if reason == "chinese_to_pinyin" or reason == "chinese_to_pinyin_strip_all":
                        _log_caseid.warning(
                            "[warn] 用例ID含中文已转拼音：表=%s/%s 行=%s 原始id=%r -> 清洗后=%r",
                            excel_name, sheet_name, row_idx, raw_case_id, case_id,
                        )

                # 读出等级/平台/车型/类型；若该列不存在（可选列未在表头）则默认通过
                level_cell = (
                    row_vals[level_col_idx] if level_col_idx is not None and len(row_vals) > level_col_idx else None
                )
                platform_cell = (
                    row_vals[platform_col_idx] if platform_col_idx is not None and len(row_vals) > platform_col_idx else None
                )
                model_cell = (
                    row_vals[model_col_idx] if model_col_idx is not None and len(row_vals) > model_col_idx else None
                )
                case_type_cell = (
                    row_vals[case_type_col_idx]
                    if case_type_col_idx is not None and len(row_vals) > case_type_col_idx
                    else None
                )
                target_version_cell = (
                    row_vals[target_version_col_idx]
                    if target_version_col_idx is not None and len(row_vals) > target_version_col_idx
                    else None
                )

                level = norm_str(level_cell).upper() if level_col_idx is not None else "ALL"
                platform = norm_str(platform_cell).upper() if platform_col_idx is not None else "ALL"
                model = norm_str(model_cell).upper() if model_col_idx is not None else "ALL"
                case_type = norm_str(case_type_cell) if case_type_col_idx is not None else "自动"
                target_version = norm_str(target_version_cell) if target_version_col_idx is not None else ""

                self.stats.total_cases += 1

                # 过滤逻辑与 XML 含义一致：等级 -> 平台 -> 车型 -> Target Version -> 用例类型
                filtered, reason = self.case_filter.is_filtered(
                    level, platform, model, case_type, target_version=target_version
                )
                if filtered:
                    case_type_p = case_type.replace("\n", " ") if case_type else ""
                    group_val = (
                        row_vals[group_col_idx]
                        if group_col_idx is not None and len(row_vals) > group_col_idx
                        else None
                    )
                    group_name = norm_str(group_val) or "-"

                    skip_events.append(
                        {
                            "excel_row": row_idx,
                            "case_id": str(case_id_value),
                            "group": group_name,
                            "case_type": case_type_p,
                            "reason": reason,
                        }
                    )
                    current_case = None
                    skipping_case = True
                    continue

                # 用例ID重复检测：第2次改为 id_1，第3次改为 id_2，依此类推
                prev = sheet_seen_ids.get(case_id)
                if prev is not None:
                    prev_excel, prev_sheet, prev_row, prev_raw = prev
                    if (prev_excel, prev_sheet, prev_row, prev_raw) != (excel_name, sheet_name, row_idx, raw_case_id):
                        case_id_had_issues = True
                        case_id_issue_type = "duplicate"
                        dup_count = sheet_dup_count.get(case_id, 0) + 1
                        sheet_dup_count[case_id] = dup_count
                        duplicate_original_id = case_id
                        case_id = f"{case_id}_{dup_count}"
                        _log_caseid = get_caseid_clean_dup_logger(self.base_dir)
                        _log_caseid.warning(
                            "[dup] 用例ID重复：表=%s sheet=%s 用例ID=%r 首次行=%s 再次行=%s 已改为 %r",
                            excel_name, sheet_name, duplicate_original_id, prev_row, row_idx, case_id,
                        )
                else:
                    sheet_seen_ids[case_id] = (excel_name, sheet_name, row_idx, raw_case_id)

                # 用例名称列（若存在）
                case_name_val = (
                    row_vals[case_name_col_idx]
                    if case_name_col_idx is not None and len(row_vals) > case_name_col_idx
                    else None
                )
                case_name = norm_str(case_name_val)

                current_case = CANTestCase(
                    case_id=case_id,
                    raw_id=raw_case_id,
                    name=case_name,
                    level=level,
                    case_id_had_issues=case_id_had_issues,
                    case_id_issue_type=case_id_issue_type,
                    duplicate_original_id=duplicate_original_id,
                    excel_row=row_idx,
                    excel_name=excel_name,
                    sheet_name=sheet_name,
                    platform=platform,
                    model=model,
                    case_type=case_type,
                )
                skipping_case = False

            # 非新用例起始行：若当前用例被标记为跳过，整段区域都不再收集步骤
            if skipping_case or current_case is None:
                continue

            # 收集步骤/预期列（按行号 zip 配对，保留位置对齐）
            # 注意：不能对整个文本 norm_str（会 strip 前导换行），先 splitlines 再逐行 norm
            step_lines: list[str] = []
            expected_lines: list[str] = []
            if step_col_idx is not None and len(row_vals) > step_col_idx:
                raw_step = row_vals[step_col_idx]
                step_text = str(raw_step) if raw_step is not None else ""
                step_lines = step_text.splitlines() if step_text else []
            if expected_col_idx is not None and len(row_vals) > expected_col_idx:
                raw_expected = row_vals[expected_col_idx]
                expected_text = str(raw_expected) if raw_expected is not None else ""
                expected_lines = expected_text.splitlines() if expected_text else []

            for line_pair_index in range(max(len(step_lines), len(expected_lines))):
                step_line = (
                    norm_str(step_lines[line_pair_index])
                    if line_pair_index < len(step_lines)
                    else ""
                )
                expected_line = (
                    norm_str(expected_lines[line_pair_index])
                    if line_pair_index < len(expected_lines)
                    else ""
                )
                if step_line:
                    current_case.raw_steps.append(
                        CANRawStep(content=step_line, source="step", excel_row=row_idx)
                    )
                if expected_line:
                    current_case.raw_steps.append(
                        CANRawStep(content=expected_line, source="expected", excel_row=row_idx)
                    )

        if current_case is not None:
            cases.append(current_case)
        if skip_events:
            self.skip_events_map[sheet_key] = skip_events
        return cases

    def build_column_mapper(self, header_row: Iterable[object]) -> ColumnMapper | None:
        """构建并校验列映射器。

        参数：
            header_row：表头行单元格值序列。

        返回：
            映射成功返回 `ColumnMapper`；否则返回 `None`。
        """
        mapper = ColumnMapper(
            aliases={
                # 与 XML 列识别保持一致：同时支持「用例ID」和「用例 ID」等写法，
                # 且不再使用过于模糊的短词 "id"，避免误把包含 "id" 的说明行当成表头。
                "case_id": (
                    "用例ID",
                    "用例 id",
                    "用例ID ",
                    "用例 id ",
                    "用例id",
                    "用例编号",
                    "case id",
                    "用例 ID",
                ),
                "group": ("功能模块", "模块", "模块名称"),
                "level": ("等级", "用例等级", "level", "优先级"),
                "case_name": ("用例名称", "用例名", "name", "标题"),
                "step": ("测试步骤", "步骤", "step", "Step"),
                "expected": ("预期结果", "预期", "结果", "expect", "expected"),
                "platform": ("平台", "platform", "测试平台"),
                "model": ("车型", "model", "测试车型"),
                "case_type": ("用例类型", "测试类型", "类型", "case type", "type"),
            },
            # CAN 必填列：用例ID、用例名称、测试步骤、预期结果；其余可选
            required=("case_id", "case_name", "step", "expected"),
        )
        ok = mapper.scan(header_row)
        return mapper if ok else None

    def collect_raw_steps(self, row: tuple, row_idx: int, mapper: ColumnMapper) -> list[CANRawStep]:
        """从一行数据提取步骤与预期文本。

        参数：
            row：当前行值元组。
            row_idx：Excel 行号。
            mapper：列映射器。

        返回：
            `CANRawStep` 列表。
        """
        items: list[CANRawStep] = []
        step_lines: list[str] = []
        expected_lines: list[str] = []
        if mapper.has("step"):
            raw_step = row[mapper.get("step")]
            step_text = str(raw_step) if raw_step is not None else ""
            step_lines = step_text.splitlines() if step_text else []
        if mapper.has("expected"):
            raw_expected = row[mapper.get("expected")]
            expected_text = str(raw_expected) if raw_expected is not None else ""
            expected_lines = expected_text.splitlines() if expected_text else []

        for line_pair_index in range(max(len(step_lines), len(expected_lines))):
            step_line = (
                norm_str(step_lines[line_pair_index])
                if line_pair_index < len(step_lines)
                else ""
            )
            expected_line = (
                norm_str(expected_lines[line_pair_index])
                if line_pair_index < len(expected_lines)
                else ""
            )
            if step_line:
                items.append(CANRawStep(content=step_line, source="step", excel_row=row_idx))
            if expected_line:
                items.append(CANRawStep(content=expected_line, source="expected", excel_row=row_idx))
        return items

    @staticmethod
    def row_value(row: tuple, mapper: ColumnMapper, field: str) -> str:
        """按字段名读取并规范化单元格值。

        参数：
            row：当前行值元组。
            mapper：列映射器。
            field：逻辑字段名。

        返回：
            规范化字符串；字段不存在时为空串。
        """
        if not mapper.has(field):
            return ""
        idx = mapper.get(field)
        if idx >= len(row):
            return ""
        return norm_str(row[idx])

    def missing_header_details(self, header_row: Iterable[object]) -> list[str]:
        """生成表头缺失明细。

        参数：
            header_row：表头行单元格值序列。

        返回：
            缺失列的人可读说明列表。
        """
        mapper = ColumnMapper(
            aliases={
                "case_id": ("用例ID", "用例id", "用例编号"),
                "level": ("等级", "用例等级"),
                "case_name": ("用例名称", "用例名"),
                "step": ("测试步骤", "步骤", "Step", "step"),
                "expected": ("预期结果", "预期", "结果"),
                "case_type": ("用例类型", "测试类型", "类型"),
                "platform": ("平台", "Platform"),
                "model": ("车型", "Model"),
            },
            required=(),
        )
        mapper.scan(header_row)
        label_map = {
            "case_id": "无法识别'用例ID'列",
            "level": "无法识别'等级'列",
            "case_name": "无法识别'用例名称'列",
            "step": "无法识别'测试步骤'列",
            "expected": "无法识别'预期结果'列",
            "case_type": "无法识别'用例类型'列",
            "platform": "无法识别'平台'列",
            "model": "无法识别'车型'列",
        }
        details: list[str] = []
        for field in ("case_id", "level", "case_name", "step", "expected", "case_type", "platform", "model"):
            if not mapper.has(field):
                details.append(label_map[field])
        return details
