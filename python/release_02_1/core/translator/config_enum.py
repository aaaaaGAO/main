#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
configuration.xlsx 枚举翻译（供 CAN/CIN 生成器复用）

功能概览：
  1. 从主配置文件的 [CONFIG_ENUM] 段读取 Inputs，解析 configuration.xlsx 路径及 Sheet 列表。
  2. 打开 configuration.xlsx，按 Name / Values 列构建「Name -> 枚举文本->数值」映射（不做 Name->Path 替换）。
  3. 专用于关键字 Set_Config：对步骤参数 [name, value...] 做枚举翻译（value 文本 -> Values 中左侧数值），name 不替换。
  4. 纯数值、含表达式符号 '><=()' 的 value 不翻译，直接透传；与 IOMAPPING 一致：只要配置了 Inputs 就启用（不检查 Enabled）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from infra.excel.workbook import ExcelService

from services.config_constants import (
    DEFAULT_DOMAIN_LR_REAR,
    OPTION_INPUTS_CANDIDATES,
    get_config_enum_section_candidates,
)
from utils.excel_io import split_input_lines


class ConfigEnumParseError(Exception):
    """configuration.xlsx 枚举翻译失败时抛出，供上层生成注释行或报错。"""


_RE_NUMERIC = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?\s*$")
_RE_ENGLISH_PHRASE = re.compile(r"^[A-Za-z]+(?:\s+[A-Za-z]+)*$")
_EXPR_CHARS = set("><=()")
_COLON_CHARS = (":", "\uFF1A")


def find_colon(text: str, start: int) -> int:
    """在 text[start:] 中查找第一个冒号（半角/全角）位置。参数: text — 字符串；start — 起始下标。返回: 索引，无则 -1。"""
    candidates = [text.find(separator_char, start) for separator_char in _COLON_CHARS]
    candidates = [candidate_pos for candidate_pos in candidates if candidate_pos >= 0]
    return min(candidates) if candidates else -1


def normalize_enum_name_key(text: str) -> str:
    """Name/键规范化：去首尾空白、转小写。参数: text — 原始字符串。返回: str。"""
    return str(text).strip().casefold()


def is_numeric_value(text: str) -> bool:
    """判断是否为十进制数值。参数: text — 待判断字符串。返回: bool。"""
    return bool(text is not None and _RE_NUMERIC.match(str(text)))


def has_expression_chars(text: str) -> bool:
    """判断是否含表达式符号 ><=()，此类值不翻译。参数: text — 待判断字符串。返回: bool。"""
    if text is None:
        return False
    return any((ch in _EXPR_CHARS) for ch in str(text))


def parse_values_cell(values_cell: str) -> Dict[str, str]:
    """解析 Values 单元格为「翻译前(右)->翻译后(左)」映射。参数: values_cell — 单元格字符串。返回: 规范 key -> 左侧值。"""
    if values_cell is None:
        return {}
    text = str(values_cell).strip()
    if not text:
        return {}

    mapping: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        cursor_pos = 0
        line_length = len(line)
        while cursor_pos < line_length:
            colon_index = find_colon(line, cursor_pos)
            if colon_index < 0:
                break
            left = line[cursor_pos:colon_index].strip()
            if not left:
                cursor_pos = colon_index + 1
                continue
            right_start = colon_index + 1
            while right_start < line_length and line[right_start].isspace():
                right_start += 1
            start_right = right_start
            next_pair_pos = None
            next_pair_match = re.search(r"\s+\S+\s*[:\uFF1A]", line[start_right:])
            if next_pair_match:
                next_pair_pos = start_right + next_pair_match.start()
            if next_pair_pos is None:
                right = line[start_right:].strip()
                cursor_pos = line_length
            else:
                right = line[start_right:next_pair_pos].strip()
                cursor_pos = next_pair_pos
                while cursor_pos < line_length and line[cursor_pos].isspace():
                    cursor_pos += 1
            if not right:
                continue
            mapping[normalize_enum_name_key(right)] = left.strip()

    return mapping


@dataclass
class ConfigEnumContext:
    """配置枚举上下文：仅持有 name_to_values，供 Set_Config 步骤参数翻译用。"""

    name_to_values: Dict[str, Dict[str, str]]

    def translate_args(self, args: List[str]) -> List[str]:
        """对 Set_Config 步骤参数做枚举翻译：args[0] 为 Name 不替换，后续 value 按 Values 映射。参数: args — [name, value...]。返回: 翻译后的参数列表。"""
        if not args:
            raise ConfigEnumParseError("参数为空")
        raw_name = str(args[0]).strip()
        if not raw_name:
            raise ConfigEnumParseError("Name 为空")

        name_key = normalize_enum_name_key(raw_name)
        values_map = self.name_to_values.get(name_key)
        values_empty = False
        if not values_map:
            if name_key not in self.name_to_values:
                raise ConfigEnumParseError(f"Name 未找到: {raw_name}")
            values_empty = True
            values_map = {}

        out: List[str] = [raw_name]
        if len(args) == 1:
            return out

        rest_tokens: List[str] = []
        for raw in args[1:]:
            token_text = str(raw).strip()
            if token_text:
                rest_tokens.append(token_text)
        rest_str = " ".join(rest_tokens).strip()
        if rest_str:
            if is_numeric_value(rest_str):
                out.append(rest_str)
                return out
            if has_expression_chars(rest_str):
                out.append(rest_str)
                return out
            if values_empty:
                raise ConfigEnumParseError(f"Values 为空: Name={raw_name}, Value={rest_str}")
            if _RE_ENGLISH_PHRASE.match(rest_str):
                k_all = normalize_enum_name_key(rest_str)
                if k_all in values_map:
                    out.append(values_map[k_all])
                    return out
                raise ConfigEnumParseError(f"Values 未匹配: Name={raw_name}, Value={rest_str}")
            k_all = normalize_enum_name_key(rest_str)
            if k_all in values_map:
                out.append(values_map[k_all])
                return out

        argument_index = 1
        while argument_index < len(args):
            tok = str(args[argument_index]).strip()
            if not tok:
                argument_index += 1
                continue

            if is_numeric_value(tok):
                out.append(tok)
                argument_index += 1
                continue

            if argument_index + 1 < len(args):
                tok2 = str(args[argument_index + 1]).strip()
                two = f"{tok} {tok2}".strip()
                two_key = normalize_enum_name_key(two)
                if two_key in values_map:
                    out.append(values_map[two_key])
                    argument_index += 2
                    continue

            one_key = normalize_enum_name_key(tok)
            if one_key in values_map:
                out.append(values_map[one_key])
                argument_index += 1
                continue

            raise ConfigEnumParseError(f"Values 未匹配: Name={raw_name}, Value={tok}")

        return out


def get_config_enum_inputs_text(config, domain: str) -> str:
    """从配置中按域读取 CONFIG_ENUM 的 Inputs 文本。参数: config — 配置对象；domain — 域（如 LR_REAR，支持全局 CONFIG_ENUM）。返回: Inputs 字符串。"""
    section_candidates = get_config_enum_section_candidates(domain)
    for section in section_candidates:
        if not config.has_section(section):
            continue
        inputs_text = ""
        for option_name in OPTION_INPUTS_CANDIDATES:
            inputs_text = config.get(section, option_name, fallback="")
            if inputs_text:
                break
        inputs_text = inputs_text.strip("\n")
        if inputs_text.strip():
            return inputs_text
    return ""


def load_config_enum_from_config(
    config,
    base_dir: Optional[str] = None,
    config_path: Optional[str] = None,
    domain: str = DEFAULT_DOMAIN_LR_REAR,
) -> Optional[ConfigEnumContext]:
    """从主配置文件的 [CONFIG_ENUM] 段加载 configuration.xlsx，构建 Name->Values 枚举上下文。
    参数: config — 配置对象；base_dir — 工程根目录；config_path — 配置文件路径；domain — 域。
    返回: ConfigEnumContext 或 None（未配置 Inputs 时）。
    """
    inputs_text = get_config_enum_inputs_text(config, domain)
    inputs = split_input_lines(inputs_text)
    if not inputs:
        return None

    if config_path:
        config_dir = os.path.dirname(os.path.abspath(config_path))
    elif base_dir:
        config_dir = base_dir
    else:
        config_dir = os.getcwd()

    name_to_values: Dict[str, Dict[str, str]] = {}

    for rel_path, sheets_str in inputs:
        excel_path = rel_path.strip()
        excel_path_for_check = excel_path.replace("/", os.sep)
        if not os.path.isabs(excel_path_for_check):
            excel_path_for_check = os.path.abspath(os.path.join(config_dir, excel_path_for_check))
        excel_path_for_check = os.path.normpath(excel_path_for_check)

        if not os.path.exists(excel_path_for_check):
            try:
                excel_path_utf8 = excel_path_for_check.encode("utf-8").decode("utf-8")
                if os.path.exists(excel_path_utf8):
                    excel_path_for_check = excel_path_utf8
                else:
                    raise ConfigEnumParseError(f"找不到 configuration.xlsx: {excel_path_for_check}")
            except Exception:
                raise ConfigEnumParseError(f"找不到 configuration.xlsx: {excel_path_for_check}")

        excel_path = excel_path_for_check.replace("\\", "/")

        try:
            wb = ExcelService.open_workbook(
                excel_path,
                data_only=True,
                read_only=True,
            )
        except Exception as error:
            raise ConfigEnumParseError(str(error))

        if not sheets_str or sheets_str.strip() == "*" or sheets_str.strip() == "":
            sheets = list(wb.sheetnames)
        else:
            sheet_candidates = [
                sheet_text.strip()
                for sheet_text in sheets_str.split(",")
                if sheet_text.strip()
            ]
            sheets = [
                sheet_name
                for sheet_name in sheet_candidates
                if sheet_name in wb.sheetnames
            ]
            if not sheets:
                sheets = list(wb.sheetnames)

        for sheet in sheets:
            ws = wb[sheet]
            try:
                header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
            except StopIteration:
                continue
            headers = [str(header_cell).strip() if header_cell is not None else "" for header_cell in header]

            name_idx = None
            values_idx = None
            for header_index, header_text in enumerate(headers):
                if header_text == "Name":
                    name_idx = header_index
                if header_text == "Values":
                    values_idx = header_index
            if name_idx is None or values_idx is None:
                continue

            for row in ws.iter_rows(min_row=2, values_only=True):
                name_cell = row[name_idx] if len(row) > name_idx else None
                values_cell = row[values_idx] if len(row) > values_idx else None

                name_s = str(name_cell).strip() if name_cell is not None else ""
                values_s = str(values_cell).strip() if values_cell is not None else ""

                if not name_s:
                    continue
                enum_map = parse_values_cell(values_s) if values_s else {}
                name_to_values[normalize_enum_name_key(name_s)] = enum_map

    if not name_to_values:
        return None

    return ConfigEnumContext(name_to_values=name_to_values)


class ConfigEnumUtility:
    """Configuration 枚举翻译统一工具类入口。"""

    find_colon = staticmethod(find_colon)
    normalize_enum_name_key = staticmethod(normalize_enum_name_key)
    is_numeric_value = staticmethod(is_numeric_value)
    has_expression_chars = staticmethod(has_expression_chars)
    parse_values_cell = staticmethod(parse_values_cell)
    get_config_enum_inputs_text = staticmethod(get_config_enum_inputs_text)
    load_config_enum_from_config = staticmethod(load_config_enum_from_config)


__all__ = [
    "load_config_enum_from_config",
    "ConfigEnumUtility",
    "ConfigEnumContext",
    "ConfigEnumParseError",
]
