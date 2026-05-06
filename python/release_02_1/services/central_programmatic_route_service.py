#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可编程中央域子接口的业务层（与 Flask 解耦）。

与 `web.routes.central` 中**不依赖** `StateConfigService` 合并页面 state 的入口对应：
路由仅解析请求体并 `jsonify`；本节返回 ``(响应 dict, HTTP 状态码)``，
供蓝图保持「薄」，复杂分支与日志在此完成。

协作：`generators.capl_soa`（矩阵解析与 ``SOA_StartSetserver.cin`` 生成）、
`infra` / `pathing`（路径）。
生成阶段异常路径与一键生成同源：``guard_plain_service_route_tuple`` + `client_error_body`。
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from generators.capl_soa.entrypoint import run_setserver_cin_generation
from generators.capl_soa.soa_setserver_cin import resolve_srv_excel_absolute_path
from services.http_api_constants import (
    HttpStatus,
    RESPONSE_KEY_OUTPUT_PATH,
    api_error,
    api_success,
)
from services.service_route_result_decorator import guard_plain_service_route_tuple

logger = logging.getLogger(__name__)

ANCHOR_REQUIRED_MESSAGE = (
    "缺少 anchor_path（用于从工程目录向上定位 Public\\TESTmode\\Bus\\SOA\\SOA_Onder）"
)


def invoke_soa_setserver_generation(
    resolved_excel: str,
    stripped_anchor: str,
) -> tuple[dict[str, Any], int]:
    """在已通过参数校验的前提下执行 CIN 生成并返回统一成功 tuple（不向调用方捕获异常）。

    参数：
        resolved_excel：解析后的接口表 Excel 绝对路径。
        stripped_anchor：已去首尾空白的锚点路径。

    返回：``api_success`` 拼装的结果与 HTTP 200。
    """
    output_path = run_setserver_cin_generation(
        excel_path=resolved_excel,
        anchor_path=stripped_anchor,
    )
    return api_success(
        f"已生成 SOA_StartSetserver.cin {output_path}",
        extra={RESPONSE_KEY_OUTPUT_PATH: output_path},
    )


def record_soa_setserver_route_exception(
    base_dir: str,
    domain_upper: str,
    wrapped_error: Exception,
) -> None:
    """在返回守卫统一错误 JSON 之前记录服务端异常栈（占位符与原实现一致）。

    参数：
        base_dir：工程根（日志占位符）。
        domain_upper：大写域名（日志占位符）。
        wrapped_error：守卫捕获到的异常对象（与同模块其它 ``before_error_response`` 回调签名一致）。

    返回：无。
    """
    logger.exception(
        "SOA_StartSetserver.cin 生成失败(base_dir=%s, domain=%s): %s",
        base_dir,
        domain_upper,
        wrapped_error,
    )


class CentralProgrammaticRouteService:
    """可编程中央域入口的封装类（与 `central.py` 路由名一一对应）。"""

    @staticmethod
    def soa_setserver_cin_result(
        *,
        base_dir: str,
        excel_path: str,
        anchor_path: str,
        domain_key: str,
    ) -> tuple[dict[str, Any], int]:
        """解析参数并生成 ``SOA_StartSetserver.cin``，返回 API 响应体与状态码。

        功能：
        - ``excel_path`` 为空时在 ``domain_key`` 对应配置节读取 ``srv_excel``；
        - ``anchor_path`` 必填；生成失败时在服务端记录 ``logger.exception`` 并返回 500。

        参数：
            base_dir：工程根目录（用于解析配置内相对路径）。
            excel_path：接口表 Excel 路径；为空则从配置推导。
            anchor_path：输出锚点路径。
            domain_key：``CENTRAL`` / ``LR_REAR`` / ``DTC`` 等（大小写不敏感）。

        返回：
            ``({"success": bool, "message": str [, "output_path": str]}, status_code)``
        """
        stripped_excel = (excel_path or "").strip()
        stripped_anchor = (anchor_path or "").strip()
        domain_upper = (domain_key or "CENTRAL").strip().upper()

        resolved_excel = stripped_excel
        if not resolved_excel:
            try:
                resolved_excel = resolve_srv_excel_absolute_path(base_dir, domain_upper)
            except ValueError as resolution_error:
                return api_error(str(resolution_error), status=HttpStatus.BAD_REQUEST)

        if not stripped_anchor:
            return api_error(ANCHOR_REQUIRED_MESSAGE, status=HttpStatus.BAD_REQUEST)

        guarded = guard_plain_service_route_tuple(
            http_status_on_error=HttpStatus.INTERNAL_SERVER_ERROR,
            before_error_response=functools.partial(
                record_soa_setserver_route_exception,
                base_dir,
                domain_upper,
            ),
        )(
            functools.partial(
                invoke_soa_setserver_generation,
                resolved_excel,
                stripped_anchor,
            ),
        )
        return guarded()


def soa_setserver_cin_result(
    *,
    base_dir: str,
    excel_path: str,
    anchor_path: str,
    domain_key: str,
) -> tuple[dict[str, Any], int]:
    """兼容 `web.routes.central` 等对模块级函数的导入；语义同 `CentralProgrammaticRouteService.soa_setserver_cin_result`。"""
    return CentralProgrammaticRouteService.soa_setserver_cin_result(
        base_dir=base_dir,
        excel_path=excel_path,
        anchor_path=anchor_path,
        domain_key=domain_key,
    )
