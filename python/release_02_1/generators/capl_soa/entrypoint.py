#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOA Node 生成入口（中央域）：
从服务通信矩阵 Excel（Service_Deployment）生成 ILNode/SOANode/*.can。
"""

from __future__ import annotations

import os
from typing import Any

from jinja2 import Environment, FileSystemLoader
from infra.excel.workbook import ExcelService
from infra.filesystem.pathing import (
    RuntimePathResolver,
    resolve_configured_path,
    resolve_target_subdir,
)
from core.generator_config import GeneratorConfig
from services.config_constants import OPTION_OUTPUT_DIR


def _str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _resolve_base_and_config(base_dir: str | None, config_path: str | None) -> GeneratorConfig:
    resolved_base_dir = RuntimePathResolver.resolve_base_dir(__file__, base_dir)
    resolved_config_path = RuntimePathResolver.resolve_config_path(resolved_base_dir, config_path)
    return GeneratorConfig(resolved_base_dir, config_path=resolved_config_path).load()


def _load_paths(gconfig: GeneratorConfig, base_dir: str, domain: str) -> tuple[str, str]:
    srv_excel = (
        gconfig.get_from_section(domain, "srv_excel", fallback="")
        or gconfig.get_from_section(domain, "Srv_Excel", fallback="")
    ).strip()
    if not srv_excel:
        raise ValueError(f"未配置 [{domain}] srv_excel（服务通信矩阵）")
    output_dir = gconfig.get_required_from_section(domain, OPTION_OUTPUT_DIR).strip()
    excel_path = resolve_configured_path(base_dir, srv_excel)
    # 与 Configuration 路径策略保持一致：目录不存在时直接报错，不自动创建。
    ilnode_dir = resolve_target_subdir(base_dir, output_dir, "ILNode")
    soa_output_dir = resolve_target_subdir(ilnode_dir, ".", "SOANode")
    return excel_path, soa_output_dir


def _read_variables_list_from_excel(excel_path: str) -> list[dict[str, Any]]:
    workbook = ExcelService.open_workbook(excel_path, data_only=True, read_only=False)
    if "Service_Deployment" not in workbook.sheetnames:
        workbook.close()
        raise ValueError(f"服务通信矩阵缺少工作表 Service_Deployment: {excel_path}")
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
        provider_node = _str(row[node_name_col]) if len(row) > node_name_col else ""
        service_id = _str(row[service_id_col]) if len(row) > service_id_col else ""
        instance_id = _str(row[instance_id_col]) if len(row) > instance_id_col else ""
        major = _str(row[major_col]) if len(row) > major_col else ""
        minor = _str(row[minor_col]) if len(row) > minor_col else ""
        protocol = _str(row[protocol_col]) if len(row) > protocol_col else ""
        port = _str(row[port_col]) if len(row) > port_col else ""

        if not provider_node or not service_id:
            continue

        protocol_value = "6" if protocol.upper() == "TCP" else "17"
        if provider_node not in node_data:
            node_data[provider_node] = {
                "NodeName": provider_node,
                "Protocol": protocol_value,
                "Port": port,
                "ProvidedServiceList": [
                    {"ServiceId": "0x0000", "InstanceId": "0x00", "Major": "0x00", "Minor": "0x00"}
                ],
                "ConsumedServiceList": [
                    {"ServiceId": "0x0000", "InstanceId": "0x00", "Major": "0x00", "Minor": "0x00"}
                ],
            }

        node_data[provider_node]["ProvidedServiceList"].append(
            {"ServiceId": service_id, "InstanceId": instance_id, "Major": major, "Minor": minor}
        )

        for col_index in range(consumer_start_col, sheet.max_column):
            consumer_node = _str(sheet.cell(row=2, column=col_index + 1).value)
            has_mark = len(row) > col_index and _str(row[col_index]).lower() == "x"
            if not consumer_node or not has_mark:
                continue
            if consumer_node not in node_data:
                node_data[consumer_node] = {
                    "NodeName": consumer_node,
                    "Protocol": protocol_value,
                    "Port": port,
                    "ProvidedServiceList": [
                        {"ServiceId": "0x0000", "InstanceId": "0x00", "Major": "0x00", "Minor": "0x00"}
                    ],
                    "ConsumedServiceList": [
                        {"ServiceId": "0x0000", "InstanceId": "0x00", "Major": "0x00", "Minor": "0x00"}
                    ],
                }
            node_data[consumer_node]["ConsumedServiceList"].append(
                {"ServiceId": service_id, "InstanceId": instance_id, "Major": major, "Minor": minor}
            )

    workbook.close()
    for node in node_data.values():
        node["ProvidedServiceListNum"] = str(len(node["ProvidedServiceList"]))
        node["ConsumedServiceListNum"] = str(len(node["ConsumedServiceList"]))
    return list(node_data.values())


def _render_nodes_to_files(variables_list: list[dict[str, Any]], output_dir: str) -> None:
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
    template = env.get_template("Node.template")
    for variables in variables_list:
        output_path = os.path.join(output_dir, f"{variables['NodeName']}.can")
        rendered = template.render(**variables)
        with open(output_path, "w", encoding="utf-8", newline="\r\n") as file_obj:
            file_obj.write(rendered)


def run_generation(
    config_path: str | None = None,
    base_dir: str | None = None,
    domain: str = "CENTRAL",
) -> None:
    gconfig = _resolve_base_and_config(base_dir, config_path)
    resolved_base_dir = gconfig.base_dir
    excel_path, output_dir = _load_paths(gconfig, resolved_base_dir, domain)
    if not os.path.isfile(excel_path):
        raise FileNotFoundError(f"服务通信矩阵不存在: {excel_path}")
    variables_list = _read_variables_list_from_excel(excel_path)
    _render_nodes_to_files(variables_list, output_dir)
    print(f"[soa] 生成完成：{len(variables_list)} 个节点文件，输出目录: {output_dir}")


def main(
    config_path: str | None = None,
    base_dir: str | None = None,
    domain: str = "CENTRAL",
) -> None:
    run_generation(config_path=config_path, base_dir=base_dir, domain=domain)


if __name__ == "__main__":
    main()

