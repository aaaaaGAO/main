#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中央域业务路由（central_bp）

当前实现（第一阶段）：
- 提供一个“生成中央域 CAN+XML”的接口，内部通过 TaskService 调用 CAN / XML 生成脚本。

说明：
- 这里假定当前主配置文件已由其他接口（如原 /api/save_preset 或未来的中央域配置接口）写好，
  本路由只负责触发生成任务。
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
    """中央域生成入口：通过 TaskOrchestrator.run_central_bundle 执行 UART(可选) → CAN → XML。
    请求体（JSON，可选）：base_dir — 工程根目录；run_can / run_xml / run_uart — 是否执行对应步骤，默认 True；
    validate_before_run — 是否先做运行前校验，默认 True。
    返回：200 时 {"success": True, "message": ...}；500 时 {"success": False, "message", "detail"}。
    """
    payload = request.get_json(silent=True) or {}
    base_dir = payload.get("base_dir") or current_base_dir()
    run_can = payload.get("run_can", True)
    run_xml = payload.get("run_xml", True)
    run_uart = payload.get("run_uart", True)
    validate_before_run = payload.get("validate_before_run", True)

    orch = TaskOrchestrator.from_base_dir(base_dir)
    result = orch.run_central_bundle(
        run_can=run_can,
        run_xml=run_xml,
        run_uart=run_uart,
        validate_before_run=validate_before_run,
    )
    return jsonify_orchestrator_result(result, success_separator=" / ", failure_message=None, failure_separator=" / ")

