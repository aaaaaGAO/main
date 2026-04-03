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

from flask import Blueprint, current_app, jsonify, request

from services.task_orchestrator import TaskOrchestrator
from .route_helpers import get_base_dir, jsonify_orchestrator_result

dtc_bp = Blueprint("dtc", __name__)


def _base_dir() -> str:
    """获取当前请求对应的项目根目录（与 common 一致）。
    参数：无。
    返回：工程根目录绝对路径。
    """
    return get_base_dir(__file__)


@dtc_bp.route("/generate", methods=["POST"])
def generate_dtc():
    """DTC 域生成入口：通过 TaskOrchestrator.run_dtc_bundle 执行 CAN + XML 生成。
    请求体（JSON，可选）：base_dir — 工程根目录；run_can / run_xml — 是否执行对应生成，默认 True。
    返回：200 时 {"success": True, "message": ...}；500 时 {"success": False, "message", "detail"}。
    """
    payload = request.get_json(silent=True) or {}
    base_dir = payload.get("base_dir") or _base_dir()
    run_can = payload.get("run_can", True)
    run_xml = payload.get("run_xml", True)

    orch = TaskOrchestrator.from_base_dir(base_dir)
    result = orch.run_dtc_bundle(run_can=run_can, run_xml=run_xml)
    return jsonify_orchestrator_result(result, success_separator=" / ", failure_message=None, failure_separator=" / ")

