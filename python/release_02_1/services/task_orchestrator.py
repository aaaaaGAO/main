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
from typing import Any, Callable, Dict, List, Optional

from services.config_manager import ConfigManager
from services.config_constants import (
    OPTION_UART_EXCEL,
    PATHS_UART_INPUT_OPTION_CANDIDATES,
    SECTION_CENTRAL,
    SECTION_DTC,
    SECTION_LR_REAR,
    SECTION_PATHS,
    UART_COMM_CFG_KEYS,
)
from services.run_validator import RunValidator
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

# 编排步名 →（是否执行所依据的 run_* 开关名，实际调用 TaskService 的闭包）
BundleTaskRunner = Callable[[TaskService, str], TaskResult]

BUNDLE_SIMPLE_STEP_RUNNERS: Dict[str, tuple[str, BundleTaskRunner]] = {
    "did_config": (
        "run_did",
        lambda task_service, domain_section: task_service.run_did_config(domain=domain_section),
    ),
    "did_info": (
        "run_did",
        lambda task_service, domain_section: task_service.run_did_info(domain=domain_section),
    ),
    "cin": (
        "run_cin",
        lambda task_service, domain_section: task_service.run_cin(domain=domain_section),
    ),
    "soa": (
        "run_soa",
        lambda task_service, domain_section: task_service.run_soa(domain=domain_section),
    ),
    "can": (
        "run_can",
        lambda task_service, domain_section: task_service.run_can(domain=domain_section),
    ),
    "xml": (
        "run_xml",
        lambda task_service, domain_section: task_service.run_xml(domain=domain_section),
    ),
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
        """与 `from_base_dir` 绑定的 `ConfigManager`（主/固定配置读写、UDS 路径解析等）。"""
        return self.config_manager_service

    @property
    def task_service(self) -> TaskService:
        """单任务执行器：调用各 `generators.*.entrypoint` 的 CAN/XML/CIN 等子任务。"""
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
                config.get(SECTION_CENTRAL, OPTION_UART_EXCEL, fallback="") or ""
            ).strip()
        if not uart_excel_raw and config.has_section(SECTION_PATHS):
            for option_name in PATHS_UART_INPUT_OPTION_CANDIDATES:
                uart_excel_raw = (
                    config.get(SECTION_PATHS, option_name, fallback="") or ""
                ).strip()
                if uart_excel_raw:
                    break
        if not uart_excel_raw:
            uart_excel_raw = "input/MCU_CDCU_CommunicationMatrix.xlsx"
        uart_excel_path = uart_excel_raw.replace("/", os.sep)
        if not os.path.isabs(uart_excel_path):
            uart_excel_path = os.path.join(base_dir, uart_excel_path)
        uart_excel_path = os.path.normpath(uart_excel_path)
        return uart_excel_path if os.path.isfile(uart_excel_path) else None

    def run_bundle_simple_step_if_applicable(
        self,
        *,
        config_section: str,
        bundle_step: str,
        run_flag_by_name: Dict[str, bool],
        run_started: float,
        messages: List[str],
        detail_parts: List[str],
        results: Dict[str, TaskResult],
        workbook_cache: Dict[str, object] | None = None,
    ) -> Optional[OrchestratorResult]:
        """执行与 BUNDLE_SIMPLE_STEP_RUNNERS 对应的单步；非表内步或开关关闭时返回 None。"""
        step_spec = BUNDLE_SIMPLE_STEP_RUNNERS.get(bundle_step)
        if step_spec is None:
            return None
        flag_name, runner = step_spec
        if not run_flag_by_name.get(flag_name):
            return None
        step_started = time.perf_counter()
        logger.info(
            "[TaskOrchestrator] event=step_start domain=%s step=%s",
            config_section,
            bundle_step,
        )
        if bundle_step == "can":
            task_result = self.task_service_instance.run_can(
                domain=config_section,
                workbook_cache=workbook_cache,
            )
        elif bundle_step == "xml":
            task_result = self.task_service_instance.run_xml(
                domain=config_section,
                workbook_cache=workbook_cache,
            )
        else:
            task_result = runner(self.task_service_instance, config_section)
        results[bundle_step] = task_result
        messages.append(task_result.message)
        if not task_result.success:
            logger.error(
                "[TaskOrchestrator] event=step_failed domain=%s step=%s elapsed_ms=%.1f",
                config_section,
                bundle_step,
                (time.perf_counter() - run_started) * 1000.0,
            )
            return OrchestratorResult(
                success=False,
                messages=messages,
                detail=task_result.detail or "",
                extra=results,
            )
        logger.info(
            "[TaskOrchestrator] event=step_done domain=%s step=%s elapsed_ms=%.1f",
            config_section,
            bundle_step,
            (time.perf_counter() - step_started) * 1000.0,
        )
        if task_result.detail:
            detail_parts.append(task_result.detail)
        return None

    def run_generic_bundle(
        self,
        config_section: str,
        *,
        run_can: bool = True,
        run_xml: bool = True,
        run_cin: bool = False,
        run_did: bool = False,
        run_uart: bool = False,
        run_soa: bool = False,
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """
        通用域编排：按 _BUNDLE_SPEC 执行；UART 步仅当 config_section 为 CENTRAL 且 run_uart 时生效。
        config_section 为 "LR_REAR" | "CENTRAL" | "DTC"。

        各 run_* 表示「本趟是否执行该子步骤」。默认仅 run_can / run_xml 为 True（主流程）；
        run_cin、run_did、run_uart、run_soa 均为 False，与「除 CAN/XML 外须用户选择或主界面
        state 中已填表再跑」一致。Web 主路径应传 StateConfigService.get_*_generation_flags 的结果。
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
            is_valid, errors = RunValidator.validate_for_domain(
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
        workbook_cache: Dict[str, object] = {}
        run_flag_by_name: Dict[str, bool] = {
            "run_can": run_can,
            "run_xml": run_xml,
            "run_cin": run_cin,
            "run_did": run_did,
            "run_uart": run_uart,
            "run_soa": run_soa,
        }

        try:
            for bundle_step in bundle_steps:
                if bundle_step == "uart":
                    # 仅中央域执行 UART 生成并创建 generate_uart_from_config.log；左右后域/DTC 不涉及 UART 则不生成该日志
                    if not run_uart or config_section != SECTION_CENTRAL:
                        continue
                    cfg = self.config_manager_service.load_config()
                    uart_matrix_path = self.resolve_uart_path(cfg)
                    has_uart_comm = cfg.has_section(SECTION_CENTRAL) and any(
                        cfg.has_option(SECTION_CENTRAL, item_key) for item_key in UART_COMM_CFG_KEYS
                    )
                    if uart_matrix_path or has_uart_comm:
                        step_started = time.perf_counter()
                        logger.info("[TaskOrchestrator] event=step_start domain=%s step=uart", config_section)
                        task_result = self.task_service_instance.run_uart(workbook_cache=workbook_cache)
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
                    continue

                failure = self.run_bundle_simple_step_if_applicable(
                    config_section=config_section,
                    bundle_step=bundle_step,
                    run_flag_by_name=run_flag_by_name,
                    run_started=run_started,
                    messages=messages,
                    detail_parts=detail_parts,
                    results=results,
                    workbook_cache=workbook_cache,
                )
                if failure is not None:
                    return failure
        finally:
            for workbook_obj in workbook_cache.values():
                try:
                    workbook_obj.close()
                except Exception:
                    pass

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
        run_cin: bool = False,
        run_did: bool = False,
        run_soa: bool = False,
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """左右后域：CAN/XML 默认可跑；CIN、DID、SOA 须 True 或 state 中已选表才跑（不含 UART）。"""
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
        run_uart: bool = False,
        run_soa: bool = False,
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """中央域：CAN/XML 默认可跑；UART、SOA 与 LR 域 CIN 等同，须 True 或 state 已选再跑。

        参数: run_can/run_xml/run_uart/run_soa — 是否执行；validate_before_run — 是否先校验。
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
        run_cin: bool = False,
        run_did: bool = False,
        run_soa: bool = False,
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """DTC 域：CAN/XML 默认可跑；CIN、DID、SOA 须 True 或 state 中已选表再跑。
        参数: run_can/run_xml/run_cin/run_did/run_soa — 是否执行；validate_before_run — 是否先校验。
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
