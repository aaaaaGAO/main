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
from infra.filesystem.pathing import (
    RuntimePathResolver,
    resolve_configured_path,
    resolve_output_dir_relative_path,
)
from core.generator_config import GeneratorConfig
from generators.capl_soa.soa_setserver_cin import SOASetServerCinGenerator
from generators.capl_soa.soa_excel_utils import is_client_marker, normalize_cell_text, open_workbook_cached
from services.config_constants import (
    OPTION_OUTPUT_DIR,
    OPTION_SRV_EXCEL,
    OPTION_SRV_EXCEL_CANDIDATES,
)
from utils.logger import PROGRESS_LEVEL

SOA_LOGGER_NAME = "generate_soa_startsetserver"
logger = logging.getLogger(SOA_LOGGER_NAME)


def resolve_base_and_config(base_dir: str | None, config_path: str | None) -> GeneratorConfig:
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


def load_paths(gconfig: GeneratorConfig, base_dir: str, domain: str) -> tuple[str, str]:
    """读取 SOA 输入矩阵与输出目录。

    参数：
        gconfig：已加载配置对象。
        base_dir：项目根目录。
        domain：配置域名（通常 CENTRAL）。

    返回：
        `(excel_path, soa_output_dir)` 元组。其中 `soa_output_dir` 规则为：
        以用户配置 `output_dir` 的上一级目录为根，拼接 `public/ILNode/SOANode`。
    """
    srv_excel = ""
    for option_name in (OPTION_SRV_EXCEL, *OPTION_SRV_EXCEL_CANDIDATES):
        srv_excel = gconfig.get_from_section(domain, option_name, fallback="").strip()
        if srv_excel:
            break
    if not srv_excel:
        raise ValueError(f"未配置 [{domain}] srv_excel（服务通信矩阵）")
    output_dir = gconfig.get_required_from_section(domain, OPTION_OUTPUT_DIR).strip()
    excel_path = resolve_configured_path(base_dir, srv_excel)

    # SOA Node 路径规则：
    # 1) 取用户 output_dir 绝对路径；
    # 2) 取其上一级目录；
    # 3) 拼接 public/ILNode/SOANode；
    # 4) 若目标目录不存在则直接报错，不自动创建。
    soa_output_dir = resolve_output_dir_relative_path(
        base_dir,
        output_dir,
        ("public", "ILNode", "SOANode"),
        anchor_level="parent",
        required=True,
    )
    return excel_path, soa_output_dir


def read_variables_list_from_excel(
    excel_path: str,
    *,
    workbook_cache: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """从 Service_Deployment 工作表提取节点变量列表。

    参数：
        excel_path：服务通信矩阵 Excel 路径。
        workbook_cache：可选工作簿缓存；传入时优先复用已打开 workbook，
            并由调用方统一关闭。

    返回：
        节点变量字典列表，供模板渲染生成 `.can` 文件。
    """
    cached = open_workbook_cached(excel_path, workbook_cache=workbook_cache)
    workbook = cached.workbook
    if "Service_Deployment" not in workbook.sheetnames:
        error_message = f"服务通信矩阵缺少工作表 Service_Deployment: {cached.normalized_excel_path}"
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
        provider_node = normalize_cell_text(row[node_name_col]) if len(row) > node_name_col else ""
        service_id = normalize_cell_text(row[service_id_col]) if len(row) > service_id_col else ""
        instance_id = normalize_cell_text(row[instance_id_col]) if len(row) > instance_id_col else ""
        major = normalize_cell_text(row[major_col]) if len(row) > major_col else ""
        minor = normalize_cell_text(row[minor_col]) if len(row) > major_col else ""
        protocol = normalize_cell_text(row[protocol_col]) if len(row) > protocol_col else ""
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
                        {"ServiceId": "0x0000", "InstanceId": "0x00", "Major": "0x00", "Minor": "0x00"}
                    ],
                    "ConsumedServiceList": [
                        {"ServiceId": "0x0000", "InstanceId": "0x00", "Major": "0x00", "Minor": "0x00"}
                    ],
                }
            node_data[consumer_node]["ConsumedServiceList"].append(
                {"ServiceId": service_id, "InstanceId": instance_id, "Major": major, "Minor": minor}
            )

    if cached.should_close:
        workbook.close()
    for node in node_data.values():
        node["ProvidedServiceListNum"] = str(len(node["ProvidedServiceList"]))
        node["ConsumedServiceListNum"] = str(len(node["ConsumedServiceList"]))
    return list(node_data.values())


def render_nodes_to_files(variables_list: list[dict[str, Any]], output_dir: str) -> None:
    """将节点变量列表渲染并写入 SOA Node 文件。

    参数：
        variables_list：节点变量数据列表。
        output_dir：输出目录。

    返回：无。
    """
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
    template = env.get_template("Node.template")
    for variables in variables_list:
        output_path = os.path.join(output_dir, f"{variables['NodeName']}.can")
        rendered = template.render(**variables)
        with open(output_path, "w", encoding="utf-8-sig", newline="\r\n") as file_obj:
            file_obj.write(rendered)


def run_generation(
    config_path: str | None = None,
    base_dir: str | None = None,
    domain: str = "CENTRAL",
    *,
    workbook_cache: dict[str, Any] | None = None,
) -> GeneratorConfig:
    """执行 SOA 节点生成主流程。

    参数：
        config_path：可选配置路径。
        base_dir：可选项目根目录。
        domain：生成域，默认 `CENTRAL`。
        workbook_cache：可选工作簿缓存字典；用于同一流程内复用已打开 Excel。

    返回：
        本流程已加载的 `GeneratorConfig` 实例，供调用方复用，避免同一次任务内再次 `load`。
    """
    gconfig = resolve_base_and_config(base_dir, config_path)
    resolved_base_dir = gconfig.base_dir
    excel_path, output_dir = load_paths(gconfig, resolved_base_dir, domain)
    if not os.path.isfile(excel_path):
        raise FileNotFoundError(f"服务通信矩阵不存在: {excel_path}")
    variables_list = read_variables_list_from_excel(excel_path, workbook_cache=workbook_cache)
    render_nodes_to_files(variables_list, output_dir)
    logger.log(PROGRESS_LEVEL, "SOA 生成完成：%s 个节点文件，输出目录: %s", len(variables_list), output_dir)
    return gconfig


def run_setserver_cin_generation(excel_path: str, anchor_path: str) -> str:
    """根据 Service_Interface 工作表生成 ``SOA_StartSetserver.cin``。

    参数：
        excel_path — 接口定义 Excel（须含 ``Service_Interface`` 表）。
        anchor_path — 锚点路径；将其视为 `output_dir`（文件则取所在目录），
            并按严格模式写入 ``output_dir/TESTmode``。

    返回：
        已写入文件的绝对路径。
    """
    return SOASetServerCinGenerator(anchor_path=anchor_path).generate(excel_path)


class SOAGenerationUtility:
    """SOA 生成入口能力统一工具类。"""

    normalize_text = staticmethod(normalize_cell_text)
    resolve_base_and_config = staticmethod(resolve_base_and_config)
    load_paths = staticmethod(load_paths)
    read_variables_list_from_excel = staticmethod(read_variables_list_from_excel)
    render_nodes_to_files = staticmethod(render_nodes_to_files)
    run_generation = staticmethod(run_generation)
    run_setserver_cin_generation = staticmethod(run_setserver_cin_generation)


def run_cli(
    config_path: str | None = None,
    base_dir: str | None = None,
    domain: str = "CENTRAL",
) -> None:
    """命令行入口封装。

    参数：
        config_path：可选配置路径。
        base_dir：可选项目根目录。
        domain：生成域。

    返回：无。
    """
    run_generation(config_path=config_path, base_dir=base_dir, domain=domain)


if __name__ == "__main__":
    run_cli()

