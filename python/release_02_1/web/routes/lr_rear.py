#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LR_REAR 业务路由（蓝图）

当前实现：
- 提供一个简单的“生成 CAN”接口，内部通过 TaskService 调用 generators.capl_can.entrypoint.main

后续可以在这里继续扩展：
- 生成 XML
- 一键生成 CAN + XML + CIN
- 获取/保存 LR_REAR 页面相关配置（可以配合 ConfigService）
"""

from __future__ import annotations

import os

from flask import Blueprint, current_app, jsonify, request

from services.config_service import ConfigService
from services.task_orchestrator import TaskOrchestrator

lr_rear_bp = Blueprint("lr_rear", __name__)


def _base_dir() -> str:
    """获取当前请求对应的项目根目录（与 common 一致）。
    参数：无。
    返回：工程根目录绝对路径。
    """
    return current_app.config.get("BASE_DIR", "") or os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


@lr_rear_bp.route("/generate/can", methods=["POST"])
def generate_can():
    """生成 LR_REAR 域 CAN 文件：通过 TaskOrchestrator.run_lr_bundle(run_can=True) 执行。
    请求体（JSON，可选）：base_dir — 工程根目录；config_path — 配置文件路径。
    返回：200 时 {"success": True, "message": ...}；500 时 {"success": False, "message", "detail"}。
    """
    payload = request.get_json(silent=True) or {}
    base_dir = payload.get("base_dir") or _base_dir()
    config_path = payload.get("config_path")

    orch = TaskOrchestrator.from_base_dir(base_dir, config_path=config_path)
    result = orch.run_lr_bundle(run_can=True)

    if not result.success:
        return jsonify({
            "success": False,
            "message": result.messages[0] if result.messages else "生成失败",
            "detail": result.detail,
        }), 500
    return jsonify({"success": True, "message": result.messages[0] if result.messages else "CAN 生成完成"})


@lr_rear_bp.route("/config", methods=["POST"])
def save_lr_rear_config():
    """保存 LR_REAR 配置（第一页主表单）：将请求体字段写入 Configuration.txt 的 [LR_REAR] 节。
    请求体（JSON）：base_dir、levels、platforms、models、out_root、selected_sheets、log_level、can_input、didinfo_excel、cin_excel 等，仅写入提供的键。
    返回：200 时 {"success": True, "message": "LR_REAR 配置已保存"}；400 时未提供可写字段或非 JSON。
    """
    if not request.is_json:
        return jsonify({"success": False, "message": "需要 JSON 请求体"}), 400

    payload = request.get_json() or {}
    base_dir = payload.get("base_dir") or _base_dir()

    svc = ConfigService.from_base_dir(base_dir)

    # 映射前端字段到 [LR_REAR] 下的键
    lr_data = {}

    levels = payload.get("levels")
    if levels is not None:
        lr_data["case_levels"] = levels if levels.strip() else "ALL"

    platforms = payload.get("platforms")
    if platforms is not None:
        lr_data["case_platforms"] = platforms.strip()

    models = payload.get("models")
    if models is not None:
        lr_data["case_models"] = models.strip()

    out_root = payload.get("out_root")
    if out_root is not None:
        lr_data["output_dir"] = out_root.strip()

    selected_sheets = payload.get("selected_sheets")
    if selected_sheets is not None:
        lr_data["selected_sheets"] = selected_sheets.strip()

    log_level = (payload.get("log_level") or "").strip().lower()
    if log_level in ("info", "warning", "error"):
        lr_data["log_level_min"] = log_level

    can_input = payload.get("can_input")
    if can_input is not None:
        lr_data["input_excel"] = can_input.strip()

    didinfo_excel = payload.get("didinfo_excel")
    if didinfo_excel is not None and didinfo_excel.strip():
        lr_data["didinfo_inputs"] = f"{didinfo_excel.strip()} | *"

    cin_excel = payload.get("cin_excel")
    if cin_excel is not None and cin_excel.strip():
        lr_data["cin_input_excel"] = cin_excel.strip()

    if not lr_data:
        return jsonify({"success": False, "message": "未提供任何可写入的 LR_REAR 字段"}), 400

    svc.save_lr_rear(lr_data)
    return jsonify({"success": True, "message": "LR_REAR 配置已保存"})


