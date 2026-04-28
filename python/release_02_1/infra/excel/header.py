#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
表头/列解析公共层（底层）

供 CAN/XML/DIDConfig/DIDInfo/UART/io_mapping 等复用，减少两套列识别标准并存。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple


def normalize_cell_text(item_value: Any) -> str:
    """单元格值规范化：None 转空串，否则去首尾空白。参数: value — 任意值。返回: str。"""
    if item_value is None:
        return ""
    return str(item_value).strip()


def normalize_nfc_text(text: str) -> str:
    """Unicode NFC 规范化。参数: text — 字符串。返回: 规范化后字符串。"""
    if not text:
        return text
    return unicodedata.normalize("NFC", text)


class ColumnMapper:
    """列名到列索引的映射器，按别名匹配表头。"""

    def __init__(
        self,
        *,
        aliases: dict[str, tuple[str, ...]],
        required: tuple[str, ...] = (),
    ) -> None:
        """参数: aliases — 逻辑列名到别名元组的映射；required — 必须匹配到的列名元组。"""
        self.aliases = aliases
        self.required = required
        self.mapping: dict[str, int] = {}

    @staticmethod
    def normalize_header(item_value: object) -> str:
        """表头单元格规范化：去空白、NFC、去空格与下划线、小写。参数: value — 单元格值。返回: str。"""
        normalized_text = normalize_cell_text(item_value)
        normalized_text = normalize_nfc_text(normalized_text)
        normalized_text = re.sub(r"\s+", "", normalized_text.replace("　", " "))
        return normalized_text.replace("_", "").lower()

    def scan(self, header_row: Iterable[object]) -> bool:
        """扫描一行表头，填充 mapping。参数: header_row — 表头行单元格迭代器。返回: 是否所有 required 列均匹配。"""
        self.mapping.clear()
        normalized = [
            self.normalize_header(header_cell_value) for header_cell_value in header_row
        ]
        for field, alias_group in self.aliases.items():
            for alias in alias_group:
                target = self.normalize_header(alias)
                if not target:
                    continue
                for idx, hv in enumerate(normalized):
                    if target in hv:
                        self.mapping[field] = idx
                        break
                if field in self.mapping:
                    break
        return all(item_key in self.mapping for item_key in self.required)

    def has(self, field: str) -> bool:
        """判断逻辑列是否已映射。参数: field — 逻辑列名。返回: bool。"""
        return field in self.mapping

    def get(self, field: str) -> int:
        """取逻辑列对应的列索引。参数: field — 逻辑列名。返回: 列索引。无则抛 KeyError。"""
        if field not in self.mapping:
            raise KeyError(f"列映射不存在: {field}")
        return self.mapping[field]


def normalize_header_cell(item_value: Any) -> str:
    """表头单元格规范化：去空白、去空格与全角空格、小写。参数: value — 单元格值。返回: str。"""
    if item_value is None:
        return ""
    return str(item_value).strip().replace(" ", "").replace("　", "").lower()


def find_header_row_and_col_indices(
    ws: Any,
    column_aliases: Dict[str, List[str]],
    *,
    max_scan_rows: int = 30,
) -> Tuple[int, Dict[str, int], List[str]]:
    """在前 max_scan_rows 行内按列别名定位表头行与列号。
    参数: ws — 工作表；column_aliases — 逻辑列名到别名列表；max_scan_rows — 最大扫描行数。
    返回: (表头行号 1-based, 逻辑列名->列号 1-based, 缺失列显示名列表)。未找到为 (-1, {}, 缺失列)。"""
    required = list(column_aliases.keys())
    if not required:
        return -1, {}, []

    alias_sets: Dict[str, set] = {}
    display_names: Dict[str, str] = {}
    for item_key, aliases in column_aliases.items():
        alias_sets[item_key] = set(
            normalize_header_cell(alias_name)
            for alias_name in aliases
            if alias_name
        )
        display_names[item_key] = aliases[0] if aliases else item_key

    for row_index in range(1, min(ws.max_row, max_scan_rows) + 1):
        found: Dict[str, int] = {}
        for column_index in range(1, ws.max_column + 1):
            try:
                cell_val = ws.cell(row=row_index, column=column_index).value
            except Exception:
                continue
            key_norm = normalize_header_cell(cell_val)
            if not key_norm:
                continue
            for logical_key, norm_set in alias_sets.items():
                if logical_key not in found and key_norm in norm_set:
                    found[logical_key] = column_index
                    break
        if set(found.keys()) >= set(required):
            return row_index, found, []
    return -1, {}, [display_names[required_key] for required_key in required]


class TestCaseHeaderResolver:
    """测试用例表头解析工具集合。

    参数：
        通过类常量维护各业务列别名。

    返回：
        提供静态方法用于定位表头行与关键列索引。
    """
    CASE_ID_ALIASES = ("用例ID", "用例id", "用例编号", "用例 ID")
    GROUP_ALIASES = ("功能模块", "模块", "模块名称")
    LEVEL_ALIASES = ("等级", "用例等级")
    PLATFORM_ALIASES = ("平台", "Platform")
    MODEL_ALIASES = ("车型", "Model")
    CASE_TYPE_ALIASES = ("用例类型", "测试类型", "类型")

    @staticmethod
    def normalize_header_for_match(text: str) -> str:
        """表头/关键字规范化以便匹配：去首尾空白、去所有空格与全角空格、小写。"""
        if not text:
            return ""
        normalized_text = str(text).strip().replace("　", " ")
        normalized_text = re.sub(r"\s+", "", normalized_text)
        return normalized_text.lower()

    @staticmethod
    def find_col_index(header_vals: List[Any], search_keywords: Tuple[str, ...]) -> Optional[int]:
        """在表头行中按关键字找列索引。表头与关键字均做规范化：去空格、小写，支持「Target Version」等带空格表头。
        参数: header_vals — 表头行值列表；search_keywords — 列名别名元组。返回: 0-based 列索引或 None。"""
        if not header_vals:
            return None
        for idx, cell_value in enumerate(header_vals):
            if cell_value is None:
                continue
            header_norm = TestCaseHeaderResolver.normalize_header_for_match(cell_value)
            if not header_norm:
                continue
            for keyword in search_keywords:
                if not keyword:
                    continue
                kw_norm = TestCaseHeaderResolver.normalize_header_for_match(keyword)
                if kw_norm and (kw_norm in header_norm or header_norm in kw_norm):
                    return idx
        return None

    @staticmethod
    def find_case_type_column_index(header_vals: List[Any]) -> Optional[int]:
        """查找用例类型列索引。参数: header_vals — 表头行值列表。返回: 0-based 列索引或 None。"""
        return TestCaseHeaderResolver.find_col_index(header_vals, TestCaseHeaderResolver.CASE_TYPE_ALIASES)

    @staticmethod
    def find_header_row(
        ws: Any,
        *,
        scan_rows: int = 50,
        max_col: int = 50,
        debug_sheet_name: str = "",
    ) -> Tuple[Optional[int], Optional[tuple], bool]:
        """定位用例表表头行（需同时有用例ID与功能模块列）。参数: ws — 工作表；scan_rows/max_col — 扫描范围；debug_sheet_name — 调试用。返回: (行号 1-based, 表头行值元组, 是否含功能模块列)。"""
        best_candidate = None
        try:
            for row_idx, row_vals in enumerate(
                ws.iter_rows(min_row=1, max_row=scan_rows, max_col=max_col, values_only=True),
                start=1,
            ):
                if not row_vals:
                    continue
                case_id_col_idx = TestCaseHeaderResolver.find_col_index(
                    list(row_vals), list(TestCaseHeaderResolver.CASE_ID_ALIASES)
                )
                if case_id_col_idx is None:
                    continue
                group_col_idx = TestCaseHeaderResolver.find_col_index(
                    list(row_vals), list(TestCaseHeaderResolver.GROUP_ALIASES)
                )
                found_group = group_col_idx is not None
                if found_group:
                    return row_idx, tuple(row_vals), True
                if best_candidate is None:
                    best_candidate = (row_idx, tuple(row_vals), False)
        except Exception:
            return None, None, False
        if best_candidate is not None:
            return best_candidate
        return None, None, False


__all__ = [
    "ColumnMapper",
    "find_header_row_and_col_indices",
    "TestCaseHeaderResolver",
]

