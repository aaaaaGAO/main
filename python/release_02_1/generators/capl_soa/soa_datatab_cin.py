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
import re
from dataclasses import dataclass
from typing import Any

from infra.config.config_access import read_fixed_config
from infra.excel.workbook import merged_cell_value
from infra.filesystem.pathing import resolve_output_dir_relative_path
from generators.capl_soa.soa_excel_utils import is_client_marker, normalize_cell_text, open_workbook_cached
from services.config_constants import OPTION_SOA_DATATAB_OUTPUT_FILENAME

SERVICE_DEPLOYMENT_SHEET = "Service_Deployment"
SERVICE_INTERFACE_SHEET = "Service_Interface"
SOA_DATATAB_RELATIVE_PARTS: tuple[str, ...] = ("Public", "TESTmode", "Bus", "SOA", "SOA_Onder")
logger = logging.getLogger("generate_soa_datatab")
EXTRA_SKIP_ROWS_AFTER_HEADER = 1
MAX_CLIENT_SLOT_COUNT = 10
HEADER_SCAN_MAX_ROWS = 60
DEFAULT_MAX_COLUMN_SCAN = 120

CLIENT_HEADER_ALIASES: tuple[str, ...] = (
    "Clients",
    "Client",
    "客户端",
    "服务使用方",
    "服务调用方",
)
EXCLUDED_CLIENT_NODE_KEYS: set[str] = {"cdcusoc"}

# 与 Excel 转换脚本目视列对齐一致（逐项写死空格，便于在编辑器中对齐阅览）。
# 该常量作为节点表的“单一真源”：既用于输出，也用于构建节点编号映射。
SOA_NODEINFO_CIN_LINES: tuple[str, ...] = (
    '    {0,           "SOAEngine",            0,                        3},',
    '    {1,           "RDCU",                 6,                        3},',
    '    {2,           "LDCU",                 6,                        3},',
    '    {3,           "TBOX",                 6,                        3},',
    '    {4,          "Tester",               0xffffffff,      0xffffffff}',
)

NODEINFO_ENTRY_RE = re.compile(
    r"\{\s*(?P<idx>\d+)\s*,\s*\"(?P<name>[^\"]+)\"\s*,\s*(?P<left>0x[0-9A-Fa-f]+|\d+)\s*,\s*(?P<right>0x[0-9A-Fa-f]+|\d+)\s*\}",
    flags=re.IGNORECASE,
)


def parse_nodeinfo_entries_from_cin_lines(lines: tuple[str, ...]) -> list[tuple[int, str, int, int]]:
    """从固定的节点表文本行解析 `soa_nodeinfo` 条目。

    参数：
    - lines: `SOA_NODEINFO_CIN_LINES`，每行形如 `{idx, "Name", left, right}`（可含尾逗号）。

    返回：
    - list[tuple[int, str, int, int]]: `(node_index, node_name, left_value, right_value)` 列表。
    """
    entries: list[tuple[int, str, int, int]] = []
    for line in lines:
        match = NODEINFO_ENTRY_RE.search(line)
        if not match:
            raise ValueError(f"SOA_NODEINFO_CIN_LINES 行格式非法，无法解析: {line!r}")
        node_index = int(match.group("idx"), 10)
        node_name = match.group("name").strip()
        left_value = int(match.group("left"), 0)
        right_value = int(match.group("right"), 0)
        entries.append((node_index, node_name, left_value, right_value))
    if not entries:
        raise ValueError("SOA_NODEINFO_CIN_LINES 解析到 0 条目")
    return entries


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

def normalize_header_text(value: Any) -> str:
    """标准化列名：小写并移除全部空白。"""
    return "".join(normalize_cell_text(value).lower().split())


def normalize_node_key(node_name: str) -> str:
    """标准化节点名以便做变量表匹配。

    功能：
    - 对 ECU/节点名做去空白、大小写折叠；
    - 去除下划线、连字符等分隔符，兼容 `CDCU_SOC/CDCU SOC` 等格式差异。

    参数：
    - node_name: 原始节点名文本。

    返回：
    - str: 归一化后的节点匹配键；空值返回空字符串。
    """
    return "".join(ch for ch in normalize_cell_text(node_name).casefold() if ch.isalnum())


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


def format_service_id_literal(service_id_value: Any) -> str:
    """将 Service ID 格式化为 CAPL 可读字面量。

    功能：
    - 对十六进制/十进制 Service ID 统一转为 `0xNNNN` 大写格式；
    - 非法值保留原文本，便于问题排查。

    参数：
    - service_id_value: Service ID 原始单元格值。

    返回：
    - str: 适合写入 `.cin` 的 Service ID 文本；空值返回空字符串。
    """
    raw_text = normalize_cell_text(service_id_value)
    if not raw_text:
        return ""
    numeric_value = try_parse_element_id(service_id_value)
    if numeric_value is None:
        return raw_text
    return f"0x{numeric_value:04X}"


def build_header_row_values(worksheet: Any, row_idx: int, max_column: int) -> list[Any]:
    """读取指定行的表头候选值，兼容合并单元格。

    功能：
    - 逐列读取表头行；
    - 对合并单元格展开左上角值，提升双层表头识别稳定性。

    参数：
    - worksheet: OpenPyXL 工作表对象。
    - row_idx: 读取行号（1-based）。
    - max_column: 最大扫描列数。

    返回：
    - list[Any]: 指定行的列值列表。
    """
    row_values: list[Any] = []
    upper_column = max(max_column, 1)
    for column_idx in range(1, upper_column + 1):
        row_values.append(merged_cell_value(worksheet, row_idx, column_idx))
    return row_values


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
    """在候选区域内定位表头并返回列索引。

    功能：
    - 在前 60 行内扫描满足必需列的表头行；
    - 表头取值兼容合并单元格，适配双层/跨列标题。

    参数：
    - worksheet: OpenPyXL 工作表对象。
    - specs: 逻辑列与别名配置。

    返回：
    - tuple[int, dict[str, int]]: `(表头行号, 逻辑列到 0-based 列索引映射)`。
    """
    max_scan_rows = min(worksheet.max_row or HEADER_SCAN_MAX_ROWS, HEADER_SCAN_MAX_ROWS)
    max_column = worksheet.max_column or DEFAULT_MAX_COLUMN_SCAN
    for header_row in range(1, max_scan_rows + 1):
        header_values = build_header_row_values(worksheet, header_row, max_column)
        try:
            return header_row, resolve_column_indexes(header_values, specs)
        except ValueError:
            continue
    raise ValueError(f"工作表 {worksheet.title} 在前 {HEADER_SCAN_MAX_ROWS} 行均未识别到有效表头")


def read_rows_as_dicts(
    worksheet: Any,
    *,
    header_row: int,
    column_indexes: dict[str, int],
    skip_after_header: int = EXTRA_SKIP_ROWS_AFTER_HEADER,
) -> list[dict[str, Any]]:
    """按列索引读取工作表行并映射为字典列表。

    功能：
    - 从数据起始行开始逐行读取指定列；
    - 对合并单元格展开左上角值，兼容跨行继承式表格。

    参数：
    - worksheet: OpenPyXL 工作表对象。
    - header_row: 表头行号（1-based）。
    - column_indexes: 逻辑列到 0-based 列索引映射。
    - skip_after_header: 表头后的额外跳过行数，默认 1。

    返回：
    - list[dict[str, Any]]: 每行映射结果列表，仅保留存在任意非空值的行。
    """
    start_row = header_row + 1 + skip_after_header
    max_row = worksheet.max_row or start_row
    rows: list[dict[str, Any]] = []
    for row_idx in range(start_row, max_row + 1):
        row_data: dict[str, Any] = {}
        has_any_value = False
        for key, col_index in column_indexes.items():
            value = merged_cell_value(worksheet, row_idx, col_index + 1)
            row_data[key] = value
            if value is not None and normalize_cell_text(value):
                has_any_value = True
        if has_any_value:
            rows.append(row_data)
    return rows


def is_client_header_text(header_text: Any) -> bool:
    """判断表头文本是否表示 Clients 分组。

    功能：
    - 兼容英文/中文常见别名；
    - 允许表头包含附加说明，只要能明显命中 Clients 语义即可。

    参数：
    - header_text: 待判断的表头文本。

    返回：
    - bool: True 表示命中 Clients 分组；否则 False。
    """
    normalized_text = normalize_header_text(header_text)
    if not normalized_text:
        return False
    for alias in CLIENT_HEADER_ALIASES:
        normalized_alias = normalize_header_text(alias)
        if normalized_alias and (normalized_alias == normalized_text or normalized_alias in normalized_text):
            return True
    return False


def build_node_name_to_index_map_from_entries(
    nodeinfo_entries: list[tuple[int, str, int, int]],
) -> dict[str, int]:
    """构建 SOA 节点名到节点编号的映射。

    参数：
    - nodeinfo_entries: `soa_nodeinfo` 条目列表。

    返回：
    - dict[str, int]: 归一化节点名到节点编号的映射。
    """
    return {normalize_node_key(node_name): node_index for node_index, node_name, _, _ in nodeinfo_entries}


def locate_client_columns(worksheet: Any, header_row: int) -> list[tuple[int, str]]:
    """定位 Service_Deployment 中的 Clients 子列。

    功能：
    - 兼容 `Clients` 合并大标题 + 下一行 ECU 子列名；
    - 兼容上一行是 `Clients`、当前行是 ECU 名称的双层表头形式；
    - 保持列顺序，便于输出客户端位置数组与 Excel 视觉顺序一致。

    参数：
    - worksheet: `Service_Deployment` 工作表对象。
    - header_row: 已识别出的主表头行号（1-based）。

    返回：
    - list[tuple[int, str]]: `(1-based 列号, 客户端 ECU 名称)` 列表。
    """
    client_columns: list[tuple[int, str]] = []
    max_column = worksheet.max_column or 1
    for column_idx in range(1, max_column + 1):
        above_text = normalize_cell_text(merged_cell_value(worksheet, header_row - 1, column_idx)) if header_row > 1 else ""
        current_text = normalize_cell_text(merged_cell_value(worksheet, header_row, column_idx))
        below_text = (
            normalize_cell_text(merged_cell_value(worksheet, header_row + 1, column_idx))
            if header_row < (worksheet.max_row or header_row)
            else ""
        )
        if is_client_header_text(above_text) and current_text:
            client_columns.append((column_idx, current_text))
            continue
        if is_client_header_text(current_text) and below_text:
            client_columns.append((column_idx, below_text))
    return client_columns


def collect_service_entries(
    worksheet: Any,
    *,
    header_row: int,
    deployment_indexes: dict[str, int],
    nodeinfo_entries: list[tuple[int, str, int, int]],
) -> list[tuple[Any, ...]]:
    """根据 Service_Deployment 生成 `soa_serviceinfo` 条目。

    功能：
    - 从 `Service ID` / `Server ECU` / `Clients` 区域读取服务信息；
    - 初始化行字段顺序：行索引、Service ID、客户端数量、客户端节点位置数组、Server ECU 名称；
    - 客户端数量：Clients 区勾选列数（仅单元格为 `x`/`X`/`×` 时计入，排除 `CDCU_SOC`）；
    - 客户端节点编号数组：按列顺序收集，固定补足到 10 位。

    参数：
    - worksheet: `Service_Deployment` 工作表对象。
    - header_row: 表头行号（1-based）。
    - deployment_indexes: `Service_Deployment` 主列索引映射。

    返回：
    - list[tuple[Any, ...]]: `soa_serviceinfo` 结构体条目列表。
    """
    service_id_column = deployment_indexes["ServiceID"] + 1
    server_ecu_column = deployment_indexes["ServerECU"] + 1
    client_columns = locate_client_columns(worksheet, header_row)
    if not client_columns:
        raise ValueError("Service_Deployment 未识别到 Clients 客户端列，无法生成 soa_serviceinfo")

    node_index_map = build_node_name_to_index_map_from_entries(nodeinfo_entries)
    start_row = header_row + 1 + EXTRA_SKIP_ROWS_AFTER_HEADER
    max_row = worksheet.max_row or start_row
    entries: list[tuple[Any, ...]] = []

    for row_idx in range(start_row, max_row + 1):
        service_id_literal = format_service_id_literal(merged_cell_value(worksheet, row_idx, service_id_column))
        server_ecu_name = normalize_cell_text(merged_cell_value(worksheet, row_idx, server_ecu_column))
        if not service_id_literal and not server_ecu_name:
            continue
        if not service_id_literal or not server_ecu_name:
            logger.warning(
                "[soa_datatab] 跳过 Service_Deployment 第 %s 行：Service ID 或 Server ECU 为空（service_id=%r, server_ecu=%r）",
                row_idx,
                service_id_literal,
                server_ecu_name,
            )
            continue

        client_positions: list[int] = []
        for column_idx, client_name in client_columns:
            client_key = normalize_node_key(client_name)
            if not client_key or client_key in EXCLUDED_CLIENT_NODE_KEYS:
                continue
            if not is_client_marker(merged_cell_value(worksheet, row_idx, column_idx)):
                continue
            node_index = node_index_map.get(client_key)
            if node_index is None:
                logger.warning(
                    "[soa_datatab] Service_Deployment 第 %s 行客户端列 %r 未在 soa_nodeinfo 中定义，已忽略",
                    row_idx,
                    client_name,
                )
                continue
            if node_index not in client_positions:
                client_positions.append(node_index)

        if len(client_positions) > MAX_CLIENT_SLOT_COUNT:
            logger.warning(
                "[soa_datatab] Service_Deployment 第 %s 行客户端数量超过 %s，后续位置将被截断",
                row_idx,
                MAX_CLIENT_SLOT_COUNT,
            )
            client_positions = client_positions[:MAX_CLIENT_SLOT_COUNT]
        padded_positions = client_positions + [0] * (MAX_CLIENT_SLOT_COUNT - len(client_positions))
        entries.append(
            (
                len(entries),
                service_id_literal,
                len(client_positions),
                "{" + ",".join(str(item) for item in padded_positions) + "}",
                f'"{server_ecu_name}"',
            )
        )
    return entries


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


def find_previous_eventgroup_id(rows: list[dict[str, Any]], start_index: int) -> int:
    """向上查找最近的 EventgroupID（统一返回 int）。

    参数：
    - rows: `Service_Interface` 行列表。
    - start_index: 当前扫描行索引（0-based）。

    返回：
    - int: 解析到的 EventgroupID 数值；未找到或非法时返回 `0xFFFF`。
    """
    for idx in range(start_index - 1, -1, -1):
        candidate = normalize_cell_text(rows[idx].get("EventgroupID"))
        if candidate:
            try:
                return int(candidate, 0)
            except ValueError:
                logger.warning("[soa_datatab] EventgroupID=%r 非法，按 0xFFFF 处理", candidate)
                return 0xFFFF
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


def format_service_entries(entries: list[tuple[Any, ...]]) -> list[str]:
    """按 `SOA_ServiceInfo_Typ` 格式输出条目文本。

    功能：
    - 将 `soa_serviceinfo` 元组列表拼接为结构体初始化行；
    - 保持客户端位置数组原样写入，不额外加引号。

    参数：
    - entries: `soa_serviceinfo` 条目列表。

    返回：
    - list[str]: 每个元素为一行结构体文本。
    """
    lines: list[str] = []
    for idx, entry in enumerate(entries):
        entry_index, service_id, client_count, client_positions, server_name = entry
        suffix = "," if idx < len(entries) - 1 else ""
        lines.append(
            "{"
            f"{entry_index},    "
            f"{service_id},    "
            f"{client_count},    "
            f"{client_positions},    "
            f"{server_name}"
            "}"
            f"{suffix}"
        )
    return lines


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
    service_entries: list[tuple[Any, ...]],
    event_entries: list[tuple[Any, ...]],
    method_entries: list[tuple[Any, ...]],
    signal_entries: list[tuple[Any, ...]],
) -> str:
    """渲染 SOA_DataTab.cin 文本内容。"""
    service_lines = format_service_entries(service_entries)
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
        *SOA_NODEINFO_CIN_LINES,
        "  };",
        "",
        f"dword soa_serviceinfo_len = {len(service_entries)};",
        "",
        f"struct SOA_ServiceInfo_Typ soa_serviceinfo[{len(service_entries)}] = {{",
        *service_lines,
        "};",
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


class SOADataTabCinGenerator:
    """SOA_DataTab.cin 生成器（类收口版）。"""

    def __init__(self, *, base_dir: str, configured_output_dir: str) -> None:
        self._base_dir = base_dir
        self._configured_output_dir = configured_output_dir

    def generate(
        self,
        excel_path: str,
        *,
        workbook_cache: dict[str, Any] | None = None,
        output_filename: str | None = None,
    ) -> str:
        """读取服务通信矩阵并生成 SOA_DataTab.cin。"""
        absolute_excel = os.path.abspath(excel_path.strip())
        if not os.path.isfile(absolute_excel):
            raise FileNotFoundError(f"服务通信矩阵不存在: {absolute_excel}")
        logger.info("[soa_datatab] event=start excel=%s", absolute_excel)

        cached = open_workbook_cached(absolute_excel, workbook_cache=workbook_cache)
        workbook = cached.workbook
        try:
            if SERVICE_DEPLOYMENT_SHEET not in workbook.sheetnames:
                raise ValueError(f"Excel 缺少工作表 {SERVICE_DEPLOYMENT_SHEET}: {cached.normalized_excel_path}")
            if SERVICE_INTERFACE_SHEET not in workbook.sheetnames:
                raise ValueError(f"Excel 缺少工作表 {SERVICE_INTERFACE_SHEET}: {cached.normalized_excel_path}")

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
            nodeinfo_entries = parse_nodeinfo_entries_from_cin_lines(SOA_NODEINFO_CIN_LINES)
            service_entries = collect_service_entries(
                deployment_sheet,
                header_row=deployment_header_row,
                deployment_indexes=deployment_indexes,
                nodeinfo_entries=nodeinfo_entries,
            )
        finally:
            if cached.should_close and workbook is not None:
                workbook.close()

        service_to_ecu = build_service_to_ecu_map(deployment_rows)
        event_entries = collect_event_entries(interface_rows, service_to_ecu)
        method_entries = collect_method_entries(interface_rows, service_to_ecu)
        signal_entries = collect_signal_entries(interface_rows)
        logger.info(
            "[soa_datatab] event=parsed deployment_rows=%s interface_rows=%s services=%s events=%s methods=%s signals=%s",
            len(deployment_rows),
            len(interface_rows),
            len(service_entries),
            len(event_entries),
            len(method_entries),
            len(signal_entries),
        )

        document = render_datatab_document(service_entries, event_entries, method_entries, signal_entries)
        output_directory = resolve_datatab_output_directory(self._base_dir, self._configured_output_dir)
        resolved_output_filename = (output_filename or "").strip() or resolve_datatab_output_filename(self._base_dir)
        output_path = os.path.join(output_directory, resolved_output_filename)
        with open(output_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(document)
        logger.info("[soa_datatab] event=written output=%s", output_path)
        return output_path

