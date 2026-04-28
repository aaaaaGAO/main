#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于服务通信矩阵 Excel 的 ``Service_Interface`` 工作表生成 ``SOA_StartSetserver.cin``。

本模块负责两类 CAPL 调用体的抽取与落盘：
1) Event：元组 ID > ``0x8001`` 且周期非空；
2) Method：元组 ID < ``0x8000`` 且 ``Type=RR-Out``（支持元组 ID 向下继承）。

核心协作关系：
- Excel 读取：`infra.excel.workbook.ExcelService`
- 表头映射：`infra.excel.header.ColumnMapper`
- 配置路径解析：`core.generator_config.GeneratorConfig` + `infra.filesystem.pathing`
- 输出文件名：`config/FixedConfig.ini` 的 `soa_setserver_output_filename`
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from core.generator_config import GeneratorConfig
from infra.config.config_access import read_fixed_config
from infra.excel.header import ColumnMapper
from infra.excel.workbook import ExcelService, merged_cell_value
from infra.filesystem.pathing import resolve_configured_path, resolve_output_dir_relative_path
from services.config_constants import (
    OPTION_SOA_SETSERVER_OUTPUT_FILENAME,
    OPTION_SRV_EXCEL,
    OPTION_SRV_EXCEL_CANDIDATES,
    SECTION_CENTRAL,
    SECTION_DTC,
    SECTION_LR_REAR,
)
from utils.logger import PROGRESS_LEVEL
DEFAULT_SOA_SETSERVER_REL_PARTS: tuple[str, ...] = ("TESTmode",)
SOA_LOGGER_NAME = "generate_soa_startsetserver"


logger = logging.getLogger(SOA_LOGGER_NAME)

TUPLE_ID_THRESHOLD = 0x8001
METHOD_TUPLE_ID_MAX_EXCLUSIVE = 0x8000

SERVICE_INTERFACE_SHEET = "Service_Interface"
SERVICE_DEPLOYMENT_SHEET = "Service_Deployment"

SERVICE_INTERFACE_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "service_name": (
        "Service Name",
        "服务名称",
    ),
    "tuple_id": (
        "Element ID",
        "元组ID",
        "元组 ID",
        "元组id",
        "Tuple ID",
        "TupleID",
        "ElementID",
    ),
    "cycle_ms": (
        "Cycle Time (ms)",
        "Cycle Time",
        "cycletime",
        "cycletime(ms)",
        "周期",
        "周期(ms)",
    ),
    "grammar": (
        "PayloadParameterGrammar",
        "负载参数语法",
        "Payload Parameter Grammar",
    ),
    "message_type": (
        "Type",
        "类型",
        "消息类型",
    ),
}

SERVICE_DEPLOYMENT_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "service_name": (
        "Service Name",
        "服务名称",
    ),
    "server_ecu": (
        "Server ECU",
        "服务提供方",
        "ServerECU",
    ),
}

CDCU_EXCLUDE_SERVER_ECUS: set[str] = {
    "soaengine",
    "tbox",
    "cdcusoc",
    "cdcumcu",
}

FIRST_PAYLOAD_FIELD_RE = re.compile(
    r"^[ \t]*[A-Za-z_]\w*(?:\[[^\]]+\])?\s*:\s*([A-Za-z_]\w*)",
    re.IGNORECASE | re.MULTILINE,
)

STRUCT_NAME_HEAD_RE = re.compile(r"^(\s*)([A-Za-z_]\w*)", re.MULTILINE)

DOMAIN_TO_SECTION: dict[str, str] = {
    "CENTRAL": SECTION_CENTRAL,
    "LR_REAR": SECTION_LR_REAR,
    "LR": SECTION_LR_REAR,
    "DTC": SECTION_DTC,
}


def normalize_cell_text(item_value: Any) -> str:
    """标准化单元格文本。

    功能：
    - 将 Excel 单元格值统一转换为去首尾空白的字符串。

    参数：
    - item_value: 原始单元格值，允许任意类型或 None。

    返回：
    - str: 标准化后的文本；当输入为 None 时返回空字符串。
    """
    if item_value is None:
        return ""
    return str(item_value).strip()


def parse_tuple_id_numeric(raw: Any) -> int | None:
    """解析元组/元素 ID 数值。

    功能：
    - 将元组 ID 文本解析为整数，兼容十六进制（如 ``0x8002``）和十进制。

    参数：
    - raw: 元组 ID 原始值，通常来自 Excel 单元格。

    返回：
    - int | None: 解析成功返回整数；空值或非法格式返回 None。
    """
    text = normalize_cell_text(raw)
    if not text:
        return None
    lowered = text.lower()
    try:
        if lowered.startswith("0x"):
            return int(lowered, 16)
        return int(text, 10)
    except ValueError:
        return None


def parse_cycle_ms_numeric(raw: Any) -> float | None:
    """解析周期毫秒值。

    功能：
    - 将周期列文本转为毫秒浮点数，支持末尾 ``ms`` 后缀。

    参数：
    - raw: 周期原始值，通常为数字或文本（如 ``500``、``500ms``）。

    返回：
    - float | None: 解析成功返回毫秒值；空值或非法格式返回 None。
    """
    text = normalize_cell_text(raw)
    if not text:
        return None
    text = re.sub(r"(?i)\s*ms\s*$", "", text).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def cycle_ms_to_sleep_token(cycle_ms: float) -> str:
    """将毫秒周期转换为 CAPL sleep token。

    功能：
    - 把毫秒值转换为 ``sleep`` 参数文本（单位秒），用于生成调用语句。

    参数：
    - cycle_ms: 周期毫秒值。

    返回：
    - str: 形如 ``sleep0.5``、``sleep1`` 的 token。
    """
    seconds = cycle_ms / 1000.0
    if abs(seconds - round(seconds)) < 1e-9:
        return f"sleep{int(round(seconds))}"
    normalized = f"{seconds:.6f}".rstrip("0").rstrip(".")
    return f"sleep{normalized}"


def extract_struct_name_and_first_field(grammar_text: str) -> tuple[str, str] | None:
    """解析负载语法中的结构体名和首字段名。

    功能：
    - 从 ``PayloadParameterGrammar`` 文本提取结构体名；
    - 提取第一条 ``类型:字段名`` 的字段名（不限制类型必须是 uint/int/float 等白名单）。

    参数：
    - grammar_text: 负载参数语法原始文本。

    返回：
    - tuple[str, str] | None: 成功返回 ``(结构体名, 首字段名)``；失败返回 None。
    """
    grammar_text = grammar_text.strip()
    if not grammar_text:
        return None
    brace_idx = grammar_text.find("{")
    head_part = grammar_text[:brace_idx] if brace_idx != -1 else grammar_text
    head_line = head_part.strip().splitlines()
    struct_name = ""
    if head_line:
        first_line = head_line[0].strip()
        token_match = re.match(r"^([A-Za-z_]\w*)", first_line)
        if token_match:
            struct_name = token_match.group(1)
    search_body = grammar_text[brace_idx + 1 :] if brace_idx != -1 else grammar_text
    field_match = FIRST_PAYLOAD_FIELD_RE.search(search_body)
    if field_match:
        field_name = field_match.group(1)
        if struct_name:
            return struct_name, field_name
    field_match_all = FIRST_PAYLOAD_FIELD_RE.search(grammar_text)
    if not field_match_all:
        return None
    field_name = field_match_all.group(1)
    if not struct_name:
        struct_match = STRUCT_NAME_HEAD_RE.search(grammar_text)
        if struct_match:
            struct_name = struct_match.group(2)
    if not struct_name:
        return None
    return struct_name, field_name


def build_header_row_values(worksheet: Any, row_idx: int, max_column: int) -> list[Any]:
    """读取指定行的表头候选值。

    功能：
    - 逐列读取行数据；
    - 对合并单元格按左上角值展开，保证表头识别一致性。

    参数：
    - worksheet: OpenPyXL 工作表对象。
    - row_idx: 读取行号（1-based）。
    - max_column: 最大扫描列数。

    返回：
    - list[Any]: 该行的列值列表。
    """
    row_values: list[Any] = []
    upper_col = max(max_column, 1)
    for column_idx in range(1, upper_col + 1):
        row_values.append(merged_cell_value(worksheet, row_idx, column_idx))
    return row_values


def locate_service_interface_header(worksheet: Any) -> tuple[int, ColumnMapper]:
    """定位 Service_Interface 的表头行并构造列映射器。

    功能：
    - 在前 60 行内扫描满足必需列的表头行；
    - 返回表头行号及列名映射结果。

    参数：
    - worksheet: OpenPyXL 工作表对象。

    返回：
    - tuple[int, ColumnMapper]: ``(表头行号, 列映射器)``。
    """
    max_row_scan = min(worksheet.max_row or 60, 60)
    max_column = worksheet.max_column or 80
    required_fields = ("service_name", "tuple_id", "cycle_ms", "grammar", "message_type")
    for row_idx in range(1, max_row_scan + 1):
        header_row = build_header_row_values(worksheet, row_idx, max_column)
        column_mapper = ColumnMapper(aliases=SERVICE_INTERFACE_COLUMN_ALIASES, required=required_fields)
        if column_mapper.scan(header_row):
            logger.info("Service_Interface 表头定位在第 %s 行", row_idx)
            return row_idx, column_mapper
    error_message = "Service_Interface 表中未找到有效表头行（需同时包含元组 ID / 周期 / 类型 / 负载参数语法相关列）"
    logger.error(error_message)
    raise ValueError(error_message)


def locate_service_deployment_header(worksheet: Any) -> tuple[int, ColumnMapper]:
    """定位 Service_Deployment 的表头行并构造列映射器。

    功能：
    - 在前 60 行内扫描满足必需列的表头行；
    - 返回表头行号及列名映射结果。

    参数：
    - worksheet: OpenPyXL 工作表对象。

    返回：
    - tuple[int, ColumnMapper]: ``(表头行号, 列映射器)``。
    """
    max_row_scan = min(worksheet.max_row or 60, 60)
    max_column = worksheet.max_column or 120
    required_fields = ("service_name", "server_ecu")
    for row_idx in range(1, max_row_scan + 1):
        header_row = build_header_row_values(worksheet, row_idx, max_column)
        column_mapper = ColumnMapper(aliases=SERVICE_DEPLOYMENT_COLUMN_ALIASES, required=required_fields)
        if column_mapper.scan(header_row):
            return row_idx, column_mapper
    error_message = "Service_Deployment 表中未找到有效表头行（需包含 Service Name / Server ECU）"
    logger.error(error_message)
    raise ValueError(error_message)


def normalize_service_name_key(service_name: str) -> str:
    """标准化服务名称匹配键。

    功能：
    - 对服务名称做去首尾空白与大小写折叠；
    - 仅用于严格匹配 Service Name（不使用中文名列）。

    参数：
    - service_name: 原始服务名称文本。

    返回：
    - str: 归一化后的服务名称键；空输入返回空字符串。
    """
    return normalize_cell_text(service_name).casefold()


def normalize_server_ecu_key(server_ecu: str) -> str:
    """标准化服务提供方匹配键。

    功能：
    - 对 Server ECU 文本做去空白、大小写折叠；
    - 去除下划线/连字符/空格等分隔符，规避格式差异。

    参数：
    - server_ecu: 原始服务提供方文本。

    返回：
    - str: 归一化后的服务提供方键；空输入返回空字符串。
    """
    text = normalize_cell_text(server_ecu).casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def build_service_name_to_server_ecus_map(workbook: Any) -> dict[str, set[str]]:
    """从 Service_Deployment 构建服务名到服务提供方集合映射。

    功能：
    - 读取 `Service_Deployment` 工作表中的 `Service Name` 与 `Server ECU`；
    - 按服务名向下继承规则归并；
    - 输出 ``service_name_key -> {server_ecu_key, ...}`` 映射供过滤阶段使用。

    参数：
    - workbook: 已打开的工作簿对象。

    返回：
    - dict[str, set[str]]: 服务名到服务提供方集合的归一化映射。
    """
    if SERVICE_DEPLOYMENT_SHEET not in workbook.sheetnames:
        error_message = f"Excel 缺少工作表 «{SERVICE_DEPLOYMENT_SHEET}»：无法按服务名称与服务提供方执行过滤"
        logger.error(error_message)
        raise ValueError(error_message)
    worksheet = workbook[SERVICE_DEPLOYMENT_SHEET]
    header_row_idx, column_mapper = locate_service_deployment_header(worksheet)
    service_col = column_mapper.get("service_name")
    server_col = column_mapper.get("server_ecu")
    mapping: dict[str, set[str]] = {}
    current_service_name = ""
    max_row = worksheet.max_row or header_row_idx

    for row_idx in range(header_row_idx + 1, max_row + 1):
        service_raw = merged_cell_value(worksheet, row_idx, service_col + 1)
        service_name = normalize_cell_text(service_raw)
        if service_name:
            current_service_name = service_name
        if not current_service_name:
            continue
        server_raw = merged_cell_value(worksheet, row_idx, server_col + 1)
        server_ecu = normalize_cell_text(server_raw)
        if not server_ecu:
            continue
        service_key = normalize_service_name_key(current_service_name)
        server_key = normalize_server_ecu_key(server_ecu)
        if not service_key or not server_key:
            continue
        mapping.setdefault(service_key, set()).add(server_key)
    return mapping


def should_skip_service_by_uds_qualifier(
    service_name: str,
    service_server_map: dict[str, set[str]],
    uds_ecu_qualifier: str,
) -> bool:
    """根据 uds_ecu_qualifier 判断是否应跳过服务名称整组。

    功能：
    - 将服务名称映射到 Service_Deployment 的服务提供方集合；
    - 常规规则：若 qualifier 与任一 Server ECU 匹配，则整组跳过；
    - 特殊规则：当 qualifier 为 `cdcu`，命中 `SOAEngine/TBOX/CDCU_SOC/CDCU_MCU` 任一即跳过。

    参数：
    - service_name: Service_Interface 当前行（含向下继承）所属服务名称。
    - service_server_map: 服务名到服务提供方集合映射。
    - uds_ecu_qualifier: 当前域选择的 UDS ECU（如 ldcu/rdcu/cdcu）。

    返回：
    - bool: True 表示该服务名称整组应跳过；False 表示可继续生成。
    """
    qualifier_key = normalize_server_ecu_key(uds_ecu_qualifier)
    if not qualifier_key:
        return False
    service_key = normalize_service_name_key(service_name)
    if not service_key:
        return False
    server_keys = service_server_map.get(service_key, set())
    if not server_keys:
        return False
    if qualifier_key == "cdcu":
        return any(server_key in CDCU_EXCLUDE_SERVER_ECUS for server_key in server_keys)
    return qualifier_key in server_keys


def collect_setserver_call_lines(
    worksheet: Any,
    header_row_idx: int,
    column_mapper: ColumnMapper,
    *,
    service_server_map: dict[str, set[str]],
    uds_ecu_qualifier: str,
) -> list[str]:
    """收集 Event 方法的 SetServer 调用行。

    功能：
    - 依据 Event 规则筛选行（元组 ID > ``0x8001`` 且周期有效）；
    - 从负载语法提取结构体名与首字段名，生成带 ``sleep`` 的调用语句。

    参数：
    - worksheet: OpenPyXL 工作表对象。
    - header_row_idx: 表头行号（1-based）。
    - column_mapper: 表头列映射器。

    返回：
    - list[str]: CAPL 调用语句列表，每项为一行完整代码。
    """
    service_col = column_mapper.get("service_name")
    tuple_col = column_mapper.get("tuple_id")
    cycle_col = column_mapper.get("cycle_ms")
    grammar_col = column_mapper.get("grammar")
    lines_out: list[str] = []
    max_row = worksheet.max_row or header_row_idx
    current_service_name = ""

    for row_idx in range(header_row_idx + 1, max_row + 1):
        service_raw = merged_cell_value(worksheet, row_idx, service_col + 1)
        service_name = normalize_cell_text(service_raw)
        if service_name:
            current_service_name = service_name
        if should_skip_service_by_uds_qualifier(current_service_name, service_server_map, uds_ecu_qualifier):
            continue
        tuple_raw = merged_cell_value(worksheet, row_idx, tuple_col + 1)
        cycle_raw = merged_cell_value(worksheet, row_idx, cycle_col + 1)
        grammar_raw = merged_cell_value(worksheet, row_idx, grammar_col + 1)

        tuple_num = parse_tuple_id_numeric(tuple_raw)
        if tuple_num is None or tuple_num <= TUPLE_ID_THRESHOLD:
            continue

        cycle_ms = parse_cycle_ms_numeric(cycle_raw)
        if cycle_ms is None:
            logger.debug("跳过行 %s：周期为空或非数字", row_idx)
            continue

        grammar_text = normalize_cell_text(grammar_raw)
        if not grammar_text:
            logger.debug("跳过行 %s：负载参数语法为空", row_idx)
            continue

        parsed = extract_struct_name_and_first_field(grammar_text)
        if not parsed:
            logger.warning("跳过行 %s：无法从负载语法解析结构体名或首字段", row_idx)
            continue
        struct_name, member_name = parsed
        sleep_token = cycle_ms_to_sleep_token(cycle_ms)
        argument = f'{struct_name}.{member_name}:0 {sleep_token}'
        lines_out.append(f'    gTC_CANTest_SOA_SetSever("{argument}");')

    return lines_out


def is_rr_out_type(type_text: str) -> bool:
    """判断消息类型是否为 RR-Out。

    功能：
    - 对 ``Type`` 文本做大小写、空白、连字符归一化后匹配 RR-Out。

    参数：
    - type_text: Type 列原始文本。

    返回：
    - bool: True 表示 RR-Out；否则 False。
    """
    normalized = re.sub(r"[\s\-_]+", "", type_text).lower()
    return normalized == "rrout"


def collect_setserver_method_lines(
    worksheet: Any,
    header_row_idx: int,
    column_mapper: ColumnMapper,
    *,
    service_server_map: dict[str, set[str]],
    uds_ecu_qualifier: str,
) -> list[str]:
    """收集 Method 方法的 SetServer 调用行。

    功能：
    - 依据 Method 规则筛选行（元组 ID < ``0x8000`` 且 ``Type=RR-Out``）；
    - 支持元组 ID 向下继承：空单元格沿用最近一次有效元组 ID；
    - 从负载语法提取结构体名与首字段名，生成 ``:0`` 结尾调用语句。

    参数：
    - worksheet: OpenPyXL 工作表对象。
    - header_row_idx: 表头行号（1-based）。
    - column_mapper: 表头列映射器。

    返回：
    - list[str]: CAPL 调用语句列表，每项为一行完整代码。
    """
    service_col = column_mapper.get("service_name")
    tuple_col = column_mapper.get("tuple_id")
    grammar_col = column_mapper.get("grammar")
    type_col = column_mapper.get("message_type")
    lines_out: list[str] = []
    max_row = worksheet.max_row or header_row_idx
    current_service_name = ""
    current_tuple_id: int | None = None

    for row_idx in range(header_row_idx + 1, max_row + 1):
        service_raw = merged_cell_value(worksheet, row_idx, service_col + 1)
        service_name = normalize_cell_text(service_raw)
        if service_name:
            current_service_name = service_name
        if should_skip_service_by_uds_qualifier(current_service_name, service_server_map, uds_ecu_qualifier):
            continue
        tuple_raw = merged_cell_value(worksheet, row_idx, tuple_col + 1)
        tuple_num = parse_tuple_id_numeric(tuple_raw)
        if tuple_num is not None:
            current_tuple_id = tuple_num
        if current_tuple_id is None or current_tuple_id >= METHOD_TUPLE_ID_MAX_EXCLUSIVE:
            continue

        type_text = normalize_cell_text(merged_cell_value(worksheet, row_idx, type_col + 1))
        if not is_rr_out_type(type_text):
            continue

        grammar_text = normalize_cell_text(merged_cell_value(worksheet, row_idx, grammar_col + 1))
        if not grammar_text:
            logger.debug("跳过行 %s：RR-Out 行负载参数语法为空", row_idx)
            continue
        parsed = extract_struct_name_and_first_field(grammar_text)
        if not parsed:
            logger.warning("跳过行 %s：RR-Out 行无法从负载语法解析结构体名或首字段", row_idx)
            continue
        struct_name, member_name = parsed
        argument = f"{struct_name}.{member_name}:0"
        lines_out.append(f'    gTC_CANTest_SOA_SetSever("{argument}");')

    return lines_out


def render_cin_document(event_lines: list[str], method_lines: list[str]) -> str:
    """渲染完整 `.cin` 文本。

    功能：
    - 按固定模板拼接 includes / variables / Event / Method；
    - 使用 CRLF 换行输出，兼容既有 CAPL 文件习惯。

    参数：
    - event_lines: Event 函数体调用语句列表。
    - method_lines: Method 函数体调用语句列表。

    返回：
    - str: 可直接写入文件的完整 `.cin` 文本。
    """
    event_body = "\r\n".join(event_lines) if event_lines else ""
    method_body = "\r\n".join(method_lines) if method_lines else ""
    parts = [
        "/*@!Encoding:65001*/",
        "includes",
        "{",
        "  ",
        "}",
        "",
        "variables",
        "{",
        "  ",
        "}",
        "",
        "void gTC_SOA_Setserver_Event()",
        "{",
        event_body,
        "}",
        "",
        "void gTC_SOA_Setserver_Method()",
        "{",
        method_body,
        "}",
        "",
    ]
    return "\r\n".join(parts)


def resolve_setserver_testmode_directory(anchor_path: str) -> str:
    """按 output_dir 下级规则解析 SOA_StartSetserver 输出目录。

    功能：
    - 将锚点视为 `output_dir`（文件则取其所在目录）；
    - 在该目录下拼接 ``TESTmode``；
    - 目录不存在时抛错（严格模式）。

    参数：
    - anchor_path: 锚点路径，可为文件或目录。

    返回：
    - str: 已存在的输出目录绝对路径（`output_dir/TESTmode`）。
    """
    if not anchor_path or not str(anchor_path).strip():
        raise ValueError("anchor_path 为空")
    anchor_abs = os.path.abspath(anchor_path.strip())
    if not os.path.exists(anchor_abs):
        raise FileNotFoundError(f"锚点路径不存在: {anchor_path}")
    output_dir = anchor_abs if os.path.isdir(anchor_abs) else os.path.dirname(anchor_abs)
    return resolve_output_dir_relative_path(
        output_dir,
        ".",
        DEFAULT_SOA_SETSERVER_REL_PARTS,
        anchor_level="self",
        required=True,
    )


def resolve_setserver_output_directory_strict(anchor_path: str) -> str:
    """按 output_dir 下级规则解析 SOA_StartSetserver 输出目录（严格模式）。

    功能：
    - 与 `resolve_setserver_testmode_directory` 行为一致；
    - 仅做目录解析，不创建任何缺失目录。

    参数：
    - anchor_path: 锚点路径，可为文件或目录。

    返回：
    - str: 已存在的输出目录绝对路径（`output_dir/TESTmode`）。
    """
    return resolve_setserver_testmode_directory(anchor_path)


def resolve_srv_excel_absolute_path(base_dir: str, domain_key: str) -> str:
    """从配置解析服务通信矩阵路径。

    功能：
    - 根据域名映射到配置节；
    - 从该节读取 ``srv_excel``（含候选键）并解析为绝对路径。

    参数：
    - base_dir: 工程基础目录。
    - domain_key: 域名（如 CENTRAL/LR_REAR/DTC）。

    返回：
    - str: 服务通信矩阵 Excel 的绝对路径。
    """
    section_name = DOMAIN_TO_SECTION.get(domain_key.upper(), SECTION_CENTRAL)
    generator_config = GeneratorConfig(os.path.abspath(base_dir)).load()
    srv_value = ""
    for option_name in (OPTION_SRV_EXCEL, *OPTION_SRV_EXCEL_CANDIDATES):
        srv_value = generator_config.get_from_section(section_name, option_name, fallback="").strip()
        if srv_value:
            break
    if not srv_value:
        raise ValueError(f"未配置 [{section_name}] srv_excel（服务通信矩阵），且请求未提供 excel_path")
    resolved_path = resolve_configured_path(generator_config.base_dir, srv_value)
    return resolved_path


def resolve_setserver_filename(base_dir: str) -> str:
    """解析 SOA_StartSetserver 输出文件名。

    功能：
    - 从 `FixedConfig.ini` 读取 `soa_setserver_output_filename`；
    - 缺失或为空时抛错，避免代码侧硬编码默认值。

    参数：
    - base_dir: 工程根目录。

    返回：
    - str: 输出文件名（不含目录）。
    """
    fixed_config = read_fixed_config(base_dir)
    filename = (fixed_config.get(OPTION_SOA_SETSERVER_OUTPUT_FILENAME) or "").strip()
    if not filename:
        raise ValueError(
            f"FixedConfig.ini 缺少配置项 `{OPTION_SOA_SETSERVER_OUTPUT_FILENAME}`，请在 [PATHS] 中显式配置。"
        )
    return filename


def detect_base_dir_for_fixed_config(anchor_path: str, excel_path: str) -> str:
    """探测可读取 FixedConfig.ini 的工程根目录。

    功能：
    - 优先从 `anchor_path` 向上查找 `config/FixedConfig.ini`；
    - 未命中时再从 `excel_path` 向上查找；
    - 都未命中则回退到 `anchor_path` 的目录。

    参数：
    - anchor_path: 输出锚点路径（文件或目录）。
    - excel_path: 当前输入 Excel 绝对路径。

    返回：
    - str: 估算得到的工程根目录。
    """
    candidates = [anchor_path, excel_path]
    for seed in candidates:
        current = os.path.abspath(seed)
        if os.path.isfile(current):
            current = os.path.dirname(current)
        visited: set[str] = set()
        while current and current not in visited:
            visited.add(current)
            fixed_path = os.path.join(current, "config", "FixedConfig.ini")
            if os.path.isfile(fixed_path):
                return current
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    fallback = os.path.abspath(anchor_path)
    if os.path.isfile(fallback):
        fallback = os.path.dirname(fallback)
    return fallback


def generate_setserver_cin_from_excel(
    excel_path: str,
    anchor_path: str,
    *,
    find_or_create_soa_onder: bool = False,
    uds_ecu_qualifier: str = "",
    workbook_cache: dict[str, Any] | None = None,
    output_filename: str | None = None,
) -> str:
    """生成并写出 ``SOA_StartSetserver.cin``。

    功能：
    - 读取 ``Service_Interface`` 工作表并定位表头；
    - 生成 Event 与 Method 两段调用内容；
    - 解析输出目录并写入目标 `.cin` 文件。

    参数：
    - excel_path: 服务通信矩阵 Excel 路径。
    - anchor_path: 输出锚点路径（文件或目录均可）。
    - find_or_create_soa_onder: 历史兼容参数，已固定为严格模式；
      无论 True/False，目录缺失都会直接报错。
    - uds_ecu_qualifier: 当前域选择的 ECU（如 LDCU/RDCU/CDCU），用于服务名级别过滤。
    - workbook_cache: 可选工作簿缓存；传入时优先复用已打开 workbook，
      并由调用方统一关闭。

    返回：
    - str: 最终写入的 ``SOA_StartSetserver.cin`` 绝对路径。
    """
    absolute_excel = os.path.abspath(excel_path.strip())
    if not os.path.isfile(absolute_excel):
        raise FileNotFoundError(f"Excel 不存在: {absolute_excel}")

    normalized_excel_path = os.path.normcase(absolute_excel)
    should_close_workbook = workbook_cache is None
    workbook = None
    if workbook_cache is not None:
        workbook = workbook_cache.get(normalized_excel_path)
    if workbook is None:
        workbook = ExcelService.open_workbook(normalized_excel_path, data_only=True, read_only=False)
        if workbook_cache is not None:
            workbook_cache[normalized_excel_path] = workbook
    try:
        if SERVICE_INTERFACE_SHEET not in workbook.sheetnames:
            error_message = f"Excel 缺少工作表 «{SERVICE_INTERFACE_SHEET}»: {normalized_excel_path}"
            logger.error(error_message)
            raise ValueError(error_message)
        service_server_map = build_service_name_to_server_ecus_map(workbook)
        worksheet = workbook[SERVICE_INTERFACE_SHEET]
        header_row_idx, column_mapper = locate_service_interface_header(worksheet)
        event_call_lines = collect_setserver_call_lines(
            worksheet,
            header_row_idx,
            column_mapper,
            service_server_map=service_server_map,
            uds_ecu_qualifier=uds_ecu_qualifier,
        )
        method_call_lines = collect_setserver_method_lines(
            worksheet,
            header_row_idx,
            column_mapper,
            service_server_map=service_server_map,
            uds_ecu_qualifier=uds_ecu_qualifier,
        )
    finally:
        if should_close_workbook:
            workbook.close()

    if not event_call_lines and not method_call_lines:
        raise ValueError(
            "未生成任何调用行：请确认 Service_Interface 存在可用数据（Event: 元组 ID > 0x8001 且周期非空；"
            "Method: 元组 ID < 0x8000 且 Type=RR-Out；且负载语法可解析首字段）。"
        )

    cin_text = render_cin_document(event_call_lines, method_call_lines)
    if find_or_create_soa_onder:
        logger.warning(
            "find_or_create_soa_onder=True 已废弃：SOA_StartSetserver 输出目录固定为严格模式，不再自动创建目录。"
        )
    output_directory = resolve_setserver_output_directory_strict(anchor_path)
    resolved_output_filename = (output_filename or "").strip()
    if not resolved_output_filename:
        fixed_base_dir = detect_base_dir_for_fixed_config(anchor_path, normalized_excel_path)
        resolved_output_filename = resolve_setserver_filename(fixed_base_dir)
    output_file_path = os.path.join(output_directory, resolved_output_filename)

    with open(output_file_path, "w", encoding="utf-8-sig", newline="") as output_file:
        output_file.write(cin_text)

    logger.log(
        PROGRESS_LEVEL,
        "已写入 %s（Event=%s 条，Method=%s 条）",
        output_file_path,
        len(event_call_lines),
        len(method_call_lines),
    )
    return output_file_path


__all__ = [
    "DOMAIN_TO_SECTION",
    "generate_setserver_cin_from_excel",
    "resolve_srv_excel_absolute_path",
]
