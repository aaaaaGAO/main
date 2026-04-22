#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中央域（CENTRAL）蓝图，注册前缀 **/api/central**（见 `web.create_app`）。

与 ``POST /api/generate_central``（`common` + `GenerationRouteService` + 全量 state 落盘）**不同**：
本路由为**可编程**子集入口，请求体**直接**传入 ``run_can`` / ``run_xml`` / ``run_uart`` / ``run_soa`` 等
布尔开关，由 `TaskOrchestrator.run_central_bundle` 执行；**不**在路由内调 `StateConfigService`
合并页面 state —— 主配置需已由其它接口或手工写好。

适用场景：集成测试、外部脚本、或只重跑子步骤时显式传参。
"""

from __future__ import annotations

from flask import Blueprint, request

from services.task_orchestrator import TaskOrchestrator
from .route_helpers import get_base_dir, jsonify_orchestrator_result

central_bp = Blueprint("central", __name__)


def current_base_dir() -> str:
    """获取当前请求对应的项目根目录（与 common 一致）。
    参数：无。
    返回：工程根目录绝对路径。
    """
    return get_base_dir(__file__)


@central_bp.route("/generate", methods=["POST"])
def generate_central():
    """
    中央域生成：``TaskOrchestrator.run_central_bundle``，顺序与编排器实现一致（如 UART 条件、CAN、XML、SOA）。

    参数：JSON 体，键均可选：
        base_dir — 工程根，缺省为当前 `BASE_DIR`。
        run_can / run_xml — 是否跑 CAN、XML 步，**默认** ``true``。
        run_uart / run_soa — 子步开关，**默认** ``false``（需显式 ``true`` 与主界面「有矩阵/有路径」时一致）。
        validate_before_run — 是否先跑 `run_validator` 域校验，**默认** ``true``。

    返回：`jsonify_orchestrator_result` 统一成功 JSON（200）或失败（500 及 ``detail``）。
    """
    payload = request.get_json(silent=True) or {}
    base_dir = payload.get("base_dir") or current_base_dir()
    run_can = payload.get("run_can", True)
    run_xml = payload.get("run_xml", True)
    run_uart = bool(payload.get("run_uart", False))
    run_soa = bool(payload.get("run_soa", False))
    validate_before_run = payload.get("validate_before_run", True)

    orch = TaskOrchestrator.from_base_dir(base_dir)
    result = orch.run_central_bundle(
        run_can=run_can,
        run_xml=run_xml,
        run_uart=run_uart,
        run_soa=run_soa,
        validate_before_run=validate_before_run,
    )
    return jsonify_orchestrator_result(result, success_separator=" / ", failure_message=None, failure_separator=" / ")

