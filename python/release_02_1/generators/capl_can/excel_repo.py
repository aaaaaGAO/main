#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN Excel 仓库：只负责 Excel 读取、过滤、清洗。
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

# 表头/数据扫描列数：与 XML 一致并兼容“大灯高度调节”等表头靠右的表格（用例ID 可能在 50 列之后）
CAN_SHEET_MAX_COL = 80


@dataclass(slots=True)
class RepoStats:
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
    """数据提取专家：读取 Excel，做过滤，聚合为 CANTestCase。"""

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
        self._case_filter = CaseFilter(
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

    def load_cases(self, excel_path: str) -> tuple[dict[tuple[str, str], list[CANTestCase]], dict]:
        # 与 XML 生成脚本保持一致：使用 read_only=False，方便多次 iter_rows，
        # 并让 ExcelService 内部的 _dimensions 重置逻辑生效，避免只读到 A 列。
        wb = ExcelService.open_workbook(excel_path, read_only=False, data_only=True)
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
                cases = self._load_sheet_cases(ws, excel_path, excel_name)
                # 有通过用例或虽无通过但有跳过事件时都加入，便于 CAN 日志与 XML 一致（处理Sheet/跳过逐条）
                if cases or self.skip_events_map.get((excel_path, sheet_name)):
                    out[(excel_path, sheet_name)] = cases
        finally:
            wb.close()
        # 合并 CaseFilter 的过滤统计到 RepoStats
        self.stats.filtered_by_level += self._case_filter.stats.filtered_by_level
        self.stats.filtered_by_platform += self._case_filter.stats.filtered_by_platform
        self.stats.filtered_by_model += self._case_filter.stats.filtered_by_model
        self.stats.filtered_by_type += self._case_filter.stats.filtered_by_type
        self.stats.filtered_by_target_version += self._case_filter.stats.filtered_by_target_version
        return out, self.stats.to_dict()

    def _load_sheet_cases(self, ws, excel_path: str, excel_name: str) -> list[CANTestCase]:
        """
        加载单个 sheet 的用例。

        表头/列识别复用 core.excel_header：
        - 使用 find_testcase_header_row 在前 50 行内找到真正的表头
        - 使用 find_col_index_by_name_in_values / find_case_type_column_index_in_values
          查找用例ID/用例名称/测试步骤/预期结果（必填）、功能模块/等级/平台/车型/用例类型（可选）
        - 缺失任一本表必填列时记入 header_validation_failed 并返回空列表

        数据行读取仍保持 CAN 原有行为：
        - 同一个用例可跨多行填写步骤/预期（case_id 只出现在第一行）
        - 使用 CANTestCase.raw_steps 收集 step/expected 列的多行内容
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
                filtered, reason = self._case_filter.is_filtered(
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

            for i in range(max(len(step_lines), len(expected_lines))):
                step_line = norm_str(step_lines[i]) if i < len(step_lines) else ""
                expected_line = norm_str(expected_lines[i]) if i < len(expected_lines) else ""
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

    def _build_column_mapper(self, header_row: Iterable[object]) -> ColumnMapper | None:
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

    def _collect_raw_steps(self, row: tuple, row_idx: int, mapper: ColumnMapper) -> list[CANRawStep]:
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

        for i in range(max(len(step_lines), len(expected_lines))):
            step_line = norm_str(step_lines[i]) if i < len(step_lines) else ""
            expected_line = norm_str(expected_lines[i]) if i < len(expected_lines) else ""
            if step_line:
                items.append(CANRawStep(content=step_line, source="step", excel_row=row_idx))
            if expected_line:
                items.append(CANRawStep(content=expected_line, source="expected", excel_row=row_idx))
        return items

    @staticmethod
    def _row_value(row: tuple, mapper: ColumnMapper, field: str) -> str:
        if not mapper.has(field):
            return ""
        idx = mapper.get(field)
        if idx >= len(row):
            return ""
        return norm_str(row[idx])

    def _missing_header_details(self, header_row: Iterable[object]) -> list[str]:
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
