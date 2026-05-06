#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务层路由结果装饰器（无 Flask / 无 request 依赖）。

在 `CommonUiRouteService` 等返回 ``tuple[dict, int]`` 的入口上，收敛重复的
``try/except Exception`` → ``client_error_body`` → ``make_json_tuple`` 样板，
与 `web.routes.route_helpers.jsonify_route_result`（负责 ``jsonify``）分层配合。

提供两类装饰器：
- `guard_service_route_tuple`：**实例方法**（首参绑定 ``self``）；
- `guard_plain_service_route_tuple`：**无 self** 的普通可调用对象（可用 ``functools.partial`` 绑定上下文），例如
  `generation_route_service.safe_execute_generation_from_payload_fetch` 的惰性 ``fetch_payload``。

仅处理**未捕获的业务外异常**；方法内部若需按业务返回 200+错误体或分支逻辑，仍手写即可。
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from services.http_api_constants import HttpStatus, make_json_tuple
from services.request_payload_utils import client_error_body

ServiceRouteTuple = tuple[dict[str, Any], int]


def guard_service_route_tuple(*, http_status_on_error: int = HttpStatus.INTERNAL_SERVER_ERROR) -> Callable:
    """返回一个装饰器：包装**实例方法**，在异常时统一返回错误体与给定 HTTP 状态码。

    **功能**：与方法体成功路径一致，仍须返回 ``tuple[dict, int]``；任意 ``Exception`` 时
    转为 ``make_json_tuple(client_error_body(str(e)), http_status_on_error)``。

    **参数**：
        http_status_on_error — 捕获异常后使用的 HTTP 状态码；常见为 ``HttpStatus.INTERNAL_SERVER_ERROR``，
        或与现网一致的 ``HttpStatus.OK``（如历史上避免前端断连的接口）。

    **返回**：适用于 ``def method(self, ...) -> tuple[dict, int]`` 的装饰器。
    """
    def decorator(method: Callable[..., ServiceRouteTuple]) -> Callable[..., ServiceRouteTuple]:
        @wraps(method)
        def wrapped(instance: Any, *args: Any, **kwargs: Any) -> ServiceRouteTuple:
            try:
                return method(instance, *args, **kwargs)
            except Exception as route_error:
                return make_json_tuple(client_error_body(str(route_error)), http_status_on_error)

        return wrapped

    return decorator


def guard_plain_service_route_tuple(
    *,
    http_status_on_error: int = HttpStatus.INTERNAL_SERVER_ERROR,
    before_error_response: Callable[[Exception], None] | None = None,
) -> Callable[
    [Callable[..., ServiceRouteTuple]],
    Callable[..., ServiceRouteTuple],
]:
    """返回包装**无实例首参**可调用对象的装饰器（与 `guard_service_route_tuple` 成对）。

    **功能**：与 `guard_service_route_tuple` 相同，但对 ``def fn(*args, **kwargs):`` 使用
    ``fn(*args, **kwargs)``（不注入 ``self``）。适用于模块级函数、``functools.partial`` 生成的零参可调用对象等。

    **参数**：
        http_status_on_error — 异常时写入 HTTP 层的数字状态码；
        before_error_response — 在拼装 ``client_error_body`` **之前**回调（通常为 ``logger.exception``），
            入参仅为捕获到的 ``Exception``；用于保留栈日志与占位符格式的既有行为。

    **返回**：可调用的二层装饰器，适用于 ``Callable[..., tuple[dict, int]]``。
    """
    def decorator(func: Callable[..., ServiceRouteTuple]) -> Callable[..., ServiceRouteTuple]:
        @wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> ServiceRouteTuple:
            try:
                return func(*args, **kwargs)
            except Exception as route_error:
                if before_error_response is not None:
                    before_error_response(route_error)
                return make_json_tuple(client_error_body(str(route_error)), http_status_on_error)

        return wrapped

    return decorator
