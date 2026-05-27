#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOA Node .can 底部 ServerCheck 列表生成。

从服务通信矩阵 Excel 的 NodeInfo 工作表读取 Node / Client ID，
生成各 Node.can 文件末尾统一的 ``SOALib_NodeServerCheckSubEcuNameList`` 常量块。
供 ``generators.capl_soa.entrypoint`` 在渲染 Node 模板时注入。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from infra.excel.header import ColumnMapper
from infra.excel.workbook import ExcelService
from generators.capl_soa.soa_excel_utils import normalize_cell_text

logger = logging.getLogger("generate_soa_startsetserver")

NODEINFO_SHEET_CANONICAL = "nodeinfo"
HEADER_SCAN_MAX_ROWS = 60
DEFAULT_MAX_COLUMN_SCAN = 40
SERVER_CHECK_CLIENT_ID_SUFFIX = "14AC"
SERVER_CHECK_EMPTY_NAME = ""
SERVER_CHECK_EMPTY_CLIENT_LITERAL = "0x0"

NODEINFO_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "Node": ("Node", "节点", "节点名", "NodeName"),
    "ClientID": ("ClientID", "Client ID", "客户端ID", "Client Id"),
}
VALID_NODE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class NodeServerCheckEntry:
    """NodeInfo 单行 ServerCheck 条目。"""

    node_name: str
    client_id_literal: str


class SOANodeServerCheckUtility:
    """NodeInfo → ServerCheck CAPL 文本块工具类。"""

    @staticmethod
    def normalize_sheet_key(sheet_name: str) -> str:
        """将工作表名规范化为比对键（忽略空格与大小写）。"""
        return re.sub(r"\s+", "", normalize_cell_text(sheet_name)).casefold()

    @classmethod
    def resolve_nodeinfo_sheet(cls, workbook: Any) -> Any:
        """在工作簿中定位 NodeInfo 工作表（名称大小写/空格不敏感）。

        参数：
            workbook：已打开的 openpyxl Workbook。

        返回：
            工作表对象。

        异常：
            ValueError：未找到 NodeInfo 工作表。
        """
        for sheet_name in workbook.sheetnames:
            if cls.normalize_sheet_key(sheet_name) == NODEINFO_SHEET_CANONICAL:
                return workbook[sheet_name]
        available = ", ".join(workbook.sheetnames)
        raise ValueError(
            f"服务通信矩阵缺少 NodeInfo 工作表（名称大小写/空格不敏感）。当前工作表: {available}"
        )

    @staticmethod
    def format_client_id_for_server_check(client_id_value: Any) -> str:
        """将 NodeInfo 的 Client ID 转为 ServerCheck 用的 dword 字面量。

        规则（与历史 Excel 转换脚本一致）：
        - 后缀固定 ``14AC``；
        - 对 ``0x10XX``：高/低字节对调后末两字符写 ``01``（例 ``0x102D`` → ``0x2D0114AC``，``0x10E0`` → ``0xE00114AC``）。

        参数：
            client_id_value：Client ID 单元格原始值。

        返回：
            str：如 ``0x2D0114AC``；无法解析时返回 ``0x0``。
        """
        raw_text = normalize_cell_text(client_id_value)
        if not raw_text:
            return SERVER_CHECK_EMPTY_CLIENT_LITERAL
        try:
            numeric_value = int(raw_text, 0)
        except ValueError:
            logger.warning("[soa_node] Client ID=%r 无法解析，按 0x0 处理", raw_text)
            return SERVER_CHECK_EMPTY_CLIENT_LITERAL

        hex_four = f"{numeric_value & 0xFFFF:04X}"
        high_byte = hex_four[0:2]
        low_byte = hex_four[2:4]
        swapped = low_byte + high_byte
        middle = swapped[:2] + "01"
        return f"0x{middle}{SERVER_CHECK_CLIENT_ID_SUFFIX}"

    @classmethod
    def locate_header_row(cls, worksheet: Any) -> tuple[int, ColumnMapper]:
        """定位 NodeInfo 表头行与列映射。

        参数：
            worksheet：NodeInfo 工作表。

        返回：
            (header_row_index, column_mapper)，行号为 1-based。

        异常：
            ValueError：未识别到 Node / Client ID 列。
        """
        max_row = min(worksheet.max_row or HEADER_SCAN_MAX_ROWS, HEADER_SCAN_MAX_ROWS)
        mapper = ColumnMapper(aliases=NODEINFO_HEADER_ALIASES, required=("Node", "ClientID"))
        for row_idx in range(1, max_row + 1):
            header_values = [
                worksheet.cell(row=row_idx, column=column_idx).value
                for column_idx in range(1, DEFAULT_MAX_COLUMN_SCAN + 1)
            ]
            if mapper.scan(header_values):
                return row_idx, mapper
        raise ValueError("NodeInfo 工作表未识别到 Node / Client ID 表头行")

    @classmethod
    def read_entries_from_worksheet(cls, worksheet: Any) -> list[NodeServerCheckEntry]:
        """从 NodeInfo 工作表读取 ServerCheck 数据行（不含首行空占位）。

        参数：
            worksheet：NodeInfo 工作表。

        返回：
            list[NodeServerCheckEntry]：按表内顺序的节点条目。
        """
        header_row, mapper = cls.locate_header_row(worksheet)
        node_col = mapper.get("Node") + 1
        client_col = mapper.get("ClientID") + 1
        entries: list[NodeServerCheckEntry] = []
        for row_idx in range(header_row + 1, (worksheet.max_row or header_row) + 1):
            node_name = normalize_cell_text(ExcelService.merged_cell_value(worksheet, row_idx, node_col))
            client_raw = ExcelService.merged_cell_value(worksheet, row_idx, client_col)
            if not node_name and not normalize_cell_text(client_raw):
                continue
            if not node_name:
                continue
            if not VALID_NODE_NAME_PATTERN.match(node_name):
                logger.warning(
                    "[soa_node] NodeInfo 第 %s 行 Node=%r 非 ECU 节点名，已跳过",
                    row_idx,
                    node_name,
                )
                continue
            client_literal = cls.format_client_id_for_server_check(client_raw)
            if client_literal == SERVER_CHECK_EMPTY_CLIENT_LITERAL:
                logger.warning(
                    "[soa_node] NodeInfo 第 %s 行 Node=%r Client ID 无效，已跳过",
                    row_idx,
                    node_name,
                )
                continue
            entries.append(NodeServerCheckEntry(node_name=node_name, client_id_literal=client_literal))
        return entries

    @classmethod
    def read_entries_from_workbook(cls, workbook: Any) -> list[NodeServerCheckEntry]:
        """从工作簿读取 NodeInfo ServerCheck 条目。"""
        worksheet = cls.resolve_nodeinfo_sheet(workbook)
        return cls.read_entries_from_worksheet(worksheet)

    @staticmethod
    def render_server_check_block(data_entries: list[NodeServerCheckEntry]) -> str:
        """渲染写入每个 Node.can 底部的 ServerCheck 常量块。

        参数：
            data_entries：NodeInfo 数据行（不含固定首行 ``{"", 0x0}``）。

        返回：
            str：CAPL 源码片段（用于插入 variables 块内，不含首尾空行）。
        """
        total_count = len(data_entries) + 1
        lines: list[str] = [
            f"  const SOALib_NodeServerCheckSubEcuNameListNum = {total_count};",
            "  struct SOALib_NodeServerCheckSubEcuListType "
            "SOALib_NodeServerCheckSubEcuNameList[SOALib_NodeServerCheckSubEcuNameListNum] = ",
            "  {",
            f'    {{ "{SERVER_CHECK_EMPTY_NAME}", {SERVER_CHECK_EMPTY_CLIENT_LITERAL}}},',
        ]
        for index, entry in enumerate(data_entries):
            suffix = "," if index < len(data_entries) - 1 else ""
            lines.append(
                f'    {{ "{entry.node_name}",   {entry.client_id_literal}}}{suffix}'
            )
        lines.append("  };")
        return "\r\n".join(lines)
