#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOA_DataTab.cin 生成器。

本模块负责从服务通信矩阵 Excel（Service_Deployment / Service_Interface）
生成 SOA_DataTab.cin，作为 SOA 页面流程中的第三个生成物。
输出目录固定为用户 output_dir 的上一级下：
Public/TESTmode/Bus/SOA/SOA_Onder（严格模式，不自动创建）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from infra.config.config_access import read_fixed_config
from infra.excel.workbook import ExcelService
from infra.filesystem.pathing import resolve_output_dir_relative_path
from services.config_constants import OPTION_SOA_DATATAB_OUTPUT_FILENAME

SERVICE_DEPLOYMENT_SHEET = "Service_Deployment"
SERVICE_INTERFACE_SHEET = "Service_Interface"
SOA_DATATAB_RELATIVE_PARTS: tuple[str, ...] = ("Public", "TESTmode", "Bus", "SOA", "SOA_Onder")
logger = logging.getLogger("generate_soa_startsetserver")


@dataclass(frozen=True)
class HeaderSpec:
    """表头候选配置。"""

    canonical: str
    aliases: tuple[str, ...]


DEPLOYMENT_HEADER_SPECS: tuple[HeaderSpec, ...] = (
    HeaderSpec("ServerECU", ("ServerECU", "Server ECU", "服务提供方", "服务提供方ECU", "服务提供方 ECU")),
    HeaderSpec("ServiceID", ("ServiceID", "Service ID", "服务ID", "服务 Id", "SomeipServiceID", "SOMEIP Service ID")),
)

INTERFACE_HEADER_SPECS: tuple[HeaderSpec, ...] = (
    HeaderSpec(
        "PayloadParameterGrammar",
        ("PayloadParameterGrammar", "Payload Parameter Grammar", "Payload", "参数语法", "负载参数语法"),
    ),
    HeaderSpec("ElementID", ("ElementID", "Element ID", "元素ID", "元组ID", "元组 ID", "元组id", "TupleID", "Tuple ID")),
    HeaderSpec("ServiceID", ("ServiceID", "Service ID", "服务ID", "服务接口ID")),
    HeaderSpec("Name", ("Name", "名称", "ServiceName", "Service Name", "服务名称", "子服务名称")),
    HeaderSpec("EventgroupID", ("EventgroupID", "Eventgroup ID", "EventGroupID", "事件组ID", "Event Group ID")),
    HeaderSpec("Type", ("Type", "类型", "消息类型")),
)

EXTRA_SKIP_ROWS_AFTER_HEADER = 1


def normalize_cell_text(value: Any) -> str:
    """将单元格值标准化为去空白字符串。"""
    if value is None:
        return ""
    return str(value).strip()


def normalize_header_text(value: Any) -> str:
    """标准化列名：小写并移除全部空白。"""
    return "".join(normalize_cell_text(value).lower().split())


def try_parse_element_id(element_id_value: Any) -> int | None:
    """解析 ElementID（支持十六进制与十进制）。"""
    text = normalize_cell_text(element_id_value)
    if not text:
        return None
    try:
        return int(text, 0)
    except ValueError:
        return None


def parse_payload_struct(grammar_text: str) -> tuple[str | None, list[dict[str, str]]]:
    """解析 PayloadParameterGrammar 文本，提取结构体名与字段列表。"""
    lines = grammar_text.strip().splitlines()
    if not lines:
        return None, []
    struct_name = lines[0].strip()
    fields: list[dict[str, str]] = []
    for line in lines[1:]:
        segment = line.strip()
        if not segment or segment in ("{", "}"):
            continue
        if ":" not in segment:
            continue
        field_type, field_name = segment.split(":", 1)
        fields.append({"type": field_type.strip(), "name": field_name.strip().rstrip(";,")})
    return struct_name, fields


def resolve_column_indexes(header_values: list[Any], specs: tuple[HeaderSpec, ...]) -> dict[str, int]:
    """根据表头行解析列索引（0-based）。"""
    normalized_headers = [normalize_header_text(item) for item in header_values]
    index_map: dict[str, int] = {}
    used_indices: set[int] = set()
    for spec in specs:
        matched_index = -1
        for alias in spec.aliases:
            alias_key = normalize_header_text(alias)
            if not alias_key:
                continue
            for idx, header_key in enumerate(normalized_headers):
                if idx in used_indices or not header_key:
                    continue
                if alias_key == header_key or (len(alias_key) >= 4 and header_key.startswith(alias_key)):
                    matched_index = idx
                    break
            if matched_index >= 0:
                break
        if matched_index < 0:
            for alias in spec.aliases:
                alias_key = normalize_header_text(alias)
                if len(alias_key) < 3:
                    continue
                for idx, header_key in enumerate(normalized_headers):
                    if idx in used_indices or not header_key:
                        continue
                    if alias_key in header_key or header_key in alias_key:
                        matched_index = idx
                        break
                if matched_index >= 0:
                    break
        if matched_index < 0:
            raise ValueError(f"未找到列 {spec.canonical}，候选={spec.aliases}")
        used_indices.add(matched_index)
        index_map[spec.canonical] = matched_index
    return index_map


def locate_header_and_indexes(worksheet: Any, specs: tuple[HeaderSpec, ...]) -> tuple[int, dict[str, int]]:
    """在前 3 行中定位表头并返回列索引。"""
    for header_row in (1, 2, 3):
        header_values = [worksheet.cell(row=header_row, column=idx).value for idx in range(1, (worksheet.max_column or 1) + 1)]
        try:
            return header_row, resolve_column_indexes(header_values, specs)
        except ValueError:
            continue
    raise ValueError(f"工作表 {worksheet.title} 在前 3 行均未识别到有效表头")


def read_rows_as_dicts(
    worksheet: Any,
    *,
    header_row: int,
    column_indexes: dict[str, int],
    skip_after_header: int = EXTRA_SKIP_ROWS_AFTER_HEADER,
) -> list[dict[str, Any]]:
    """按列索引读取工作表行并映射为字典列表。"""
    start_row = header_row + 1 + skip_after_header
    max_row = worksheet.max_row or start_row
    rows: list[dict[str, Any]] = []
    for row_idx in range(start_row, max_row + 1):
        row_data: dict[str, Any] = {}
        has_any_value = False
        for key, col_index in column_indexes.items():
            value = worksheet.cell(row=row_idx, column=col_index + 1).value
            row_data[key] = value
            if value is not None and normalize_cell_text(value):
                has_any_value = True
        if has_any_value:
            rows.append(row_data)
    return rows


def build_service_to_ecu_map(deployment_rows: list[dict[str, Any]]) -> dict[str, str]:
    """构建 ServiceID 到 ServerECU 的映射（同 ServiceID 取首个非空 ECU）。"""
    mapping: dict[str, str] = {}
    for row in deployment_rows:
        service_id = normalize_cell_text(row.get("ServiceID"))
        server_ecu = normalize_cell_text(row.get("ServerECU"))
        if service_id and server_ecu and service_id not in mapping:
            mapping[service_id] = server_ecu
    return mapping


def find_next_service_row(rows: list[dict[str, Any]], start_index: int) -> int:
    """查找下一个 ServiceID 非空的行索引（找不到返回 len(rows)）。"""
    for idx in range(start_index + 1, len(rows)):
        if normalize_cell_text(rows[idx].get("ServiceID")):
            return idx
    return len(rows)


def collect_event_entries(interface_rows: list[dict[str, Any]], service_to_ecu: dict[str, str]) -> list[tuple[Any, ...]]:
    """生成 soa_subserviceinfo 条目。"""
    entries: list[tuple[Any, ...]] = []
    entry_index = 0
    for i, row in enumerate(interface_rows):
        service_id = normalize_cell_text(row.get("ServiceID"))
        if not service_id:
            continue
        ecu_name = service_to_ecu.get(service_id, "")
        block_end = find_next_service_row(interface_rows, i)
        for j in range(i + 1, block_end):
            child = interface_rows[j]
            eventgroup_id = normalize_cell_text(child.get("EventgroupID"))
            if not eventgroup_id:
                continue
            name = normalize_cell_text(child.get("Name"))
            entries.append((entry_index, service_id, eventgroup_id, f'"{name}"', f'"{ecu_name}"'))
            entry_index += 1
    return entries


def find_previous_eventgroup_id(rows: list[dict[str, Any]], start_index: int) -> str:
    """向上查找最近的 EventgroupID；未找到返回 65535 对应整数。"""
    for idx in range(start_index - 1, -1, -1):
        candidate = normalize_cell_text(rows[idx].get("EventgroupID"))
        if candidate:
            return candidate
    return 0xFFFF


def collect_method_entries(interface_rows: list[dict[str, Any]], service_to_ecu: dict[str, str]) -> list[tuple[Any, ...]]:
    """生成 soa_subservice_methodinfo 条目。"""
    entries: list[tuple[Any, ...]] = []
    entry_index = 0
    for i, row in enumerate(interface_rows):
        service_id = normalize_cell_text(row.get("ServiceID"))
        if not service_id:
            continue
        ecu_name = service_to_ecu.get(service_id, "")
        block_end = find_next_service_row(interface_rows, i)
        for j in range(i + 1, block_end):
            child = interface_rows[j]
            element_id = normalize_cell_text(child.get("ElementID"))
            if not element_id:
                continue
            element_id_num = try_parse_element_id(child.get("ElementID"))
            if element_id_num is None:
                continue
            eventgroup_id = find_previous_eventgroup_id(interface_rows, j) if element_id_num > 0x8000 else 0xFFFF
            name = normalize_cell_text(child.get("Name"))
            entries.append((entry_index, service_id, element_id, f'"{name}"', f'"{ecu_name}"', eventgroup_id))
            entry_index += 1
    return entries


def collect_signal_entries(interface_rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """生成 soa_signalinfo 条目（首列编号从 1 开始）。"""
    entries: list[tuple[Any, ...]] = []
    index_value = 1
    subservice_index = 0
    for row in interface_rows:
        grammar = normalize_cell_text(row.get("PayloadParameterGrammar"))
        if not grammar:
            continue
        struct_name, fields = parse_payload_struct(grammar)
        if not struct_name:
            continue
        if normalize_cell_text(row.get("Type")) == "RR-Out":
            subservice_index -= 1
        for field in fields:
            entries.append((index_value, subservice_index, f'"{struct_name}"', f'"{field["name"]}"', f'"{field["type"]}"'))
            index_value += 1
        subservice_index += 1
    return entries


def format_struct_entries(entries: list[tuple[Any, ...]]) -> list[str]:
    """将事件/方法结构体条目格式化为文本行。"""
    lines: list[str] = []
    for idx, entry in enumerate(entries):
        body = ",    ".join(str(x) for x in entry)
        comma = "," if idx < len(entries) - 1 else ""
        lines.append("{" + body + "}" + comma)
    return lines


def format_signal_entries(entries: list[tuple[Any, ...]]) -> list[str]:
    """按原脚本格式输出 soa_signalinfo 条目文本。"""
    lines: list[str] = []
    for idx, entry in enumerate(entries):
        signal_index, subservice_index, struct_name, signal_name, signal_type = entry
        suffix = "," if idx < len(entries) - 1 else ""
        lines.append(
            "{"
            f"{signal_index},      "
            f"{subservice_index},      "
            f"{struct_name},      "
            f"{signal_name},      "
            f"{signal_type}"
            "}"
            f"{suffix}"
        )
    return lines


def render_datatab_document(
    event_entries: list[tuple[Any, ...]],
    method_entries: list[tuple[Any, ...]],
    signal_entries: list[tuple[Any, ...]],
) -> str:
    """渲染 SOA_DataTab.cin 文本内容。"""
    event_lines = format_struct_entries(event_entries)
    method_lines = format_struct_entries(method_entries)
    signal_lines = format_signal_entries(signal_entries)
    parts: list[str] = [
        "/*@!Encoding:936*/",
        "includes",
        "{",
        '   // #include "SOA_DataTyp.cin"',
        "}",
        "",
        "variables",
        "{",
        "   struct SOA_NodeInfo_Typ soa_nodeinfo[MAX_NODE_NUM] = {",
        '       {0,           "SOAEngine",            0,                        3},',
        '       {1,           "RDCU",                 6,                        3},',
        '       {2,           "LDCU",                 6,                        3},',
        '       {3,           "TBOX",                 6,                        3},',
        '       {4,           "Tester",               0xffffffff,      0xffffffff}',
        "   };",
        "",
        f"dword soa_subserviceinfo_len = {len(event_entries)};",
        f"struct SOA_SubServiceEventInfo_Typ soa_subserviceinfo[{len(event_entries)}] = {{",
        *event_lines,
        "};",
        f"dword soa_subservice_len = {len(method_entries)};",
        f"struct SOA_SubServiceMethodInfo_Typ soa_subservice_methodinfo[{len(method_entries)}] = {{",
        *method_lines,
        "};",
        f"dword soa_signalinfo_len = {len(signal_entries)};",
        f"struct SOA_SignalInfo_Typ soa_signalinfo[{len(signal_entries)}] = {{",
        *signal_lines,
        "};",
        "}",
        "",
    ]
    return "\n".join(parts)


def resolve_datatab_output_directory(base_dir: str, configured_output_dir: str) -> str:
    """解析 SOA_DataTab 固定输出目录（严格存在校验）。"""
    return resolve_output_dir_relative_path(
        base_dir,
        configured_output_dir,
        SOA_DATATAB_RELATIVE_PARTS,
        anchor_level="parent",
        required=True,
    )


def resolve_datatab_output_filename(base_dir: str) -> str:
    """从 FixedConfig.ini 读取 SOA_DataTab 输出文件名。"""
    fixed_config = read_fixed_config(base_dir)
    output_filename = (fixed_config.get(OPTION_SOA_DATATAB_OUTPUT_FILENAME) or "").strip()
    if not output_filename:
        raise ValueError(
            f"FixedConfig.ini 缺少配置项 `{OPTION_SOA_DATATAB_OUTPUT_FILENAME}`，请在 [PATHS] 中显式配置。"
        )
    return output_filename


def generate_datatab_cin_from_excel(
    excel_path: str,
    *,
    base_dir: str,
    configured_output_dir: str,
    workbook_cache: dict[str, Any] | None = None,
    output_filename: str | None = None,
) -> str:
    """读取服务通信矩阵并生成 SOA_DataTab.cin。"""
    absolute_excel = os.path.abspath(excel_path.strip())
    if not os.path.isfile(absolute_excel):
        raise FileNotFoundError(f"服务通信矩阵不存在: {absolute_excel}")
    logger.info("[soa_datatab] event=start excel=%s", absolute_excel)

    normalized_excel = os.path.normcase(absolute_excel)
    should_close_workbook = workbook_cache is None
    workbook = None
    if workbook_cache is not None:
        workbook = workbook_cache.get(normalized_excel)
    if workbook is None:
        workbook = ExcelService.open_workbook(normalized_excel, data_only=True, read_only=False)
        if workbook_cache is not None:
            workbook_cache[normalized_excel] = workbook

    try:
        if SERVICE_DEPLOYMENT_SHEET not in workbook.sheetnames:
            raise ValueError(f"Excel 缺少工作表 {SERVICE_DEPLOYMENT_SHEET}: {normalized_excel}")
        if SERVICE_INTERFACE_SHEET not in workbook.sheetnames:
            raise ValueError(f"Excel 缺少工作表 {SERVICE_INTERFACE_SHEET}: {normalized_excel}")

        deployment_sheet = workbook[SERVICE_DEPLOYMENT_SHEET]
        interface_sheet = workbook[SERVICE_INTERFACE_SHEET]
        deployment_header_row, deployment_indexes = locate_header_and_indexes(deployment_sheet, DEPLOYMENT_HEADER_SPECS)
        interface_header_row, interface_indexes = locate_header_and_indexes(interface_sheet, INTERFACE_HEADER_SPECS)
        deployment_rows = read_rows_as_dicts(
            deployment_sheet,
            header_row=deployment_header_row,
            column_indexes=deployment_indexes,
        )
        interface_rows = read_rows_as_dicts(
            interface_sheet,
            header_row=interface_header_row,
            column_indexes=interface_indexes,
        )
    finally:
        if should_close_workbook and workbook is not None:
            workbook.close()

    service_to_ecu = build_service_to_ecu_map(deployment_rows)
    event_entries = collect_event_entries(interface_rows, service_to_ecu)
    method_entries = collect_method_entries(interface_rows, service_to_ecu)
    signal_entries = collect_signal_entries(interface_rows)
    logger.info(
        "[soa_datatab] event=parsed deployment_rows=%s interface_rows=%s events=%s methods=%s signals=%s",
        len(deployment_rows),
        len(interface_rows),
        len(event_entries),
        len(method_entries),
        len(signal_entries),
    )

    document = render_datatab_document(event_entries, method_entries, signal_entries)
    output_directory = resolve_datatab_output_directory(base_dir, configured_output_dir)
    resolved_output_filename = (output_filename or "").strip() or resolve_datatab_output_filename(base_dir)
    output_path = os.path.join(output_directory, resolved_output_filename)
    with open(output_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(document)
    logger.info("[soa_datatab] event=written output=%s", output_path)
    return output_path

