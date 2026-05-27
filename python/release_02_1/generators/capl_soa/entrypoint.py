#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOA Node 生成入口（中央域）：
从服务通信矩阵 Excel（Service_Deployment）生成 ILNode/SOANode/*.can。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from jinja2 import Environment, FileSystemLoader
from infra.filesystem.pathing import RuntimePathResolver
from core.generator_config import GeneratorConfig
from generators.capl_soa.soa_node_server_check import SOANodeServerCheckUtility
from generators.capl_soa.soa_setserver_cin import SOASetServerCinGenerator
from generators.capl_soa.soa_excel_utils import is_client_marker, normalize_cell_text, open_workbook_cached
from services.config_constants import (
    OPTION_OUTPUT_DIR,
    OPTION_OUTPUT_DIR_CANDIDATES,
    OPTION_SRV_EXCEL,
    OPTION_SRV_EXCEL_CANDIDATES,
)
from utils.logger import PROGRESS_LEVEL

SOA_LOGGER_NAME = "generate_soa_startsetserver"
logger = logging.getLogger(SOA_LOGGER_NAME)


class SOAGenerationUtility:
    """SOA 生成入口能力统一工具类。

    要求：
    - 本模块不保留模块级业务函数（def）；所有入口与流程均通过本类承载。
    - 对外兼容入口使用“变量别名”，避免出现 `def run_generation()` 影子函数。
    """

    @staticmethod
    def normalize_text(raw: Any) -> str:
        """兼容入口：标准化单元格文本。"""
        return normalize_cell_text(raw)

    @staticmethod
    def resolve_base_and_config(
        base_dir: str | None,
        config_path: str | None,
    ) -> GeneratorConfig:
        """解析运行根目录并加载生成器配置。

        参数：
            base_dir：可选项目根目录。
            config_path：可选主配置路径。

        返回：
            已加载完成的 `GeneratorConfig` 实例。
        """
        resolved_base_dir = RuntimePathResolver.resolve_base_dir(__file__, base_dir)
        resolved_config_path = RuntimePathResolver.resolve_config_path(resolved_base_dir, config_path)
        return GeneratorConfig(resolved_base_dir, config_path=resolved_config_path).load()

    @staticmethod
    def load_paths(gconfig: GeneratorConfig, base_dir: str, domain: str) -> tuple[str, str]:
        """读取 SOA 输入矩阵，并按 output_dir 向上两级定位 public 输出目录。"""
        srv_excel = ""
        for option_name in (OPTION_SRV_EXCEL, *OPTION_SRV_EXCEL_CANDIDATES):
            srv_excel = gconfig.get_from_section(domain, option_name, fallback="").strip()
            if srv_excel:
                break
        if not srv_excel:
            raise ValueError(f"未配置 [{domain}] srv_excel（服务通信矩阵）")
        output_dir = ""
        for option_name in (OPTION_OUTPUT_DIR, *OPTION_OUTPUT_DIR_CANDIDATES):
            output_dir = gconfig.get_from_section(domain, option_name, fallback="").strip()
            if output_dir:
                break
        if not output_dir:
            raise ValueError(f"未配置 [{domain}] output_dir（输出路径）")
        excel_path = RuntimePathResolver.resolve_configured_path(base_dir, srv_excel)
        soa_output_dir = RuntimePathResolver.resolve_soa_output_dir_relative_path(
            base_dir,
            output_dir,
            ("public", "ILNode", "SOANode"),
            required=True,
            purpose="SOA Node（.can）生成",
        )
        return excel_path, soa_output_dir

    @staticmethod
    def read_variables_list_from_workbook(workbook: Any) -> list[dict[str, Any]]:
        """从已打开工作簿的 Service_Deployment 工作表提取节点变量列表。

        参数：
            workbook：已打开的 Excel Workbook。

        返回：
            list[dict[str, Any]]：Jinja 模板变量列表。
        """
        if "Service_Deployment" not in workbook.sheetnames:
            error_message = "服务通信矩阵缺少工作表 Service_Deployment"
            logger.error(error_message)
            raise ValueError(error_message)
        sheet = workbook["Service_Deployment"]

        node_name_col = 0
        service_id_col = 3
        instance_id_col = 4
        major_col = 5
        minor_col = 6
        port_col = 7
        protocol_col = 10
        consumer_start_col = 12

        node_data: dict[str, dict[str, Any]] = {}

        for row in sheet.iter_rows(min_row=3, values_only=True):
            provider_node = (
                normalize_cell_text(row[node_name_col]) if len(row) > node_name_col else ""
            )
            service_id = (
                normalize_cell_text(row[service_id_col]) if len(row) > service_id_col else ""
            )
            instance_id = (
                normalize_cell_text(row[instance_id_col]) if len(row) > instance_id_col else ""
            )
            major = normalize_cell_text(row[major_col]) if len(row) > major_col else ""
            minor = normalize_cell_text(row[minor_col]) if len(row) > major_col else ""
            protocol = (
                normalize_cell_text(row[protocol_col]) if len(row) > protocol_col else ""
            )
            port = normalize_cell_text(row[port_col]) if len(row) > port_col else ""

            if not provider_node or not service_id:
                continue

            protocol_value = "6" if protocol.upper() == "TCP" else "17"
            if provider_node not in node_data:
                node_data[provider_node] = {
                    "NodeName": provider_node,
                    "Protocol": protocol_value,
                    "Port": port,
                    "ProvidedServiceList": [
                        {
                            "ServiceId": "0x0000",
                            "InstanceId": "0x00",
                            "Major": "0x00",
                            "Minor": "0x00",
                        }
                    ],
                    "ConsumedServiceList": [
                        {
                            "ServiceId": "0x0000",
                            "InstanceId": "0x00",
                            "Major": "0x00",
                            "Minor": "0x00",
                        }
                    ],
                }

            node_data[provider_node]["ProvidedServiceList"].append(
                {"ServiceId": service_id, "InstanceId": instance_id, "Major": major, "Minor": minor}
            )

            for col_index in range(consumer_start_col, sheet.max_column):
                consumer_node = normalize_cell_text(sheet.cell(row=2, column=col_index + 1).value)
                has_mark = len(row) > col_index and is_client_marker(row[col_index])
                if not consumer_node or not has_mark:
                    continue
                if consumer_node not in node_data:
                    node_data[consumer_node] = {
                        "NodeName": consumer_node,
                        "Protocol": protocol_value,
                        "Port": port,
                        "ProvidedServiceList": [
                            {
                                "ServiceId": "0x0000",
                                "InstanceId": "0x00",
                                "Major": "0x00",
                                "Minor": "0x00",
                            }
                        ],
                        "ConsumedServiceList": [
                            {
                                "ServiceId": "0x0000",
                                "InstanceId": "0x00",
                                "Major": "0x00",
                                "Minor": "0x00",
                            }
                        ],
                    }
                node_data[consumer_node]["ConsumedServiceList"].append(
                    {"ServiceId": service_id, "InstanceId": instance_id, "Major": major, "Minor": minor}
                )

        for node in node_data.values():
            node["ProvidedServiceListNum"] = str(len(node["ProvidedServiceList"]))
            node["ConsumedServiceListNum"] = str(len(node["ConsumedServiceList"]))
        return list(node_data.values())

    @staticmethod
    def read_variables_list_from_excel(
        excel_path: str,
        *,
        workbook_cache: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """打开 Excel 并从 Service_Deployment 工作表提取节点变量列表。"""
        cached = open_workbook_cached(excel_path, workbook_cache=workbook_cache)
        try:
            return SOAGenerationUtility.read_variables_list_from_workbook(cached.workbook)
        finally:
            if cached.should_close:
                cached.workbook.close()

    @staticmethod
    def render_nodes_to_files(
        variables_list: list[dict[str, Any]],
        output_dir: str,
        *,
        server_check_block: str = "",
    ) -> None:
        """将节点变量列表渲染并写入 SOA Node 文件。

        参数：
            variables_list：各节点模板变量字典列表。
            output_dir：SOANode 输出目录。
            server_check_block：NodeInfo 生成的 ServerCheck 常量块（各 .can 共用）。
        """
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
        template = env.get_template("Node.template")
        for variables in variables_list:
            output_path = os.path.join(output_dir, f"{variables['NodeName']}.can")
            render_context = dict(variables)
            render_context["ServerCheckBlock"] = server_check_block
            rendered = template.render(**render_context)
            with open(output_path, "w", encoding="utf-8-sig", newline="\r\n") as file_obj:
                file_obj.write(rendered)

    @classmethod
    def run_generation(
        cls,
        config_path: str | None = None,
        base_dir: str | None = None,
        domain: str = "CENTRAL",
        *,
        workbook_cache: dict[str, Any] | None = None,
    ) -> GeneratorConfig:
        """执行 SOA 节点生成主流程。"""
        gconfig = cls.resolve_base_and_config(base_dir, config_path)
        resolved_base_dir = gconfig.base_dir
        excel_path, output_dir = cls.load_paths(gconfig, resolved_base_dir, domain)
        if not os.path.isfile(excel_path):
            raise FileNotFoundError(f"服务通信矩阵不存在: {excel_path}")
        cached_workbook = open_workbook_cached(excel_path, workbook_cache=workbook_cache)
        variables_list: list[dict[str, Any]] = []
        server_check_entry_count = 0
        try:
            server_check_entries = SOANodeServerCheckUtility.read_entries_from_workbook(
                cached_workbook.workbook
            )
            server_check_entry_count = len(server_check_entries) + 1
            server_check_block = SOANodeServerCheckUtility.render_server_check_block(
                server_check_entries
            )
            variables_list = cls.read_variables_list_from_workbook(cached_workbook.workbook)
            cls.render_nodes_to_files(
                variables_list,
                output_dir,
                server_check_block=server_check_block,
            )
        finally:
            if cached_workbook.should_close:
                cached_workbook.workbook.close()
        logger.log(
            PROGRESS_LEVEL,
            "SOA 生成完成：%s 个节点文件，输出目录: %s，ServerCheck 条目: %s",
            len(variables_list),
            output_dir,
            server_check_entry_count,
        )
        return gconfig

    @staticmethod
    def run_setserver_cin_generation(
        excel_path: str,
        anchor_path: str,
        project_base_dir: str,
    ) -> str:
        """根据 Service_Interface 工作表生成 ``SOA_StartSetserver.cin``。"""
        return SOASetServerCinGenerator(
            anchor_path=anchor_path,
            project_base_dir=project_base_dir,
        ).generate(excel_path)


if __name__ == "__main__":
    SOAGenerationUtility.run_generation()

