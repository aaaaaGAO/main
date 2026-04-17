#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IO Mapping 解析与替换（供 CAN/CIN 生成器复用）

功能概览：
  1. 从当前主配置文件的 [IOMAPPING] 段读取 Inputs，解析「Excel 路径 | Sheet 列表」。
  2. 打开一个或多个 IO_mapping Excel，支持指定 sheet 或全部 sheet（*）。
  3. 表头定位 Name/Path/Values；Name/Path/Values 均使用当前行单元格原始值，不做向下填充（不受合并单元格影响）。
  4. 将 Name -> Path 做替换；将 Values 中的「翻译前(右侧)」->「翻译后(左侧)」做枚举翻译（大小写不敏感）。
  5. 支持 J_DI*LS 特殊规则：二值枚举取反、分组分号、多参数透传等。

执行顺序（load_io_mapping_from_config 一次调用的步骤）：
  ① 读 config 的 [IOMAPPING].Inputs，解析为 (excel_path, sheets) 列表。
  ② 初始化日志（IO_Mapping.log），确定配置目录用于解析相对路径。
  ③ 对每个 Excel：校验路径与格式、打开工作簿；对每个 Sheet 定位表头（Name/Path/Values）。
  ④ 逐行读取 Name/Path/Values，填充 name_to_path、name_to_values；同表内冲突仅告警、保留首次。
  ⑤ 返回 IOMappingContext(name_to_path, name_to_values)，供上层对步骤参数调用 transform_args 做替换与枚举翻译。

代码阅读顺序（本文件已按此顺序组织，从上往下读即可）：
  - ① 常量与异常：PROGRESS_LEVEL、正则/集合常量、IOMappingParseError。
  - ② 读配置相关：get_base_dir、get_log_level_from_config、split_input_lines（来自 utils）。
  - ③ 日志相关：IOProgressFormatter、setup_logging、emit_log_message。
  - ④ 表头与列定位：normalize_header_text、find_header_row_and_indices。
  - ⑤ 字符串/枚举工具：find_colon、is_numeric_value、normalize_name_key、normalize_enum_key、has_expression_chars。
  - ⑥ Values 解析：parse_values_cell。
  - ⑦ 上下文类：IOMappingContext（maybe_invert_ls_enum、is_j_di_ls、process_inverted_token、transform_args）。
  - ⑧ 主加载入口：load_io_mapping_from_config。

配置建议（主配置文件 `Configuration.ini`）：
  [IOMAPPING]
  Inputs =
    input/xxx.xlsx | *
    input/yyy.xlsx | Sheet1,Sheet2
  注：不再检查 Enabled；只要配置了 Inputs 即启用。
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional

from infra.excel.workbook import ExcelService

from core.caseid_log_dedup import DedupOnceFilter
from core.log_run_context import ensure_run_log_dirs
from services.config_constants import (
    DEFAULT_DOMAIN_LR_REAR,
    OPTION_INPUTS_CANDIDATES,
    get_io_mapping_section_candidates,
)
from utils.excel_io import split_input_lines
from utils.logger import (
    ExcludeProgressFilter as LoggerExcludeProgressFilter,
    PROGRESS_LEVEL as LoggerProgressLevel,
    ProgressOnlyFilter as LoggerProgressOnlyFilter,
    get_log_level_from_config,
)
from infra.filesystem import get_base_dir

# ==================== ① 常量与异常 ====================

# 正常进度日志等级：不受 log_level_min 限制，始终写入（日志已启用、处理 Excel/sheet 等）
PROGRESS_LEVEL = LoggerProgressLevel

_ProgressOnlyFilter = LoggerProgressOnlyFilter
_ExcludeProgressFilter = LoggerExcludeProgressFilter

# 十进制数值、十六进制(0x/0X)、表达式符号、Values 冒号
_RE_NUMERIC = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?\s*$")
_RE_HEX = re.compile(r"^\s*0[xX][0-9a-fA-F]+\s*$")
_EXPR_CHARS = set("><=()")
_COLON_CHARS = (":", "\uFF1A")  # 半角 : 、全角 ：

# J_DI*LS 多值枚举告警去重（同一 Name 只打一次）
LS_INVERT_WARNED_NAMES: set[str] = set()
ACTIVE_LOGGER: Optional[logging.Logger] = None


class IOMappingParseError(Exception):
    """当 IO mapping 替换/翻译失败时抛出，供上层生成注释行或报错。"""


# ==================== ② 读配置相关 ====================

# 使用 utils.path_utils.get_base_dir 替代 _default_base_dir
# 使用 utils.logger.get_log_level_from_config 替代 _get_log_level_from_config
# 使用 utils.excel_io.split_input_lines 替代 _split_mapping_input_lines


# ==================== ③ 日志相关 ====================


class IOProgressFormatter(logging.Formatter):
    """进度类消息只输出时间+消息，不显示等级名。"""

    def format(self, record: logging.LogRecord) -> str:
        if record.levelno == PROGRESS_LEVEL:
            old_name = record.levelname
            record.levelname = " "
            formatted_text = super().format(record)
            record.levelname = old_name
            return (
                formatted_text.replace("  ", " ", 1)
                if "  " in formatted_text
                else formatted_text
            )
        return super().format(record)


def setup_logging(base_dir: Optional[str], section: Optional[str] = None) -> logging.Logger:
    """
    初始化 IO_Mapping.log（写入 <base_dir>/log/，按大小轮转）。
    形参：base_dir - 传入工程根目录或 None（None 时用 get_base_dir()）；section - 从 Configuration 的哪一节读 log_level_min（如 LR_REAR/DTC），None 时用 get_run_domain()。
    返回：logging.Logger。支持 log_level_min；进度类消息始终写入。
    """
    global ACTIVE_LOGGER
    base_dir = base_dir or get_base_dir()
    user_level = get_log_level_from_config(base_dir, section=section)

    run_dirs = ensure_run_log_dirs(base_dir)
    log_dir = run_dirs.parse_dir
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "IO_Mapping.log")

    if ACTIVE_LOGGER is not None:
        desired = os.path.abspath(log_path)
        has_correct = any(
            isinstance(h, logging.FileHandler)
            and os.path.abspath(getattr(h, "baseFilename", "")) == desired
            for h in ACTIVE_LOGGER.handlers
        )
        if has_correct:
            # 复用已有 logger 时仍按当前配置刷新日志级别（界面修改 error 后再次运行可生效）
            user_level_new = get_log_level_from_config(base_dir, section=section)
            for h in ACTIVE_LOGGER.handlers:
                if (
                    isinstance(h, logging.FileHandler)
                    and os.path.abspath(getattr(h, "baseFilename", "")) == desired
                    and any(
                        isinstance(filter_item, _ExcludeProgressFilter)
                        for filter_item in (h.filters if hasattr(h, "filters") else [])
                    )
                ):
                    h.setLevel(user_level_new)
                    break
            return ACTIVE_LOGGER
        for h in ACTIVE_LOGGER.handlers[:]:
            try:
                h.close()
            except Exception:
                pass
            ACTIVE_LOGGER.removeHandler(h)

    logger = logging.getLogger("io_mapping")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if not logger.handlers:
        fmt = IOProgressFormatter("%(asctime)s %(levelname)s %(message)s")
        dedup_filter = DedupOnceFilter()
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=20,
            encoding="utf-8",
        )
        fh.addFilter(_ExcludeProgressFilter())
        fh.addFilter(dedup_filter)
        fh.setLevel(user_level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        fh_progress = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=20,
            encoding="utf-8",
        )
        fh_progress.addFilter(_ProgressOnlyFilter())
        fh_progress.addFilter(dedup_filter)
        fh_progress.setLevel(PROGRESS_LEVEL)
        fh_progress.setFormatter(fmt)
        logger.addHandler(fh_progress)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        ch.addFilter(dedup_filter)
        logger.addHandler(ch)

    ACTIVE_LOGGER = logger
    ACTIVE_LOGGER.log(PROGRESS_LEVEL, "[io_mapping] 日志已启用：%s", log_path)
    return logger


def emit_log_message(level: int, msg: str) -> None:
    """
    写日志或 fallback 到 print。
    形参：level - 传入 logging 等级（如 logging.ERROR）；msg - 传入日志消息字符串。
    返回：无。
    """
    if ACTIVE_LOGGER is not None:
        ACTIVE_LOGGER.log(level, msg)
    else:
        print(msg)


# ==================== ④ 表头与列定位 ====================


def normalize_header_text(header_value) -> str:
    """
    表头规范化：去首尾空白、移除空格、转小写，用于匹配 Name/Path/Values。
    形参：v - 传入表头单元格原始值（可为 None）。
    返回：str。空表头为 ""。
    """
    if header_value is None:
        return ""
    return str(header_value).strip().replace(" ", "").casefold()


def find_header_row_and_indices(worksheet, *, max_scan_rows: int = 30) -> tuple[int, dict[str, int], list[str]]:
    """
    在工作表前若干行中定位同时包含 Name/Path/Values 的表头行。
    形参：worksheet - 传入 openpyxl 的 Worksheet 对象；max_scan_rows - 传入最大扫描行数，默认 30。
    返回：(header_row, col_map, missing)。
      - header_row: 表头行号（1-based），找不到为 -1。
      - col_map: {"name": idx, "path": idx, "values": idx}，idx 为 0-based 列索引。
      - missing: 缺失的必须列名列表（如 ["Name", "Path"]）。
    """
    required = {"name": "Name", "path": "Path", "values": "Values"}
    seen_headers: set[str] = set()
    max_scan_row_index = (
        min(getattr(worksheet, "max_row", 0) or 0, max_scan_rows) or max_scan_rows
    )
    for row_index, row_values in enumerate(
        worksheet.iter_rows(min_row=1, max_row=max_scan_row_index, values_only=True),
        start=1,
    ):
        found_columns: dict[str, int] = {}
        for column_index, cell_value in enumerate(row_values):
            normalized_key = normalize_header_text(cell_value)
            if not normalized_key or normalized_key not in required:
                continue
            seen_headers.add(normalized_key)
            if normalized_key not in found_columns:
                found_columns[normalized_key] = column_index
        if all(required_key in found_columns for required_key in required.keys()):
            return row_index, {
                "name": found_columns["name"],
                "path": found_columns["path"],
                "values": found_columns["values"],
            }, []
    missing = [required[required_key] for required_key in required.keys() if required_key not in seen_headers]
    return -1, {}, missing


# ==================== ⑤ 字符串/枚举工具 ====================


def find_colon(text_line: str, start: int) -> int:
    """
    返回 text_line[start:] 中第一个冒号（英文或中文）的位置。
    形参：text_line - 传入待查字符串；start - 传入起始下标。
    返回：int。位置索引，无则 -1。
    """
    candidates = [text_line.find(char, start) for char in _COLON_CHARS]
    candidates = [found_at for found_at in candidates if found_at >= 0]
    return min(candidates) if candidates else -1


def is_numeric_value(value_text: str) -> bool:
    """
    判断字符串是否为数值（十进制或十六进制如 0x1）。
    形参：s - 传入待判断字符串（可为 None）。
    返回：bool。
    """
    if value_text is None:
        return False
    normalized_text = str(value_text).strip()
    return bool(_RE_NUMERIC.match(normalized_text) or _RE_HEX.match(normalized_text))


def normalize_name_key(name_text: str) -> str:
    """
    Name/Path 等键的规范化：去首尾空白、转小写，用于字典查找。
    形参：s - 传入原始键字符串。
    返回：str。
    """
    return str(name_text).strip().casefold()


def normalize_enum_key(enum_text: str) -> str:
    """
    Values/枚举专用 key 规范化：去首尾空白、折叠内部空白、移除不可见字符、转小写。
    形参：s - 传入枚举显示值（如 "AUTO DOWN"）。
    返回：str。用于避免复制粘贴导致的匹配失败。
    """
    if enum_text is None:
        return ""
    normalized = str(enum_text).strip()
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.casefold()


def has_expression_chars(value_text: str) -> bool:
    """
    判断是否包含表达式符号 ><=()，此类字符串不做枚举翻译、直接透传。
    形参：s - 传入待判断字符串（可为 None）。
    返回：bool。
    """
    if value_text is None:
        return False
    return any((ch in _EXPR_CHARS) for ch in str(value_text))


# ==================== ⑥ Values 解析 ====================


def parse_values_cell(values_cell: str) -> Dict[str, str]:
    """
    解析 Values 单元格，得到 翻译前(右侧) -> 翻译后(左侧) 的映射。
    支持多行、一行多对（如 1:ON 0:OFF）、数值 key 紧挨（如 0:AUTO DOWN2.2:AUTO UP）的强容错切分。
    形参：values_cell - 传入 Values 列单元格的原始字符串（可为 None）。
    返回：Dict[str, str]。key 为 normalize_enum_key(翻译前)，value 为翻译后（如 "1"、"0"）。
    """
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

        numeric_pair_pattern = re.compile(r"[-+]?\d+(?:\.\d+)?\s*[:\uFF1A]")
        numeric_pair_matches = list(numeric_pair_pattern.finditer(line))
        if numeric_pair_matches:
            for match_index, numeric_pair_match in enumerate(numeric_pair_matches):
                colon_pos = numeric_pair_match.end() - 1
                if match_index == 0:
                    pair_start = 0
                else:
                    probe_index = numeric_pair_match.start() - 1
                    while probe_index >= 0 and not line[probe_index].isalpha():
                        probe_index -= 1
                    if probe_index < 0:
                        pair_start = 0
                    else:
                        probe_index += 1
                        while probe_index < len(line) and line[probe_index].isspace():
                            probe_index += 1
                        pair_start = probe_index
                left = line[pair_start:colon_pos].strip()
                value_start = numeric_pair_match.end()
                value_end = (
                    numeric_pair_matches[match_index + 1].start()
                    if match_index + 1 < len(numeric_pair_matches)
                    else len(line)
                )
                right = line[value_start:value_end].strip()
                if not left or not right:
                    continue
                mapping[normalize_enum_key(right)] = left
            continue

        current_index = 0
        line_length = len(line)
        while current_index < line_length:
            colon_index = find_colon(line, current_index)
            if colon_index < 0:
                break
            left = line[current_index:colon_index].strip()
            if not left:
                current_index = colon_index + 1
                continue
            after_colon_index = colon_index + 1
            while after_colon_index < line_length and line[after_colon_index].isspace():
                after_colon_index += 1
            start_right = after_colon_index
            pair_boundary_match = re.search(r"\s+\S+\s*[:\uFF1A]", line[start_right:])
            next_pair_pos = start_right + pair_boundary_match.start() if pair_boundary_match else None
            if next_pair_pos is None:
                right = line[start_right:].strip()
                current_index = line_length
            else:
                right = line[start_right:next_pair_pos].strip()
                current_index = next_pair_pos
                while current_index < line_length and line[current_index].isspace():
                    current_index += 1
            if not right:
                continue
            mapping[normalize_enum_key(right)] = left.strip()
    return mapping


# ==================== ⑦ 上下文类 ====================


@dataclass
class IOMappingContext:
    """
    加载后的 IO mapping 上下文，供 CAN/CIN 步骤里对参数做 Name->Path 替换与 Values 枚举翻译。
    属性：name_to_path - Name(规范键)->Path；name_to_values - Name(规范键)->{枚举key->翻译后值}。
    """

    name_to_path: Dict[str, str]
    name_to_values: Dict[str, Dict[str, str]]

    @staticmethod
    def maybe_invert_ls_enum(name: str, value_token: str, values_map: Dict[str, str]) -> str:
        """
        J_DI*LS 二值枚举取反：若 Name 为 J_DI*LS 且 Values 仅 2 个枚举，则返回「另一个」枚举 key。
        形参：name - 传入当前 Name（如 J_DI_RDoorInnerSw_LS）；value_token - 传入用户写的枚举值；values_map - 传入该 Name 的 Values 映射（norm_enum_key -> 翻译后）。
        返回：str。若无需取反或非二值，返回原 value_token；否则返回另一个枚举的 key。
        """
        if not name or not value_token or not values_map:
            return value_token
        upper_name = str(name).strip().upper()
        if not (upper_name.startswith("J_DI") and upper_name.endswith("LS")):
            return value_token
        token_text = str(value_token).strip()
        if not token_text:
            return value_token
        keys = list(values_map.keys())
        current_key = normalize_enum_key(token_text)
        if len(keys) != 2:
            if len(keys) > 2 and current_key in values_map:
                if upper_name not in LS_INVERT_WARNED_NAMES:
                    LS_INVERT_WARNED_NAMES.add(upper_name)
                    enum_preview = ", ".join(sorted(keys)[:20])
                    more = "" if len(keys) <= 20 else f" ...(+{len(keys)-20})"
                    emit_log_message(
                        logging.ERROR,
                        "[io_mapping][ERROR] J_DI*LS 枚举反转仅支持 2 值，但该 Name 的 Values 有 "
                        f"{len(keys)} 值：name={name!r} enums=[{enum_preview}{more}] 当前输入={value_token!r}（本次将不反转）",
                    )
            return value_token
        if current_key not in values_map:
            return value_token
        return keys[0] if keys[1] == current_key else keys[1]

    @staticmethod
    def is_j_di_ls(name: str) -> bool:
        """
        判断 Name 是否以 J_DI 开头且以 LS 结尾。
        形参：name - 传入 Name 字符串。
        返回：bool。
        """
        if not name:
            return False
        upper_name = str(name).strip().upper()
        return upper_name.startswith("J_DI") and upper_name.endswith("LS")

    def process_inverted_token(
        self,
        raw_name: str,
        value_token: str,
        values_map: Dict[str, str],
    ) -> str:
        """
        统一处理 J_DI*LS 的取反：数字 0/1 互换；枚举经 maybe_invert_ls_enum 后按 values_map 翻译；表达式透传。
        形参：raw_name - 传入原始 Name；value_token - 传入当前 token；values_map - 传入该 Name 的 Values 映射。
        返回：str。翻译后或取反后的值。失败抛 IOMappingParseError。
        """
        if value_token is None:
            return value_token
        token = str(value_token).strip()
        if not token:
            return token
        if has_expression_chars(token):
            return token
        if is_numeric_value(token):
            try:
                num_val = int(token, 16) if _RE_HEX.match(token) else int(float(token))
            except (ValueError, OverflowError):
                return token
            if num_val == 0:
                return "1"
            if num_val == 1:
                return "0"
            return token
        if not values_map:
            raise IOMappingParseError(f"Values 为空，无法翻译: {token}")
        phrase2 = self.maybe_invert_ls_enum(raw_name, token, values_map)
        enum_key = normalize_enum_key(phrase2)
        if enum_key in values_map:
            return values_map[enum_key]
        raise IOMappingParseError(
            f"J_DI*LS 名称 {raw_name!r} 的值必须是 0、1 或 Values 中的枚举值，"
            f"但收到 {token!r}。Values 中的有效枚举值: {list(values_map.keys())}"
        )

    def transform_args(self, args: List[str]) -> List[str]:
        """
        对关键字后的 args 做 IO mapping：args[0] 替换为 Path；第一个 value 做 Values 翻译（支持多词枚举、J_DI*LS 取反与分组）。
        形参：args - 传入步骤参数列表，args[0] 为以 J_ 开头的 Name，后续为 value 及可选单位等。
        返回：List[str]。首元素为 Path，其余为翻译后 value + 透传的后续 token。失败抛 IOMappingParseError。
        """
        if not args:
            raise IOMappingParseError("参数为空")
        raw_name = str(args[0]).strip()
        if not raw_name.upper().startswith("J_"):
            return args
        name_key = normalize_name_key(raw_name)
        if name_key not in self.name_to_path and name_key not in self.name_to_values:
            raise IOMappingParseError(f"Name 未找到: {raw_name}")
        path = self.name_to_path.get(name_key, "")
        if not path:
            raise IOMappingParseError(f"Path 为空: {raw_name}")
        values_map = self.name_to_values.get(name_key, {})
        transformed_args: List[str] = [path]
        if len(args) == 1:
            return transformed_args
        rest_tokens: List[str] = [
            str(raw_token).strip()
            for raw_token in args[1:]
            if str(raw_token).strip()
        ]
        if not rest_tokens:
            return transformed_args
        if not values_map:
            first_token = rest_tokens[0]
            if is_numeric_value(first_token) or has_expression_chars(first_token):
                transformed_args.extend(rest_tokens)
                return transformed_args
            raise IOMappingParseError(f"Values 为空: Name={raw_name}, Value={' '.join(rest_tokens)}")

        if self.is_j_di_ls(raw_name):
            rest_str = " ".join(rest_tokens).strip()
            if not rest_str:
                return transformed_args
            group_strs = re.split(r"[;；]", rest_str)
            new_groups: List[str] = []
            for group_text in group_strs:
                group_text = group_text.strip()
                if not group_text:
                    continue
                seg_tokens = group_text.split()
                if len(seg_tokens) == 1:
                    new_groups.append(self.process_inverted_token(raw_name, seg_tokens[0], values_map))
                else:
                    inverted_value = self.process_inverted_token(raw_name, seg_tokens[1], values_map)
                    new_groups.append(" ".join([seg_tokens[0], inverted_value] + seg_tokens[2:]))
            new_rest_str = ";".join(new_groups)
            transformed_args.extend([token for token in new_rest_str.split() if token])
            return transformed_args

        first_token = rest_tokens[0]
        if has_expression_chars(first_token):
            transformed_args.extend(rest_tokens)
            return transformed_args
        if is_numeric_value(first_token):
            if self.is_j_di_ls(raw_name):
                try:
                    num_val = (
                        int(str(first_token).strip(), 16)
                        if _RE_HEX.match(str(first_token).strip())
                        else int(float(first_token))
                    )
                    if num_val == 0:
                        transformed_args.append("1")
                        transformed_args.extend(rest_tokens[1:])
                        return transformed_args
                    if num_val == 1:
                        transformed_args.append("0")
                        transformed_args.extend(rest_tokens[1:])
                        return transformed_args
                    raise IOMappingParseError(
                        f"J_DI*LS 名称 {raw_name!r} 的值必须是 0、1 或 Values 中的枚举值，但收到数字 {num_val!r}。"
                    )
                except (ValueError, OverflowError):
                    pass
            transformed_args.extend(rest_tokens)
            return transformed_args

        max_phrase_token_count = 0
        for candidate_token in rest_tokens:
            if not candidate_token:
                continue
            if is_numeric_value(candidate_token) or has_expression_chars(candidate_token):
                break
            max_phrase_token_count += 1
        if max_phrase_token_count <= 0:
            transformed_args.extend(rest_tokens)
            return transformed_args
        matched = False
        for token_count in range(max_phrase_token_count, 0, -1):
            phrase = " ".join(rest_tokens[:token_count]).strip()
            if not phrase:
                continue
            phrase2 = self.maybe_invert_ls_enum(raw_name, phrase, values_map)
            enum_key = normalize_enum_key(phrase2)
            if enum_key in values_map:
                transformed_args.append(values_map[enum_key])
                transformed_args.extend(rest_tokens[token_count:])
                matched = True
                break
        if not matched:
            if self.is_j_di_ls(raw_name):
                raise IOMappingParseError(
                    f"J_DI*LS 名称 {raw_name!r} 的值必须是 0、1 或 Values 中的枚举值，但收到 {first_token!r}。有效枚举: {list(values_map.keys())}"
                )
            raise IOMappingParseError(f"Values 未匹配: {first_token}")
        return transformed_args


# ==================== ⑧ 主加载入口 ====================


def get_io_mapping_inputs_text(config, domain: str) -> str:
    """从配置中按域读取 [IOMAPPING] 的 Inputs 文本。参数: config — 配置对象；domain — 域（LR_REAR 兼容全局 IOMAPPING）。返回: Inputs 字符串。"""
    section_candidates = get_io_mapping_section_candidates(domain)
    for section in section_candidates:
        if not config.has_section(section):
            continue
        inputs_text = ""
        for option_name in OPTION_INPUTS_CANDIDATES:
            inputs_text = config.get(section, option_name, fallback="")
            if inputs_text:
                break
        if inputs_text and str(inputs_text).strip():
            return str(inputs_text)
    return ""


def load_io_mapping_from_config(
    config,
    base_dir: Optional[str] = None,
    config_path: Optional[str] = None,
    domain: str = DEFAULT_DOMAIN_LR_REAR,
) -> Optional[IOMappingContext]:
    """
    从 config 的 [IOMAPPING] 段加载 IO mapping；未配置 Inputs 则返回 None。
    形参：
      config - 传入 ConfigParser 对象（已读入当前主配置文件）。
      base_dir - 传入工程根目录，用于日志与相对路径；可选。
      config_path - 传入配置文件路径，用于解析 Inputs 中相对路径的基准目录；可选，优先于 base_dir。
    返回：IOMappingContext 或 None。有 Inputs 时返回上下文，供 transform_args 使用。
    """
    inputs_text = get_io_mapping_inputs_text(config, domain)
    input_lines = split_input_lines(inputs_text)
    if not input_lines:
        return None

    # 日志需从工程根目录读取当前主配置的 log_level_min，此处传入工程根
    if base_dir:
        logger_base = base_dir
    elif config_path:
        config_dir = os.path.dirname(os.path.abspath(config_path))
        # 若 config_path 在 config/ 子目录下，工程根为其父目录
        if os.path.basename(config_dir) == "config":
            logger_base = os.path.dirname(config_dir)
        else:
            logger_base = config_dir
    else:
        logger_base = None
    logger = setup_logging(logger_base, section=domain)
    config_dir = (
        os.path.dirname(os.path.abspath(config_path))
        if config_path
        else (base_dir or os.getcwd())
    )

    name_to_path: Dict[str, str] = {}
    name_to_values: Dict[str, Dict[str, str]] = {}

    for excel_path_raw, sheets_raw in input_lines:
        excel_path = excel_path_raw.strip()
        excel_path_for_check = excel_path.replace("/", os.sep)
        if not os.path.isabs(excel_path_for_check):
            excel_path_for_check = os.path.abspath(
                os.path.join(config_dir, excel_path_for_check)
            )
        excel_path_for_check = os.path.normpath(excel_path_for_check)
        if not os.path.exists(excel_path_for_check):
            try:
                excel_path_utf8 = excel_path_for_check.encode("utf-8").decode("utf-8")
                if os.path.exists(excel_path_utf8):
                    excel_path_for_check = excel_path_utf8
                else:
                    raise FileNotFoundError(
                        f"找不到 IO_mapping Excel 文件: {excel_path_for_check}"
                    )
            except Exception:
                raise FileNotFoundError(f"找不到 IO_mapping Excel 文件: {excel_path_for_check}")
        if not os.path.isfile(excel_path_for_check):
            raise IOMappingParseError(f"路径不是文件: {excel_path_for_check}")
        if not excel_path_for_check.lower().endswith((".xlsx", ".xlsm")):
            raise IOMappingParseError(
                f"文件不是有效的 Excel 文件（.xlsx 或 .xlsm）: {excel_path_for_check}"
            )

        excel_path_to_open = excel_path_for_check
        try:
            with open(excel_path_to_open, "rb") as excel_binary_file:
                if excel_binary_file.read(4) != b"PK\x03\x04":
                    raise IOMappingParseError(
                        f"文件不是有效的 Excel（缺少 ZIP 文件头）: {excel_path_to_open}"
                    )
            workbook = ExcelService.open_workbook(
                excel_path_to_open,
                data_only=True,
                read_only=False,
            )
        except FileNotFoundError:
            raise IOMappingParseError(f"找不到文件: {excel_path_to_open}")
        except PermissionError:
            raise IOMappingParseError(f"没有权限读取: {excel_path_to_open}")
        except Exception as error:
            error_message = str(error).lower()
            if (
                "decompressing" in error_message
                or "incorrect header" in error_message
                or "badzipfile" in error_message
                or "not a zip file" in error_message
            ):
                raise IOMappingParseError(
                    "IO Mapping Excel 格式错误或文件已损坏。\n"
                    f"文件: {excel_path_to_open}\n"
                    "说明: .xlsx 本质是压缩包结构，出现该错误通常表示文件后缀与真实格式不一致，或文件内容已损坏。\n"
                    "建议: 请用 Excel 打开后另存为新的 .xlsx，再重新导入。"
                )
            raise IOMappingParseError(
                "无法读取 IO Mapping Excel。\n"
                f"文件: {excel_path_to_open}\n"
                f"原因: {error}"
            )

        sheet_names = (
            [sheet_name for sheet_name in workbook.sheetnames]
            if (sheets_raw.strip() == "*" or not sheets_raw.strip())
            else [
                sheet_name_text.strip()
                for sheet_name_text in sheets_raw.split(",")
                if sheet_name_text.strip()
            ]
        )
        for sheet_name in sheet_names:
            if sheet_name not in workbook.sheetnames:
                raise FileNotFoundError(
                    f"IO_mapping sheet 不存在: {excel_path_to_open} | {sheet_name}"
                )
            worksheet = workbook[sheet_name]
            excel_name_for_log = os.path.basename(excel_path_to_open)
            header_row, col_map, missing = find_header_row_and_indices(
                worksheet, max_scan_rows=30
            )
            if header_row < 0 or missing:
                logger.error(
                    "[io_mapping] 跳过sheet: Excel=%s sheet=%s 表头缺少必须列: %s",
                    excel_name_for_log,
                    sheet_name,
                    ", ".join(missing) if missing else "Name, Path, Values",
                )
                continue
            logger.log(
                PROGRESS_LEVEL,
                "[io_mapping] 处理Excel=%s sheet名=%s",
                excel_name_for_log,
                sheet_name,
            )
            name_column_index, path_column_index, values_column_index = (
                col_map["name"],
                col_map["path"],
                col_map["values"],
            )
            local_name_to_path: Dict[str, str] = {}
            local_name_to_values: Dict[str, Dict[str, str]] = {}
            multi_path_warnings: Dict[str, dict] = {}
            for excel_row, row_values in enumerate(
                worksheet.iter_rows(min_row=header_row + 1, values_only=True),
                start=header_row + 1,
            ):
                name_cell_value = (
                    row_values[name_column_index]
                    if name_column_index < len(row_values)
                    else None
                )
                path_cell_value = (
                    row_values[path_column_index]
                    if path_column_index < len(row_values)
                    else None
                )
                values_cell_value = (
                    row_values[values_column_index]
                    if values_column_index < len(row_values)
                    else None
                )
                name_text = str(name_cell_value).strip() if name_cell_value is not None else ""
                path_text = str(path_cell_value).strip() if path_cell_value is not None else ""
                values_text = (
                    str(values_cell_value).strip()
                    if values_cell_value is not None
                    else ""
                )
                if not name_text and not path_text and not values_text:
                    continue
                if not name_text:
                    continue
                name_key = normalize_name_key(name_text)
                source_label = f"{os.path.basename(excel_path)}/{sheet_name}"
                if path_text:
                    if name_key in local_name_to_path and local_name_to_path[name_key] != path_text:
                        path_warn_record = multi_path_warnings.get(name_key)
                        if path_warn_record is None:
                            path_warn_record = {
                                "name": name_text,
                                "path_first": local_name_to_path.get(name_key, ""),
                                "ignored_paths": set(),
                                "rows": [],
                                "src": source_label,
                            }
                            multi_path_warnings[name_key] = path_warn_record
                        path_warn_record["ignored_paths"].add(path_text)
                        path_warn_record["rows"].append(excel_row)
                    else:
                        local_name_to_path[name_key] = path_text
                        if name_key not in name_to_path:
                            name_to_path[name_key] = path_text
                if values_text:
                    values_mapping = parse_values_cell(values_text)
                    if values_mapping:
                        current_local_values = local_name_to_values.get(name_key)
                        if current_local_values is None:
                            current_local_values = {}
                            local_name_to_values[name_key] = current_local_values
                        enum_conflict_info = None
                        for enum_key, enum_value in values_mapping.items():
                            if (
                                enum_key in current_local_values
                                and current_local_values[enum_key] != enum_value
                            ):
                                enum_conflict_info = (
                                    enum_key,
                                    current_local_values[enum_key],
                                    enum_value,
                                )
                                break
                        if enum_conflict_info is not None:
                            enum_key_conflict, first_enum_value, ignored_enum_value = enum_conflict_info
                            logger.warning(
                                "[io_mapping] Name 同表 Values 冲突，保留首次：来源=%s 行=%s name=%r enum=%r val_first=%r val_ignored=%r",
                                source_label,
                                excel_row,
                                name_text,
                                enum_key_conflict,
                                first_enum_value,
                                ignored_enum_value,
                            )
                        else:
                            for enum_key, enum_value in values_mapping.items():
                                if enum_key not in current_local_values:
                                    current_local_values[enum_key] = enum_value
                            current_global_values = name_to_values.get(name_key)
                            if current_global_values is None:
                                name_to_values[name_key] = dict(values_mapping)
                            else:
                                for enum_key, enum_value in values_mapping.items():
                                    if enum_key not in current_global_values:
                                        current_global_values[enum_key] = enum_value
            for path_warn_record in multi_path_warnings.values():
                ignored_paths = sorted(path_warn_record["ignored_paths"])
                rows = sorted(set(path_warn_record["rows"]))
                rows_preview = ",".join(str(row_index) for row_index in rows[:100]) + (
                    "" if len(rows) <= 100 else f"...(+{len(rows)-100})"
                )
                logger.warning(
                    "[io_mapping] Name 同表多 Path，保留首次：来源=%s name=%r path_first=%r path_ignored=%s 行=%s",
                    path_warn_record.get("src", ""),
                    path_warn_record.get("name", ""),
                    path_warn_record.get("path_first", ""),
                    ignored_paths,
                    rows_preview,
                )

    return IOMappingContext(name_to_path=name_to_path, name_to_values=name_to_values)

