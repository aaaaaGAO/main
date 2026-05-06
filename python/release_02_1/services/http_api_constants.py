#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web / 路由服务层共用的 HTTP 状态码与标准 JSON 响应构造。

职责：
- 集中定义常用 HTTP 状态码（避免在业务返回值里散落 200/400/500）；

- 提供 ``api_success`` / ``api_error`` 组装 ``(dict, status)``；另提供 ``api_success_dict`` /
  ``api_error_dict`` 仅返回 dict，供 `GuiService` 等不经 HTTP 的服务复用同一套字段约定；

- 定义响应字段名字符串常量，便于与 `services.request_payload_utils.client_error_body` 等保持一致。

不参与 Flask ``jsonify``；调用方在服务层组装 dict 后在路由层再 ``jsonify``。
"""

from __future__ import annotations

from typing import Any

# ---------- JSON 键名（与现有前端/API 契约一致）----------
RESPONSE_KEY_SUCCESS = "success"
RESPONSE_KEY_MESSAGE = "message"
RESPONSE_KEY_DETAIL = "detail"
RESPONSE_KEY_DATA = "data"
# ---------- 经由 ``api_success(..., extra=...)`` 等合并到顶层的约定键 ----------
RESPONSE_KEY_OUTPUT_PATH = "output_path"
RESPONSE_KEY_PATH = "path"
RESPONSE_KEY_FILENAME = "filename"
RESPONSE_KEY_FILEPATH = "filepath"
RESPONSE_KEY_PORTS = "ports"
# ---------- 串口枚举项：`ports` 列表元素内字段 ----------
RESPONSE_KEY_PORT_DEVICE = "port"
RESPONSE_KEY_PORT_DESCRIPTION = "description"


class HttpStatus:
    """路由服务层常用的 HTTP 状态码整型常量。"""

    OK = 200
    BAD_REQUEST = 400
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_SERVER_ERROR = 500


# 兼容旧导入名（与各服务层已替换的常量等价）
HTTP_OK = HttpStatus.OK
HTTP_BAD_REQUEST = HttpStatus.BAD_REQUEST
HTTP_INTERNAL_SERVER_ERROR = HttpStatus.INTERNAL_SERVER_ERROR


def make_json_tuple(response_body: dict[str, Any], http_status: int) -> tuple[dict[str, Any], int]:
    """将已构造好的响应体与安全 HTTP 状态码组成服务层返回值元组。"""
    return response_body, http_status


def api_success(
    message: str | None = None,
    *,
    data: Any | None = None,
    extra: dict[str, Any] | None = None,
    status: int | None = None,
) -> tuple[dict[str, Any], int]:
    """构造统一成功响应：``({"success": True, ...}, status)``.

    - 仅当 ``message`` 非 ``None`` 时写入 ``message`` 键（避免破坏仅含 ``data`` 的旧契约）。

    - 仅当 ``data`` 不为 ``None`` 时写入 ``data`` 键。

    - ``extra`` 中的键会直接合并入响应 dict（用于 ``output_path``、``filepath``、``ports`` 等）。
    """
    body: dict[str, Any] = {RESPONSE_KEY_SUCCESS: True}
    if message is not None:
        body[RESPONSE_KEY_MESSAGE] = message
    if data is not None:
        body[RESPONSE_KEY_DATA] = data
    if extra:
        body.update(extra)
    http_status = status if status is not None else HttpStatus.OK
    return body, http_status


def api_error(
    message: str,
    *,
    detail: str | None = None,
    status: int | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    """构造统一失败响应：``({"success": False, "message": ...}, status)``."""
    http_status = status if status is not None else HttpStatus.BAD_REQUEST
    body: dict[str, Any] = {RESPONSE_KEY_SUCCESS: False, RESPONSE_KEY_MESSAGE: message}
    if detail:
        body[RESPONSE_KEY_DETAIL] = detail
    if extra:
        body.update(extra)
    return body, http_status


def api_success_dict(
    message: str | None = None,
    *,
    data: Any | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """同 `api_success`，仅返回 JSON 体（无状态码），供 GUI/解析等不接触 Flask 的调用方。"""
    body, _ = api_success(message, data=data, extra=extra)
    return body


def api_error_dict(
    message: str,
    *,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """同 `api_error` 的 body 部分（状态码由路由层单独指定），与 `client_error_body` 契约一致。"""
    body, _ = api_error(message, detail=detail, extra=extra)
    return body
