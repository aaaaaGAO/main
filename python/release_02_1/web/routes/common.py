#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Common 蓝图：跨 Tab 的通用 HTTP API（前缀 `/api`）。

提供：健康/心跳、加载配置与筛选项、Tk 文件选择、文件结构解析、串口列表、
自动保存、LR/中央/DTC 一键生成、预设保存/导入。具体业务在 `CommonUiRouteService`、
`GenerationRouteService` 中实现；本文件只注册 `Blueprint` 与薄封装，符合「路由仅分发」
约定（见 `docs/架构.txt`）。
"""

from __future__ import annotations

import logging
import time

from flask import Blueprint, jsonify, request

from services.generation_route_service import (
    GenerationRouteOptions,
    generation_route_options_central,
    generation_route_options_dtc,
    generation_route_options_lr_rear,
    safe_execute_generation_from_payload_fetch,
)
from services.common_ui_route_service import CommonUiRouteService
from .route_helpers import get_base_dir

common_bp = Blueprint("common", __name__)
logger = logging.getLogger(__name__)


def current_base_dir() -> str:
    """从 Flask 配置或路径解析器得到本应用使用的工程根目录（与 `app.config['BASE_DIR']` 一致）。

    参数：无。

    返回：工程根绝对路径字符串。
    """
    return get_base_dir(__file__)


def common_ui_route_service() -> CommonUiRouteService:
    """构造绑定当前 `current_base_dir()` 的 `CommonUiRouteService`（无单例，按请求现建即可）。

    参数：无。返回：配置好根目录的 `CommonUiRouteService` 实例。
    """
    return CommonUiRouteService(current_base_dir())


@common_bp.route("/healthz", methods=["GET"])
def healthz():
    """健康检查：供负载/探针使用。

    参数：无。返回：HTTP 200，JSON 体含 ``status: ok`` 与服务器时间戳 ``ts``。
    """
    return jsonify({"status": "ok", "ts": time.time()})


@common_bp.route("/heartbeat", methods=["POST"])
def api_heartbeat():
    """前端定时心跳，供 `app.py` 中无活动监控等逻辑使用。

    参数：无（请求体可空）。返回：HTTP 200，``{"status": "alive"}``。
    """
    return jsonify({"status": "alive"})


@common_bp.route("/config/lr_rear", methods=["GET"])
def get_lr_rear_config():
    """读取并返回 `[LR_REAR]` 等与左右后域相关的 INI 片段，供页面初始化。

    参数：无。返回：``(jsonify 体, HTTP 状态码)`` 由 `lr_rear_config_result` 决定。
    """
    body, status_code = common_ui_route_service().lr_rear_config_result()
    return jsonify(body), status_code


@common_bp.route("/get_filter_options", methods=["GET"])
def get_filter_options():
    """读取 `config/filter_options.ini` 中等级/平台/车型等下拉项。

    参数：无。返回：``FilterService.parse_shaixuan_config`` 结构的 JSON 包装。
    """
    body, status_code = common_ui_route_service().filter_options_result()
    return jsonify(body), status_code


@common_bp.route("/load_config", methods=["GET"])
def load_config():
    """加载主配置/固定配置并组合为前端所需的大块 state 结构。

    参数：无。返回：含 ``success`` / ``data`` 的 JSON 与状态码。
    """
    body, status_code = common_ui_route_service().load_config_result()
    return jsonify(body), status_code


@common_bp.route("/select_file", methods=["POST"])
def select_file():
    """在服务端线程中弹出 Tk 文件/文件夹选择对话框，返回所选绝对路径。

    参数：JSON 体可选字段 ``file_type``：``"file"`` 或 ``"folder"``，缺省为文件。

    返回：``success`` 与 ``path`` 等字段；失败时含错误信息。
    """
    payload = request.get_json(silent=True) or {}
    body, status_code = common_ui_route_service().select_file_result(payload)
    return jsonify(body), status_code


@common_bp.route("/parse_file_structure", methods=["POST"])
def parse_file_structure():
    """解析指定 Excel/目录下列表/Sheet 等结构，供前端树形展示或校验。

    参数：JSON 体须含 ``path``：待解析的绝对或相对路径。

    返回：``GuiService`` 结构解析结果 JSON 与状态码。
    """
    payload = request.get_json(silent=True) or {}
    body, status_code = common_ui_route_service().parse_file_structure_result(payload)
    return jsonify(body), status_code


def execute_generation_route(options: GenerationRouteOptions):
    """
    各域「一键生成」路由的公共实现：读当前 `request` 的 JSON，交给 `safe_execute_generation_from_payload_fetch`。

    参数：options — 含域标识、编排方法名、成功/失败提示文案等的 `GenerationRouteOptions`。

    返回：``(Response, status_code)`` 元组，供直接 `return`。
    """
    response_payload, status_code = safe_execute_generation_from_payload_fetch(
        lambda: request.get_json(silent=True) or {},
        base_dir=current_base_dir(),
        options=options,
        route_logger=logger,
    )
    return jsonify(response_payload), status_code


@common_bp.route("/get_serial_ports", methods=["GET"])
def get_serial_ports():
    """枚举当前环境可用串口（供 UART/通信配置下拉）。

    参数：无。返回：``ports`` 列表等 JSON 与状态码。
    """
    body, status_code = common_ui_route_service().serial_ports_result()
    return jsonify(body), status_code


@common_bp.route("/auto_save_config", methods=["POST"])
def auto_save_config():
    """将多 Tab 合并 state 经 `StateConfigService` 写回主配置（可含仅 data 内对象）。

    参数：JSON 体，通常含 ``data``：当前全量或增量 state。

    返回：``success`` / 错误信息及 HTTP 状态码。
    """
    payload = request.get_json(silent=True) or {}
    body, status_code = common_ui_route_service().auto_save_config_result(payload)
    return jsonify(body), status_code


@common_bp.route("/generate", methods=["POST"])
def generate():
    """左右后域一键生成：编排 CAN/XML/条件 DID·CIN·SOA 等（不含 UART 步，见 `TaskOrchestrator`）。

    参数：JSON 含 ``data`` 或全包 state；可选 ``validate_before_run``。

    返回：编排器统一 JSON 与 HTTP 状态码。
    """
    return execute_generation_route(generation_route_options_lr_rear())


@common_bp.route("/generate_central", methods=["POST"])
def generate_central():
    """中央域一键生成：含条件 UART 矩阵与 SOA 等（与 `get_central_generation_flags` 一致）。

    参数：同 `generate`。

    返回：编排器统一 JSON 与状态码。
    """
    return execute_generation_route(generation_route_options_central())


@common_bp.route("/generate_dtc", methods=["POST"])
def generate_dtc():
    """DTC 域一键生成：DID/IO/ConfigEnum 等路径经 `sync_dtc_domain_inputs` 已写入配置后编排。

    参数：同 `generate`。

    返回：编排器统一 JSON 与状态码。
    """
    return execute_generation_route(generation_route_options_dtc())


@common_bp.route("/save_preset", methods=["POST"])
def save_preset():
    """将当前 state 另存为预设 JSON/路径（由 `CommonUiRouteService` 实现具体路径策略）。

    参数：JSON 体含要保存的 ``data`` 等。

    返回：``success``、生成文件路径或错误信息。
    """
    payload = request.get_json(silent=True) or {}
    body, status_code = common_ui_route_service().save_preset_result(payload)
    return jsonify(body), status_code


@common_bp.route("/import_preset", methods=["POST"])
def import_preset():
    """从用户选择的预设文件读回 state，供页面填充。

    参数：无（或按服务层约定由对话框完成路径选择）。返回：新 state 或错误 JSON。
    """
    body, status_code = common_ui_route_service().import_preset_result()
    return jsonify(body), status_code


