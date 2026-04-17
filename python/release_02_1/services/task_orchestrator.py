#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业务逻辑层（TaskOrchestrator）

目标：收纳 generate_lr、generate_central、generate_dtc 的组合逻辑。
职责：不关心 HTTP 请求，只负责：校验（可选）-> 调用底层生成器 -> 收集成功/失败清单。
"""

from __future__ import annotations

import logging
import os
import time
from configparser import ConfigParser
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.config_manager import ConfigManager
from services.config_constants import (
    SECTION_CENTRAL,
    SECTION_DTC,
    SECTION_LR_REAR,
    SECTION_PATHS,
    UART_COMM_CFG_KEYS,
)
from services.run_validator import validate_for_domain
from services.task_service import TaskService, TaskResult
from core.log_run_context import reset_run_context, set_run_domain


@dataclass
class OrchestratorResult:
    """一次编排执行的结果：是否整体成功、消息列表、详情。"""
    success: bool
    messages: List[str] = field(default_factory=list)
    detail: str = ""
    extra: Optional[Dict[str, Any]] = None


# 各域编排步骤顺序（与第一界面一致时，DTC 也执行 DID/CIN → CAN → XML）
_BUNDLE_SPEC: Dict[str, List[str]] = {
    # 左右后域不包含 UART（UART 仅中央域）
    SECTION_LR_REAR: ["did_config", "did_info", "cin", "soa", "can", "xml"],
    SECTION_CENTRAL: ["uart", "soa", "can", "xml"],
    SECTION_DTC: ["did_config", "did_info", "cin", "soa", "can", "xml"],
}

logger = logging.getLogger(__name__)


class TaskOrchestrator:
    """
    任务编排器：按域组合「校验 + 运行生成任务」，并汇总结果。
    使用方式：
        orch = TaskOrchestrator.from_base_dir(base_dir)
        result = orch.run_lr_bundle()
        result = orch.run_central_bundle()
        result = orch.run_dtc_bundle()
    """

    def __init__(
        self,
        base_dir: str,
        config_path: Optional[str] = None,
    ) -> None:
        """初始化任务编排器，绑定项目根目录与配置路径。
        参数: base_dir — 项目根目录；config_path — 主配置路径，None 时由 ConfigManager 自动解析。
        """
        self.config_manager_service = ConfigManager.from_base_dir(base_dir)
        self.task_service_instance = TaskService(base_dir=base_dir, config_path=config_path)

    @classmethod
    def from_base_dir(cls, base_dir: str, config_path: Optional[str] = None) -> "TaskOrchestrator":
        """从项目根目录创建编排器。参数: base_dir — 项目根；config_path — 可选主配置路径。返回: TaskOrchestrator 实例。"""
        return cls(base_dir=base_dir, config_path=config_path)

    @property
    def config_manager(self) -> ConfigManager:
        return self.config_manager_service

    @property
    def task_service(self) -> TaskService:
        return self.task_service_instance

    def build_result_message(
        self,
        result: OrchestratorResult,
        *,
        config: Optional[Any],
        section: str,
        prefix: str = "",
        separator: str = " | ",
    ) -> str:
        """构建给路由层展示的结果消息，并在存在时追加 UDS 完成提示。"""
        body = separator.join(result.messages)
        message = f"{prefix}{body}" if prefix else body
        if config is None:
            return message
        uds_path = self.config_manager_service.resolve_uds_output_path(config, section)
        if uds_path and os.path.isfile(uds_path):
            message += f"{separator}UDS.txt 生成完成"
        return message

    def resolve_uart_path(self, config: Optional[ConfigParser] = None) -> Optional[str]:
        """解析 UART 矩阵文件路径；文件不存在则返回 None。"""
        if config is None:
            config = self.config_manager_service.load_config()
        base_dir = self.task_service_instance.base_dir
        uart_excel_raw = ""
        if config.has_section(SECTION_CENTRAL):
            uart_excel_raw = (
                config.get(SECTION_CENTRAL, "uart_excel", fallback="") or ""
            ).strip()
        if not uart_excel_raw and config.has_section(SECTION_PATHS):
            uart_excel_raw = (
                config.get(SECTION_PATHS, "Uart_Input_Excel", fallback="") or ""
            ).strip()
        if not uart_excel_raw:
            uart_excel_raw = "input/MCU_CDCU_CommunicationMatrix.xlsx"
        uart_excel_path = uart_excel_raw.replace("/", os.sep)
        if not os.path.isabs(uart_excel_path):
            uart_excel_path = os.path.join(base_dir, uart_excel_path)
        uart_excel_path = os.path.normpath(uart_excel_path)
        return uart_excel_path if os.path.isfile(uart_excel_path) else None

    def run_generic_bundle(
        self,
        config_section: str,
        *,
        run_can: bool = True,
        run_xml: bool = True,
        run_cin: bool = True,
        run_did: bool = True,
        run_uart: bool = True,
        run_soa: bool = False,
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """
        通用域编排：按 _BUNDLE_SPEC 执行；UART 步仅当 config_section 为 CENTRAL 且 run_uart 时生效。
        config_section 为 "LR_REAR" | "CENTRAL" | "DTC"。
        """
        run_started = time.perf_counter()
        logger.info(
            "[TaskOrchestrator] event=start domain=%s run_can=%s run_xml=%s run_cin=%s run_did=%s run_uart=%s run_soa=%s validate_before_run=%s",
            config_section,
            run_can,
            run_xml,
            run_cin,
            run_did,
            run_uart,
            run_soa,
            validate_before_run,
        )
        reset_run_context()
        set_run_domain(config_section)
        messages: List[str] = []
        detail_parts: List[str] = []
        results: Dict[str, TaskResult] = {}

        if validate_before_run:
            is_valid, errors = validate_for_domain(
                config_section,
                self.task_service_instance.base_dir,
                self.task_service_instance.config_path,
                self.config_manager_service,
                run_can=run_can,
                run_xml=run_xml,
                run_did=run_did,
                run_cin=run_cin,
                run_soa=run_soa,
            )
            if not is_valid:
                logger.warning(
                    "[TaskOrchestrator] event=validation_failed domain=%s errors=%d elapsed_ms=%.1f",
                    config_section,
                    len(errors),
                    (time.perf_counter() - run_started) * 1000.0,
                )
                return OrchestratorResult(
                    success=False,
                    messages=["校验未通过"],
                    detail="\n".join(errors),
                    extra=None,
                )

        bundle_steps = _BUNDLE_SPEC.get(config_section, [])

        for bundle_step in bundle_steps:
            if bundle_step == "did_config":
                if not run_did:
                    continue
                step_started = time.perf_counter()
                logger.info("[TaskOrchestrator] event=step_start domain=%s step=did_config", config_section)
                task_result = self.task_service_instance.run_did_config(domain=config_section)
                results["did_config"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    logger.error(
                        "[TaskOrchestrator] event=step_failed domain=%s step=did_config elapsed_ms=%.1f",
                        config_section,
                        (time.perf_counter() - run_started) * 1000.0,
                    )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                logger.info(
                    "[TaskOrchestrator] event=step_done domain=%s step=did_config elapsed_ms=%.1f",
                    config_section,
                    (time.perf_counter() - step_started) * 1000.0,
                )
                if task_result.detail:
                    detail_parts.append(task_result.detail)

            elif bundle_step == "did_info":
                if not run_did:
                    continue
                step_started = time.perf_counter()
                logger.info("[TaskOrchestrator] event=step_start domain=%s step=did_info", config_section)
                task_result = self.task_service_instance.run_did_info(domain=config_section)
                results["did_info"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    logger.error(
                        "[TaskOrchestrator] event=step_failed domain=%s step=did_info elapsed_ms=%.1f",
                        config_section,
                        (time.perf_counter() - run_started) * 1000.0,
                    )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                logger.info(
                    "[TaskOrchestrator] event=step_done domain=%s step=did_info elapsed_ms=%.1f",
                    config_section,
                    (time.perf_counter() - step_started) * 1000.0,
                )
                if task_result.detail:
                    detail_parts.append(task_result.detail)

            elif bundle_step == "cin":
                if not run_cin:
                    continue
                step_started = time.perf_counter()
                logger.info("[TaskOrchestrator] event=step_start domain=%s step=cin", config_section)
                task_result = self.task_service_instance.run_cin(domain=config_section)
                results["cin"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    logger.error(
                        "[TaskOrchestrator] event=step_failed domain=%s step=cin elapsed_ms=%.1f",
                        config_section,
                        (time.perf_counter() - run_started) * 1000.0,
                    )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                logger.info(
                    "[TaskOrchestrator] event=step_done domain=%s step=cin elapsed_ms=%.1f",
                    config_section,
                    (time.perf_counter() - step_started) * 1000.0,
                )
                if task_result.detail:
                    detail_parts.append(task_result.detail)

            elif bundle_step == "uart":
                # 仅中央域执行 UART 生成并创建 generate_uart_from_config.log；左右后域/DTC 不涉及 UART 则不生成该日志
                if not run_uart or config_section != SECTION_CENTRAL:
                    continue
                cfg = self.config_manager_service.load_config()
                uart_matrix_path = self.resolve_uart_path(cfg)
                has_uart_comm = cfg.has_section(SECTION_CENTRAL) and any(
                    cfg.has_option(SECTION_CENTRAL, key) for key in UART_COMM_CFG_KEYS
                )
                if uart_matrix_path or has_uart_comm:
                    step_started = time.perf_counter()
                    logger.info("[TaskOrchestrator] event=step_start domain=%s step=uart", config_section)
                    task_result = self.task_service_instance.run_uart()
                    results["uart"] = task_result
                    messages.append(task_result.message)
                    if not task_result.success:
                        logger.error(
                            "[TaskOrchestrator] event=step_failed domain=%s step=uart elapsed_ms=%.1f",
                            config_section,
                            (time.perf_counter() - run_started) * 1000.0,
                        )
                        return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                    logger.info(
                        "[TaskOrchestrator] event=step_done domain=%s step=uart elapsed_ms=%.1f",
                        config_section,
                        (time.perf_counter() - step_started) * 1000.0,
                    )
                    if task_result.detail:
                        detail_parts.append(task_result.detail)
                else:
                    messages.append(
                        "跳过 UART 生成（无有效矩阵文件且 [CENTRAL] 未配置 uart_comm_*）"
                    )
                    logger.info("[TaskOrchestrator] event=step_skip domain=%s step=uart reason=no_matrix_or_uart_comm", config_section)

            elif bundle_step == "soa":
                if not run_soa:
                    continue
                step_started = time.perf_counter()
                logger.info("[TaskOrchestrator] event=step_start domain=%s step=soa", config_section)
                task_result = self.task_service_instance.run_soa(domain=config_section)
                results["soa"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    logger.error(
                        "[TaskOrchestrator] event=step_failed domain=%s step=soa elapsed_ms=%.1f",
                        config_section,
                        (time.perf_counter() - run_started) * 1000.0,
                    )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                logger.info(
                    "[TaskOrchestrator] event=step_done domain=%s step=soa elapsed_ms=%.1f",
                    config_section,
                    (time.perf_counter() - step_started) * 1000.0,
                )
                if task_result.detail:
                    detail_parts.append(task_result.detail)

            elif bundle_step == "can":
                if not run_can:
                    continue
                step_started = time.perf_counter()
                logger.info("[TaskOrchestrator] event=step_start domain=%s step=can", config_section)
                task_result = self.task_service_instance.run_can(domain=config_section)
                results["can"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    logger.error(
                        "[TaskOrchestrator] event=step_failed domain=%s step=can elapsed_ms=%.1f",
                        config_section,
                        (time.perf_counter() - run_started) * 1000.0,
                    )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                logger.info(
                    "[TaskOrchestrator] event=step_done domain=%s step=can elapsed_ms=%.1f",
                    config_section,
                    (time.perf_counter() - step_started) * 1000.0,
                )
                if task_result.detail:
                    detail_parts.append(task_result.detail)

            elif bundle_step == "xml":
                if not run_xml:
                    continue
                step_started = time.perf_counter()
                logger.info("[TaskOrchestrator] event=step_start domain=%s step=xml", config_section)
                task_result = self.task_service_instance.run_xml(domain=config_section)
                results["xml"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    logger.error(
                        "[TaskOrchestrator] event=step_failed domain=%s step=xml elapsed_ms=%.1f",
                        config_section,
                        (time.perf_counter() - run_started) * 1000.0,
                    )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                logger.info(
                    "[TaskOrchestrator] event=step_done domain=%s step=xml elapsed_ms=%.1f",
                    config_section,
                    (time.perf_counter() - step_started) * 1000.0,
                )
                if task_result.detail:
                    detail_parts.append(task_result.detail)

        elapsed_ms = (time.perf_counter() - run_started) * 1000.0
        logger.info(
            "[TaskOrchestrator] event=done domain=%s success=true steps=%d elapsed_ms=%.1f",
            config_section,
            len(results),
            elapsed_ms,
        )
        return OrchestratorResult(
            success=True,
            messages=messages,
            detail="\n".join(detail_parts) if detail_parts else "",
            extra=results or None,
        )

    def run_lr_bundle(
        self,
        run_can: bool = True,
        run_xml: bool = True,
        run_cin: bool = True,
        run_did: bool = True,
        run_soa: bool = False,
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """左右后域一键生成：DID → DIDInfo → CIN → CAN → XML（不包含 UART）。"""
        return self.run_generic_bundle(
            SECTION_LR_REAR,
            run_can=run_can,
            run_xml=run_xml,
            run_cin=run_cin,
            run_did=run_did,
            run_soa=run_soa,
            run_uart=False,
            validate_before_run=validate_before_run,
        )

    def run_central_bundle(
        self,
        run_can: bool = True,
        run_xml: bool = True,
        run_uart: bool = True,
        run_soa: bool = True,
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """中央域一键生成：UART(可选) → CAN → XML。
        参数: run_can/run_xml/run_uart — 是否执行；validate_before_run — 是否先校验。
        返回: OrchestratorResult。
        """
        return self.run_generic_bundle(
            SECTION_CENTRAL,
            run_can=run_can,
            run_xml=run_xml,
            run_cin=False,
            run_did=False,
            run_uart=run_uart,
            run_soa=run_soa,
            validate_before_run=validate_before_run,
        )

    def run_dtc_bundle(
        self,
        run_can: bool = True,
        run_xml: bool = True,
        run_cin: bool = True,
        run_did: bool = True,
        run_soa: bool = False,
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """DTC 域一键生成：DIDConfig → DIDInfo → CIN → CAN → XML（配置了对应表时）。
        参数: run_can/run_xml/run_cin/run_did — 是否执行；validate_before_run — 是否先校验。
        返回: OrchestratorResult。
        """
        return self.run_generic_bundle(
            SECTION_DTC,
            run_can=run_can,
            run_xml=run_xml,
            run_cin=run_cin,
            run_did=run_did,
            run_soa=run_soa,
            run_uart=False,
            validate_before_run=validate_before_run,
        )
