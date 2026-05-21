#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可编程域路由的业务入口（与 Flask 请求对象解耦）。

供 ``web.routes.lr_rear`` / ``central`` / ``dtc`` 等蓝图调用：
编排 ``TaskOrchestrator``、或经 ``ConfigService`` 写入 LR 片段，不在路由文件中堆叠分支逻辑。
"""

from __future__ import annotations

from typing import Any, TypedDict

from services.config_service import ConfigService
from services.http_api_constants import HttpStatus, api_error, api_success
from services.task_orchestrator import TaskOrchestrator


class ProgrammaticDomainPayload(TypedDict, total=False):
    """可编程域接口请求体（用于脚本/颗粒度 API），允许按需增量扩展字段。"""

    base_dir: str
    config_path: str
    validate_before_run: bool
    run_can: bool
    run_xml: bool
    run_uart: bool
    run_soa: bool
    run_cin: bool
    run_did: bool


class ProgrammaticDomainRouteService:
    """脚本/颗粒度接口用的域编排封装（无 Flask ``request`` 依赖）。"""

    @staticmethod
    def parse_base_dir(payload: ProgrammaticDomainPayload, fallback_base_dir: str) -> str:
        """从 JSON ``payload['base_dir']`` 或非空退回 ``fallback_base_dir``。"""
        raw = payload.get("base_dir")
        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped:
                return stripped
        return fallback_base_dir

    @staticmethod
    def run_lr_generate_can_bundle(payload: ProgrammaticDomainPayload, *, fallback_base_dir: str):
        """构造编排器并执行 ``run_lr_bundle(run_can=True)``。"""
        base_dir = ProgrammaticDomainRouteService.parse_base_dir(payload, fallback_base_dir)
        config_path = payload.get("config_path")
        orch = TaskOrchestrator.from_base_dir(base_dir, config_path=config_path)
        return orch.run_lr_bundle(run_can=True)

    @staticmethod
    def save_lr_rear_section_tuple(
        payload: ProgrammaticDomainPayload, *, fallback_base_dir: str
    ) -> tuple[dict[str, Any], int]:
        """
        将 ``payload`` 中可识别的 LR_REAR 字段写入主配置。

        返回：``tuple[响应 dict, HTTP 状态码]``，供路由层 ``jsonify_route_result`` 使用。
        """
        base_dir = ProgrammaticDomainRouteService.parse_base_dir(payload, fallback_base_dir)
        svc = ConfigService.from_base_dir(base_dir)
        lr_data = svc.build_lr_rear_section_data(payload)
        if not lr_data:
            return api_error(
                "未提供任何可写入的 LR_REAR 字段",
                status=HttpStatus.BAD_REQUEST,
            )
        svc.save_lr_rear(lr_data)
        return api_success("LR_REAR 配置已保存")

    @staticmethod
    def run_central_programmatic_bundle(payload: ProgrammaticDomainPayload, *, fallback_base_dir: str):
        """中央域：按请求体布尔开关调用 ``run_central_bundle``。"""
        base_dir = ProgrammaticDomainRouteService.parse_base_dir(payload, fallback_base_dir)
        run_can = payload.get("run_can", True)
        run_xml = payload.get("run_xml", True)
        run_uart = bool(payload.get("run_uart", False))
        run_soa = bool(payload.get("run_soa", False))
        validate_before_run = payload.get("validate_before_run", True)
        orch = TaskOrchestrator.from_base_dir(base_dir)
        return orch.run_central_bundle(
            run_can=run_can,
            run_xml=run_xml,
            run_uart=run_uart,
            run_soa=run_soa,
            validate_before_run=validate_before_run,
        )

    @staticmethod
    def run_dtc_programmatic_bundle(payload: ProgrammaticDomainPayload, *, fallback_base_dir: str):
        """DTC 域：按请求体布尔开关调用 ``run_dtc_bundle``。"""
        base_dir = ProgrammaticDomainRouteService.parse_base_dir(payload, fallback_base_dir)
        run_can = payload.get("run_can", True)
        run_xml = payload.get("run_xml", True)
        run_cin = bool(payload.get("run_cin", False))
        run_did = bool(payload.get("run_did", False))
        run_soa = bool(payload.get("run_soa", False))
        validate_before_run = payload.get("validate_before_run", True)
        orch = TaskOrchestrator.from_base_dir(base_dir)
        return orch.run_dtc_bundle(
            run_can=run_can,
            run_xml=run_xml,
            run_cin=run_cin,
            run_did=run_did,
            run_soa=run_soa,
            validate_before_run=validate_before_run,
        )
