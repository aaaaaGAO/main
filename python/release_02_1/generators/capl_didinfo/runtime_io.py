#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDInfo 表头解析与单 Sheet 生成逻辑。

从根脚本迁入：find_header_row_and_cols、find_variant_cols、pick_sheet_name、
merged_cell_value、parse_int_or_range、parse_bit、normalize_did、normalize_field_data、
compute_positions_and_length、generate_from_sheet。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from utils.excel_io import norm_str


def find_header_row_and_cols(ws: Any) -> Tuple[int, dict]:
    """在工作表前 50 行内定位 Configure DID、Length (Bytes)、Byte、Bit 表头，返回 (header_row, col_map)。"""
    required = {"Configure DID", "Length (Bytes)", "Byte", "Bit"}
    for row_index in range(1, min(ws.max_row, 50) + 1):
        row_vals = {
            norm_str(ws.cell(row_index, column_index).value)
            for column_index in range(1, min(ws.max_column, 50) + 1)
        }
        if required.issubset(row_vals):
            col_map = {}
            for column_index in range(1, min(ws.max_column, 50) + 1):
                column_value = norm_str(ws.cell(row_index, column_index).value)
                if column_value in required:
                    col_map[column_value] = column_index
            return row_index, col_map
    raise RuntimeError("Header row not found (missing required columns).")
def norm_variant(s: str) -> str:
    return norm_str(s).upper()


def find_variant_cols(ws: Any, header_row: int, variant_names: list[str]) -> dict[str, int]:
    """在表头行及之前行中查找车型列名对应的列号（忽略大小写）。"""
    canonical_to_original = {
        norm_variant(variant_name): variant_name for variant_name in variant_names
    }
    found: dict[str, int] = {}
    for row_index in range(1, header_row + 1):
        for column_index in range(1, ws.max_column + 1):
            cell_value = norm_str(ws.cell(row_index, column_index).value)
            key = norm_variant(cell_value)
            if key in canonical_to_original:
                orig = canonical_to_original[key]
                if orig not in found:
                    found[orig] = column_index
        if len(found) == len(variant_names):
            break
    missing = [variant_name for variant_name in variant_names if variant_name not in found]
    if missing:
        raise RuntimeError(f"Variant column(s) not found in rows 1..{header_row}: {missing}")
    return found


def pick_sheet_name(wb: Any, preferred: str | None) -> str:
    """从工作簿选取 Sheet 名：preferred 存在则用，否则 LDCU/RDCU，否则第一个。"""
    if preferred and preferred in wb.sheetnames:
        return preferred
    for candidate in ("LDCU", "RDCU"):
        if candidate in wb.sheetnames:
            return candidate
    return wb.sheetnames[0]


def merged_cell_value(ws: Any, row: int, col: int) -> Any:
    """取单元格值，若在合并区域内则取左上角的值。"""
    cell = ws.cell(row, col)
    v = cell.value
    if v is not None:
        return v
    try:
        coord = cell.coordinate
        for merged_range in getattr(ws.merged_cells, "ranges", []):
            if coord in merged_range:
                return ws.cell(merged_range.min_row, merged_range.min_col).value
    except Exception:
        pass
    return v
def parse_int_or_range(byte_text: str) -> Optional[Tuple[int, int]]:
    """解析 Byte 列：单个数字或 a-b/a~b，返回 (start, end)。"""
    byte_text = norm_str(byte_text)
    if not byte_text:
        return None
    byte_text = byte_text.replace("~", "-")
    if "-" in byte_text:
        start_text, end_text = byte_text.split("-", 1)
        return int(start_text.strip()), int(end_text.strip())
    try:
        integer_value = int(byte_text)
        return integer_value, integer_value
    except ValueError:
        return None
def parse_bit(bit_text: str) -> Optional[Tuple[int, int, bool]]:
    """解析 Bit 列：All->(0,7,True)；数字->(i,i,False)；a-b->(a,b,False)；END/无效->None。"""
    bit_text = norm_str(bit_text)
    if not bit_text:
        return None
    if bit_text.upper() == "END":
        return None
    if bit_text.lower() == "all":
        return 0, 7, True
    if "-" in bit_text:
        start_text, end_text = bit_text.split("-", 1)
        return int(start_text.strip()), int(end_text.strip()), False
    try:
        bit_value = int(bit_text)
        return bit_value, bit_value, False
    except ValueError:
        return None


DID_PATTERN = re.compile(r"^\s*(?:0x)?([0-9A-Fa-f]+)\s*$")
def normalize_did(did_str: str) -> Optional[str]:
    """规范化 DID：XXXX 或 0xXXXX -> 0xXXXX（大写）。"""
    if not did_str:
        return None
    did_match = DID_PATTERN.match(did_str.strip())
    if did_match:
        return f"0x{did_match.group(1).upper()}"
    return None
def normalize_field_data(cell_val: Any) -> str:
    """规范化 Field_Data：空->0x00；0x 开头原样；含空格去空格。"""
    s = norm_str(cell_val)
    if not s or not s.strip():
        return "0x00"
    s = s.strip()
    if s.lower().startswith("0x"):
        return s
    if " " in s:
        compact = "".join(s.split())
        return compact if compact else "0x00"
    return s


@dataclass
class Field:
    """单字段信息（与 compute_positions_and_length 配合）。"""
    name: str
    byte_range: Tuple[int, int]
    bit_range: Tuple[int, int]
    bit_is_all: bool


def compute_positions_and_length(
    byte_range: Tuple[int, int],
    bit_range: Tuple[int, int],
    bit_is_all: bool,
) -> Tuple[int, int, int]:
    """计算 Field_BytePosition、Field_bitPosition、Field_FieldLength（bit）。返回 (byte_pos, bit_pos, length_bits)。"""
    byte_start, byte_end = byte_range
    bit_start, bit_end = bit_range
    byte_pos = byte_end
    if bit_is_all:
        bit_pos = 0
        length_bits = (byte_end - byte_start + 1) * 8
    else:
        bit_pos = bit_start
        bit_len = bit_end - bit_start + 1
        length_bits = bit_len if byte_end == byte_start else (byte_end - byte_start) * 8 + bit_len
    return byte_pos, bit_pos, length_bits
def flush_did_header(
    out_lines: list[str],
    *,
    sheet_name: str,
    variant_name: str,
    current_did: Optional[str],
    current_len: Optional[int],
    last_written_sheet: Optional[str],
    last_written_variant: Optional[str],
    last_written_did: Optional[str],
    last_written_len: Optional[int],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
    if current_did is None or current_len is None:
        return last_written_sheet, last_written_variant, last_written_did, last_written_len

    need_write = (
        last_written_sheet is None
        or last_written_variant is None
        or last_written_did is None
        or last_written_len is None
        or sheet_name != last_written_sheet
        or variant_name != last_written_variant
        or current_did != last_written_did
        or current_len != last_written_len
    )
    if need_write:
        out_lines.append(f"{{{sheet_name}}}")
        out_lines.append(f"[{variant_name}]")
        out_lines.append(f"[{current_did}]")
        out_lines.append(f"DIDLength:{current_len};//DID数据长度BYTE")
        return sheet_name, variant_name, current_did, current_len

    return last_written_sheet, last_written_variant, last_written_did, last_written_len


def generate_from_sheet(
    ws: Any,
    *,
    excel_name: str,
    variant_name: str,
    variant_col: int,
    sheet_name: str,
    last_sheet_name: Optional[str] = None,
    last_variant_name: Optional[str] = None,
    last_did: Optional[str] = None,
    last_len: Optional[int] = None,
) -> Tuple[str, str, str, str, int]:
    """针对一个 Sheet 和一个车型列，遍历数据行生成该 variant 的 DIDInfo 片段；同 DID+Length 下 Byte 重复校验。"""
    header_row, cols = find_header_row_and_cols(ws)
    col_did = cols["Configure DID"]
    col_len = cols["Length (Bytes)"]
    col_byte = cols["Byte"]
    col_bit = cols["Bit"]

    out_lines: list[str] = []
    current_did: Optional[str] = None
    current_len: Optional[int] = None
    seen_byte_pos: dict[tuple[str, int], dict[int, int]] = {}

    last_written_sheet = last_sheet_name
    last_written_variant = last_variant_name
    last_written_did = last_did
    last_written_len = last_len

    started = False
    for row_index in range(header_row + 1, ws.max_row + 1):
        did_cell = norm_str(merged_cell_value(ws, row_index, col_did))
        normalized_did = normalize_did(did_cell) if did_cell else None
        if normalized_did:
            current_did = normalized_did
            len_cell = merged_cell_value(ws, row_index, col_len)
            try:
                current_len = int(str(len_cell).strip())
            except Exception:
                current_len = None
            started = True
            (
                last_written_sheet,
                last_written_variant,
                last_written_did,
                last_written_len,
            ) = flush_did_header(
                out_lines,
                sheet_name=sheet_name,
                variant_name=variant_name,
                current_did=current_did,
                current_len=current_len,
                last_written_sheet=last_written_sheet,
                last_written_variant=last_written_variant,
                last_written_did=last_written_did,
                last_written_len=last_written_len,
            )

        if not started:
            continue

        byte_val_raw = merged_cell_value(ws, row_index, col_byte)
        byte_raw = norm_str(byte_val_raw)
        byte_cell_val = ws.cell(row_index, col_byte).value
        byte_is_explicit_cell = byte_cell_val is not None
        bit_raw = norm_str(merged_cell_value(ws, row_index, col_bit))

        if byte_raw and byte_raw.upper() == "END":
            continue
        if bit_raw and bit_raw.upper() == "END":
            continue

        if not byte_raw and not bit_raw:
            row_has_any = any(
                norm_str(ws.cell(row_index, column_index).value)
                for column_index in range(1, min(ws.max_column, 50) + 1)
            )
            if row_has_any:
                print(
                    f"[resetdid] ERROR Excel={excel_name} sheet '{sheet_name}', 车型 '{variant_name}', "
                    f"DID '{current_did}', 行 {row_index} 中 Byte/Bit 均为空，跳过该行。"
                )
            continue

        bit_parsed = parse_bit(bit_raw) if bit_raw else (0, 7, True)
        if not bit_raw and byte_raw:
            print(
                f"[resetdid] INFO Excel={excel_name} sheet '{sheet_name}', 车型 '{variant_name}', "
                f"DID '{current_did}', 行 {row_index} 中 Bit 为空，已使用 ALL 代替。"
            )
        if bit_parsed is None:
            continue

        if byte_raw:
            byte_parsed = parse_int_or_range(byte_raw)
            if byte_parsed:
                display_byte_raw = byte_raw
            else:
                continue
        else:
            print(
                f"[resetdid] ERROR Excel={excel_name} sheet '{sheet_name}', 车型 '{variant_name}', "
                f"DID '{current_did}', 行 {row_index} 中 Byte 为空，跳过该行。"
            )
            continue

        bit_start, bit_end, bit_is_all = bit_parsed
        byte_pos, bit_pos, length_bits = compute_positions_and_length(
            byte_parsed, (bit_start, bit_end), bit_is_all
        )
        field_data = normalize_field_data(ws.cell(row_index, variant_col).value)

        if byte_is_explicit_cell and current_did is not None and current_len is not None:
            key = (current_did, current_len)
            prev_map = seen_byte_pos.setdefault(key, {})
            prev_row = prev_map.get(byte_pos)
            if prev_row is not None:
                print(
                    f"[resetdid] ERROR Excel={excel_name} sheet '{sheet_name}', 车型 '{variant_name}', "
                    f"DID '{current_did}', Length '{current_len}', 行 {row_index} 中 BytePosition={byte_pos} 重复（首次出现在行 {prev_row}）。"
                )
            else:
                prev_map[byte_pos] = row_index

        byte_str_tag = f"Byte{display_byte_raw}"
        bit_normalized = bit_raw.strip() if bit_raw else ""
        bit_str_tag = "BitALL" if (not bit_raw or bit_is_all or bit_normalized.lower() == "all") else f"Bit{bit_normalized}"
        sub_data_name = f"DID{current_did}_{byte_str_tag}_{bit_str_tag}"

        out_lines.append(f"Field_subDataName:{sub_data_name};//字段名称")
        out_lines.append(f"Field_BytePosition:{byte_pos};//字段起始byte")
        out_lines.append(f"Field_bitPosition:{bit_pos};//字段起始bit;")
        out_lines.append(f"Field_FieldLength:{length_bits};//字段长度，单位bit;")
        out_lines.append("Field_SortOrder:0;//排序方式0是motorola,1是intel")
        out_lines.append(f"Field_Data:{field_data};//字段数据")
        out_lines.append("")

    while out_lines and out_lines[-1] == "":
        out_lines.pop()
    out_lines.append("")
    content = "\n".join(out_lines)
    final_sheet = last_written_sheet if last_written_sheet is not None else sheet_name
    final_variant = last_written_variant if last_written_variant is not None else variant_name
    final_did = last_written_did if last_written_did is not None else (last_did or "")
    final_len = last_written_len if last_written_len is not None else (last_len or 0)
    return (content, final_sheet, final_variant, final_did, final_len)
