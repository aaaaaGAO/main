#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可编程中央域子接口的业务层（与 Flask 解耦）。

与 `web.routes.central` 中**不依赖** `StateConfigService` 合并页面 state 的入口对应：
路由仅解析请求体并 `jsonify`；本节返回 ``(响应 dict, HTTP 状态码)``，
供蓝图保持「薄」，复杂分支与日志在此完成。

协作：`generators.capl_soa`（矩阵解析与 ``SOA_StartSetserver.cin`` 生成）、
`infra` / `pathing`（路径）。
"""

from __future__ import annotations

import logging
from typing import Any

from generators.capl_soa.entrypoint import run_setserver_cin_generation
from generators.capl_soa.soa_setserver_cin import resolve_srv_excel_absolute_path

logger = logging.getLogger(__name__)

ANCHOR_REQUIRED_MESSAGE = (
    "缺少 anchor_path（用于从工程目录向上定位 Public\\TESTmode\\Bus\\SOA\\SOA_Onder）"
)


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
            return {"success": False, "message": str(resolution_error)}, 400

    if not stripped_anchor:
        return {"success": False, "message": ANCHOR_REQUIRED_MESSAGE}, 400

    try:
        output_path = run_setserver_cin_generation(
            excel_path=resolved_excel,
            anchor_path=stripped_anchor,
        )
        return (
            {
                "success": True,
                "message": f"已生成 SOA_StartSetserver.cin {output_path}",
                "output_path": output_path,
            },
            200,
        )
    except Exception as route_error:
        logger.exception(
            "SOA_StartSetserver.cin 生成失败(base_dir=%s, domain=%s)",
            base_dir,
            domain_upper,
        )
        return {"success": False, "message": str(route_error)}, 500


class CentralProgrammaticRouteService:
    """可编程中央域入口的封装类（与 `central.py` 路由名一一对应）。"""

    soa_setserver_cin_result = staticmethod(soa_setserver_cin_result)
