#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一 Excel 读写封装（供所有生成器复用）。

本模块聚合字符串处理与输入解析能力：
- `StringUtility`：字符串规范化、NFC、用例 ID 清洗等；
- `ExcelUtility`：Inputs 文本解析、前端 sheet 过滤字符串解析。
同时统一导出 `ExcelService`、`merged_cell_value`、`ColumnMapper`。
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import unicodedata
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from infra.config.input_parser import split_input_lines as core_split_input_lines
from infra.excel.header import ColumnMapper, normalize_cell_text as common_normalize_cell_text
from infra.excel.workbook import ExcelService, merged_cell_value

Style = None  # type: ignore[assignment]
lazy_pinyin = None  # type: ignore[assignment]
if importlib.util.find_spec("pypinyin") is not None:
    pypinyin_module = importlib.import_module("pypinyin")
    Style = getattr(pypinyin_module, "Style", None)  # type: ignore[assignment]
    lazy_pinyin = getattr(pypinyin_module, "lazy_pinyin", None)  # type: ignore[assignment]

# sanitize_case_id 用到的清洗规则
_RE_SYS_ID = re.compile(r"(SYS-[^\r\n]+)")
_TRAILING_PUNCT = " \t,，。.;；:：!！?？、/\\@#￥$%^&*+=~`|<>《》“”\"'）)】]"
_RE_ILLEGAL = re.compile(r"[\s\u3000\uFF08\uFF09\u3010\u3011（）【】]+")
_RE_HAS_CJK = re.compile(r"[\u4e00-\u9fff]")
_RE_CAPL_SAFE = re.compile(r"[^a-zA-Z0-9_\-]")


class StringUtility:
    """字符串处理统一工具类。"""

    @staticmethod
    def norm_str(raw_value) -> str:
        """安全地将任意值转为去首尾空白字符串。

        参数：
            raw_value：任意值，可为 None/数字/字符串。

        返回：
            str：None 返回空串，其余转字符串后去首尾空白。
        """
        return common_normalize_cell_text(raw_value)

    @staticmethod
    def nfc_normalize(raw_text: str) -> str:
        """对字符串做 Unicode NFC 归一化。

        参数：
            raw_text：原始字符串。

        返回：
            str：归一化后的字符串；空值原样返回。
        """
        if not raw_text:
            return raw_text
        return unicodedata.normalize("NFC", raw_text)

    @staticmethod
    def chinese_to_pinyin(text: str) -> str:
        """将字符串中的中文转为拼音，非中文字符原样保留。"""
        if lazy_pinyin is None or Style is None:
            return text
        result: list[str] = []
        for char in text:
            if "\u4e00" <= char <= "\u9fff":
                pinyin_items = lazy_pinyin(char, style=Style.NORMAL)
                result.append(pinyin_items[0] if pinyin_items else char)
            else:
                result.append(char)
        return "".join(result)

    @staticmethod
    def sanitize_case_id(raw: Any) -> Tuple[str, bool, str]:
        """清洗用例 ID：非法字符、中文转拼音、SYS- 提取等。"""
        if raw is None:
            return ("", False, "empty")

        raw_str = str(raw).strip()
        if not raw_str:
            return ("", False, "empty")

        sys_id_match = _RE_SYS_ID.search(raw_str)
        candidate = sys_id_match.group(1).strip() if sys_id_match else raw_str
        cleaned = _RE_ILLEGAL.sub("", candidate)
        cleaned = cleaned.rstrip(_TRAILING_PUNCT).strip()

        had_cjk = bool(_RE_HAS_CJK.search(cleaned))
        if had_cjk:
            cleaned = StringUtility.chinese_to_pinyin(cleaned)
            cleaned = cleaned.rstrip(_TRAILING_PUNCT).strip()

        cleaned = _RE_CAPL_SAFE.sub("", cleaned)
        if had_cjk:
            if cleaned:
                return (cleaned, True, "chinese_to_pinyin")
            return (cleaned, True, "chinese_to_pinyin_strip_all")

        changed = cleaned != raw_str
        if not changed:
            return (cleaned, False, "ok")
        if not cleaned:
            return (cleaned, True, "strip_all")
        if sys_id_match and candidate != raw_str:
            return (cleaned, True, "extract_SYS_pattern")
        if _RE_ILLEGAL.search(candidate) or " " in candidate:
            return (cleaned, True, "remove_spaces_or_illegal_chars")
        return (cleaned, True, "strip_trailing_punct")


class ExcelUtility:
    """Excel 输入与 Sheet 过滤工具类。"""

    @staticmethod
    def split_input_lines(text: str) -> List[Tuple[str, str]]:
        """解析 Inputs 配置多行格式（path | sheet1,sheet2）。

        参数：
            text：配置文本。

        返回：
            list[tuple[str, str]]：每项为 `(path, sheets)`。
        """
        return core_split_input_lines(text)

    @staticmethod
    def parse_selected_sheets(filter_str: Optional[str]) -> Optional[Dict[str, Set[str]]]:
        """解析前端勾选传递的 `table|sheet` 列表。

        参数：
            filter_str：形如 `table1|sheet1,table1|sheet2` 的字符串；空值表示不过滤。

        返回：
            dict[str, set[str]] | None：`{table_key_lower: {sheet_lower...}}`；空时返回 None。
        """
        filter_map: Dict[str, Set[str]] = {}
        if not filter_str or not str(filter_str).strip():
            return None
        for selected_item in str(filter_str).split(","):
            if "|" not in selected_item:
                continue
            table, sheet = selected_item.split("|", 1)
            table_key = os.path.basename(str(table).strip()).lower()
            sheet_val = str(sheet).strip().lower()
            if not table_key or not sheet_val:
                continue
            filter_map.setdefault(table_key, set()).add(sheet_val)
        return filter_map if filter_map else None

# ExcelService、merged_cell_value 已自 infra.excel.workbook 导入并统一导出
