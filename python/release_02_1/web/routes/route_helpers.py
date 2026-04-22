#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路由层共享辅助函数。

供各蓝图在返回 JSON 前复用：解析 Flask 上下文中的项目根、把 `TaskOrchestrator` 的
`OrchestratorResult` 统一格式化为 `jsonify` 成功/失败响应，避免在多个路由中重复分支逻辑。
"""

from __future__ import annotations

from flask import current_app, jsonify
from infra.filesystem import get_project_root


def get_base_dir(current_file: str) -> str:
    """从 Flask 应用配置或路径解析器得到工程根目录。

    参数：
        current_file — 调用方 `__file__` 等参考路径，用于在缺少 `BASE_DIR` 时回退解析。

    返回：工程根绝对路径字符串。
    """
    return current_app.config.get("BASE_DIR", "") or get_project_root(current_file)


def jsonify_orchestrator_result(
    result,
    *,
    success_separator: str = " / ",
    failure_message: str | None = None,
    failure_separator: str = " / ",
    success_fallback: str = "生成完成",
):
    """将 `OrchestratorResult` 转为 `jsonify` 元组 (Response, status_code)。

    参数：
        result — 编排结果对象，需含 `success: bool`、`messages: list[str]`、`detail: str`。
        success_separator — 成功时合并 `messages` 的分隔符。
        failure_message — 失败时若提供，则覆盖为对外 `message`；为 None 时用 `failure_separator` 拼 `messages`。
        failure_separator — 失败时合并 `messages` 的分隔符。
        success_fallback — 成功但 `messages` 为空时使用的默认文案。

    返回：`(Response, 500)` 当 `not result.success`；否则成功 JSON，HTTP 200（Flask 默认）。
    """
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
