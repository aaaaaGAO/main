#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
左右后域（LR_REAR）蓝图，URL 前缀由 `web.create_app` 注册为 **/api/lr**。

与 `web.routes.common` 中 ``POST /api/generate``（整包一键生成）**并行**：本文件提供**颗粒度更细**的 API，
便于脚本或未来前端单独触「只跑 CAN」或**仅保存**第一页配置；底层仍走 `TaskOrchestrator` /
`ConfigService`，与《架构》中 `lr_rear` 路由表一致。

当前路由：
- ``POST /api/lr/generate/can`` — 调 `run_lr_bundle(run_can=True)`；**未**覆盖其它参数时
  与编排器默认一致（``run_xml`` 仍为 **True**，会跑 XML；CIN/DID/SOA 默认 False、无 UART）。名称偏历史，不等价「仅 CAN」。
- ``POST /api/lr/config`` — 将 JSON 中 LR 相关字段写入主配置 ``[LR_REAR]`` 节（经 `ConfigService`）。
"""

from __future__ import annotations

from flask import Blueprint, request

from services.config_service import ConfigService
from services.http_api_constants import HttpStatus, api_error, api_success
from services.task_orchestrator import TaskOrchestrator
from .route_helpers import get_base_dir, jsonify_orchestrator_result, jsonify_route_result

lr_rear_bp = Blueprint("lr_rear", __name__)


def current_base_dir() -> str:
    """获取当前请求对应的项目根目录（与 common 一致）。
    参数：无。
    返回：工程根目录绝对路径。
    """
    return get_base_dir(__file__)


@lr_rear_bp.route("/generate/can", methods=["POST"])
def generate_can():
    """
    左右后域生成入口：``TaskOrchestrator.run_lr_bundle(run_can=True)``，其它布尔参数**未传**时取
    `run_lr_bundle` **默认值**（当前实现：``run_xml`` 默认 **True** 会执行 XML；``run_cin`` /
    ``run_did`` / ``run_soa`` 默认 False；UART 在 LR 域恒为不跑）。路径名 `generate_can` 为历史命名。

    参数：JSON 体，可选键：
        base_dir — 工程根；缺省为当前应用 ``BASE_DIR``（见 `get_base_dir`）。
        config_path — 主配置文件路径；缺省为 ``ConfigManager`` 按工程根解析的默认 `Configuration.ini`。

    返回：由 `jsonify_orchestrator_result` 统一包装；成功约 ``{"success": true, "message": ...}``，
    失败 500 且含 ``detail``（与 `route_helpers` 一致）。
    """
    payload = request.get_json(silent=True) or {}
    base_dir = payload.get("base_dir") or current_base_dir()
    config_path = payload.get("config_path")

    orch = TaskOrchestrator.from_base_dir(base_dir, config_path=config_path)
    result = orch.run_lr_bundle(run_can=True)
    return jsonify_orchestrator_result(
        result,
        success_separator=" / ",
        failure_message=None,
        failure_separator=" / ",
        success_fallback="CAN 生成完成",
    )


@lr_rear_bp.route("/config", methods=["POST"])
@jsonify_route_result
def save_lr_rear_config():
    """
    将前端采集的 **LR 第一页** 字段经 `ConfigService.build_lr_rear_section_data` 清洗后，写入
    主配置 ``[LR_REAR]``（`save_lr_rear`），不经过 ``StateConfigService`` 全量 state 路径。

    参数：**必须** `Content-Type: application/json`。键可含
    ``base_dir``、``levels``、``platforms``、``models``、``out_root``、``selected_sheets``、
    ``log_level``、``can_input``、``didinfo_excel``、``cin_excel`` 等；仅**出现且可映射**的项写入，空请求体
    或无可映射字段时 400。

    返回：200 为 API 成功体与 ``HttpStatus.OK``；400 为 ``HttpStatus.BAD_REQUEST`` 与错误 ``message``（由 ``jsonify_route_result`` 统一 ``jsonify``）。
    """
    if not request.is_json:
        return api_error("需要 JSON 请求体", status=HttpStatus.BAD_REQUEST)

    payload = request.get_json() or {}
    base_dir = payload.get("base_dir") or current_base_dir()

    svc = ConfigService.from_base_dir(base_dir)
    lr_data = svc.build_lr_rear_section_data(payload)

    if not lr_data:
        return api_error("未提供任何可写入的 LR_REAR 字段", status=HttpStatus.BAD_REQUEST)

    svc.save_lr_rear(lr_data)
    return api_success("LR_REAR 配置已保存")


