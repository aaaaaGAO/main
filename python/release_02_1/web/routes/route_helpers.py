#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路由层共享 helper。"""

from __future__ import annotations

from flask import current_app, jsonify
from infra.filesystem import get_project_root


def get_base_dir(current_file: str) -> str:
    """获取当前请求对应的项目根目录。"""
    return current_app.config.get("BASE_DIR", "") or get_project_root(current_file)


def jsonify_orchestrator_result(
    result,
    *,
    success_separator: str = " / ",
    failure_message: str | None = None,
    failure_separator: str = " / ",
    success_fallback: str = "生成完成",
):
    """将编排器结果转换为统一 JSON 响应。"""
    if not result.success:
        message = failure_message if failure_message is not None else failure_separator.join(result.messages)
        return jsonify({
            "success": False,
            "message": message,
            "detail": result.detail,
        }), 500
    return jsonify({
        "success": True,
        "message": success_separator.join(result.messages) if result.messages else success_fallback,
    })
