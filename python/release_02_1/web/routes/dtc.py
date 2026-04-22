#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DTC 域蓝图，注册前缀 **/api/dtc**。

与 ``POST /api/generate_dtc``（`common` + 全量 state + `get_dtc_generation_flags`）**不同**：
本路由**直接**将 JSON 中的 ``run_cin`` / ``run_did`` / ``run_soa`` 等传入
`TaskOrchestrator.run_dtc_bundle`；**不**在本路由内根据 Excel 路径自动推导开关。
主配置中 ``[DTC]`` 等节应已就绪（由 `StateConfigService` / 自动保存等写入）。

与 `web/routes/central` 的「可编程子步」设计对称，供脚本/测试/高级用法使用。
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
    """
    DTC 域生成：``TaskOrchestrator.run_dtc_bundle``，各子步是否执行由**请求体**显式指定（与编排器默认一致）。

    参数：JSON 体，键均可选：
        base_dir — 工程根，缺省为当前 `BASE_DIR`。
        run_can / run_xml — **默认** ``true``。
        run_cin / run_did / run_soa — **默认** ``false``；主界面一键生成时通常由
        ``/api/generate_dtc`` 经 state 推导出 ``true``，此处需自行传 ``true`` 才会跑对应步。
        validate_before_run — **默认** ``true``。

    返回：`jsonify_orchestrator_result` 成功（200）或失败（500 + ``detail``）。
    """
    payload = request.get_json(silent=True) or {}
    base_dir = payload.get("base_dir") or current_base_dir()
    run_can = payload.get("run_can", True)
    run_xml = payload.get("run_xml", True)
    run_cin = bool(payload.get("run_cin", False))
    run_did = bool(payload.get("run_did", False))
    run_soa = bool(payload.get("run_soa", False))
    validate_before_run = payload.get("validate_before_run", True)

    orch = TaskOrchestrator.from_base_dir(base_dir)
    result = orch.run_dtc_bundle(
        run_can=run_can,
        run_xml=run_xml,
        run_cin=run_cin,
        run_did=run_did,
        run_soa=run_soa,
        validate_before_run=validate_before_run,
    )
    return jsonify_orchestrator_result(result, success_separator=" / ", failure_message=None, failure_separator=" / ")

