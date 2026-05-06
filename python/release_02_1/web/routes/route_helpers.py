#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路由层共享辅助函数。

供各蓝图在返回 JSON 前复用：解析 Flask 上下文中的项目根、把 `TaskOrchestrator` 的
`OrchestratorResult` 统一格式化为 `jsonify` 成功/失败响应，避免在多个路由中重复分支逻辑。

另提供 ``jsonify_route_result``：**服务层约定的** ``tuple[dict, int]``（JSON 体 + HTTP 状态码）
在进入 Flask 时再 ``jsonify``，避免各处手写 ``return jsonify(body), status_code``。
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import current_app, jsonify
from infra.filesystem import get_project_root
from services.http_api_constants import HttpStatus, api_error, api_success

RouteJsonTupleFn = Callable[..., tuple[dict[str, Any], int]]


def get_base_dir(current_file: str) -> str:
    """从 Flask 应用配置或路径解析器得到工程根目录。

    参数：
        current_file — 调用方 `__file__` 等参考路径，用于在缺少 `BASE_DIR` 时回退解析。

    返回：工程根绝对路径字符串。
    """
    return current_app.config.get("BASE_DIR", "") or get_project_root(current_file)


def jsonify_route_result(view_fn: RouteJsonTupleFn) -> Callable[..., Any]:
    """将视图函数返回值由 ``(dict, status_code)`` 转为 ``jsonify(dict), status_code``。

    **用途**：与各 `CommonUiRouteService.*_result`、``soa_setserver_cin_result``、
    ``safe_execute_generation_from_payload_fetch`` 等服务层返回值对齐；装饰器紧贴视图定义、
    位于 ``@bp.route(...)`` **之下**（先套本装饰器，再注册路由时需把 ``route`` 写在最外层，见 ``common.py``）。

    **参数**：view_fn — 无额外约束的视图函数，须返回二元组 ``(Serializable dict, HTTP int)``。

    **返回**：包装后的视图，供 Flask ``return`` 使用。
    """
    @wraps(view_fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        body, status_code = view_fn(*args, **kwargs)
        return jsonify(body), status_code

    return wrapped


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

    返回：`not result.success` 时为 ``(Response, HttpStatus.INTERNAL_SERVER_ERROR)``；否则成功 JSON 与 ``HttpStatus.OK``。
    """
    if not result.success:
        message = failure_message if failure_message is not None else failure_separator.join(result.messages)
        body, status = api_error(
            message,
            detail=result.detail or None,
            status=HttpStatus.INTERNAL_SERVER_ERROR,
        )
        return jsonify(body), status
    body, status = api_success(
        success_separator.join(result.messages) if result.messages else success_fallback,
    )
    return jsonify(body), status
