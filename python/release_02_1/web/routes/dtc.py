#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DTC 业务路由（dtc_bp）

当前实现（第一阶段）：
- 提供一个“生成 DTC CAN+XML”的接口，内部通过 TaskService 调用 CAN / XML 生成脚本。

说明：
- 与中央域类似，这里只负责触发生成；具体的 DTC 配置写入仍由现有逻辑负责，
  后续可以逐步迁移到 services/config_service.py。
"""

from __future__ import annotations

from flask import Blueprint, request

from services.task_orchestrator import TaskOrchestrator
from .route_helpers import get_base_dir, jsonify_orchestrator_result

dtc_bp = Blueprint("dtc", __name__)


def current_base_dir() -> str:
    """获取当前请求对应的项目根目录（与 common 一致）。
    参数：无。
    返回：工程根目录绝对路径。
    """
    return get_base_dir(__file__)


@dtc_bp.route("/generate", methods=["POST"])
def generate_dtc():
    """DTC 域生成入口：通过 TaskOrchestrator.run_dtc_bundle 执行 DIDConfig → DIDInfo → CIN → CAN → XML（按配置与开关）。
    请求体（JSON，可选）：base_dir — 工程根目录；run_can / run_xml / run_cin / run_did — 是否执行对应步骤，默认 True；
    validate_before_run — 是否先做运行前校验，默认 True。
    返回：200 时 {"success": True, "message": ...}；500 时 {"success": False, "message", "detail"}。
    """
    payload = request.get_json(silent=True) or {}
    base_dir = payload.get("base_dir") or current_base_dir()
    run_can = payload.get("run_can", True)
    run_xml = payload.get("run_xml", True)
    run_cin = payload.get("run_cin", True)
    run_did = payload.get("run_did", True)
    validate_before_run = payload.get("validate_before_run", True)

    orch = TaskOrchestrator.from_base_dir(base_dir)
    result = orch.run_dtc_bundle(
        run_can=run_can,
        run_xml=run_xml,
        run_cin=run_cin,
        run_did=run_did,
        validate_before_run=validate_before_run,
    )
    return jsonify_orchestrator_result(result, success_separator=" / ", failure_message=None, failure_separator=" / ")

