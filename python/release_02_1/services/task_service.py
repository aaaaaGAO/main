#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务执行服务。

负责统一封装各生成步骤（CAN/XML/CIN/DID/UART/SOA）的调用、耗时日志与错误返回。
"""

from __future__ import annotations

import logging
import os
import time
import traceback
from dataclasses import dataclass
from typing import Any, Dict, Optional

from infra.filesystem import resolve_main_config_path
from services.config_constants import (
    DEFAULT_DOMAIN_LR_REAR,
    LABEL_RESETDID_VALUE_CONFIG_TABLE,
    SECTION_CENTRAL,
)
from generators.capl_can.entrypoint import run_generation as run_can_generation
from generators.capl_cin.entrypoint import run_generation as run_cin_generation
from generators.capl_didconfig.entrypoint import run_generation as run_didconfig_generation
from generators.capl_resetdid.entrypoint import run_generation as run_resetdid_generation
from generators.capl_uart.entrypoint import run_generation as run_uart_generation
from generators.capl_xml.entrypoint import run_generation as run_xml_generation
from generators.capl_soa.entrypoint import run_generation as run_soa_generation

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """任务执行结果数据结构。

    Attributes:
        success: 是否执行成功。
        message: 结果摘要信息。
        detail: 异常详情或补充信息。
        extra: 可选扩展字段。
    """

    success: bool
    message: str
    detail: str = ""
    extra: Dict[str, Any] | None = None


class TaskService:
    """各生成步骤服务封装层。"""
    def __init__(self, base_dir: str, config_path: Optional[str] = None) -> None:
        """初始化任务服务。

        Args:
            base_dir: 项目根目录。
            config_path: 可选，指定配置文件路径；不传则使用默认主配置路径。
        """
        self.base_dir = os.path.abspath(base_dir)
        if config_path is None:
            self.config_path = resolve_main_config_path(self.base_dir)
        else:
            self.config_path = os.path.abspath(config_path)

    # ------------------------------------------------------------------
    # 构造快捷方法
    # ------------------------------------------------------------------
    @classmethod
    def from_base_dir(cls, base_dir: str) -> "TaskService":
        """从项目根目录快速创建 TaskService。

        Args:
            base_dir: 项目根目录。

        Returns:
            TaskService: 初始化后的任务服务实例。
        """
        return cls(base_dir=base_dir)

    # ------------------------------------------------------------------
    # 各类生成任务封装
    # ------------------------------------------------------------------
    def log_task_start(self, *, step: str, domain: str) -> float:
        """打任务开始日志并返回 `perf_counter` 起点。参数：step — 子任务名；domain — 域。返回：t0 浮点秒。"""
        started = time.perf_counter()
        logger.info("[TaskService] event=start domain=%s step=%s", domain, step)
        return started

    def log_task_done(self, *, step: str, domain: str, elapsed_ms: float) -> None:
        """子任务成功结束时的结构化 info 日志。参数：elapsed_ms — 耗时毫秒。返回：无。"""
        logger.info(
            "[TaskService] event=done domain=%s step=%s success=true elapsed_ms=%.1f",
            domain,
            step,
            elapsed_ms,
        )

    def log_task_skip(self, *, step: str, domain: str, reason: str, elapsed_ms: float) -> None:
        """子任务被跳过时打 info。参数：reason — 人可读原因。返回：无。"""
        logger.info(
            "[TaskService] event=skip domain=%s step=%s reason=%s elapsed_ms=%.1f",
            domain,
            step,
            reason,
            elapsed_ms,
        )

    def log_task_failed(
        self,
        *,
        step: str,
        domain: str,
        error: Exception,
        elapsed_ms: float,
    ) -> None:
        """子任务抛错时打 error 级日志。参数：error — 异常对象。返回：无。"""
        logger.error(
            "[TaskService] event=failed domain=%s step=%s error_type=%s error=%s elapsed_ms=%.1f",
            domain,
            step,
            type(error).__name__,
            error,
            elapsed_ms,
        )

    def run_can(
        self,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
        *,
        workbook_cache: Dict[str, Any] | None = None,
    ) -> TaskResult:
        """执行 CAN 生成任务。

        Args:
            domain: 生成域，默认 LR_REAR。

        Returns:
            TaskResult: 执行结果。
        """
        started = self.log_task_start(step="can", domain=domain)
        try:
            run_can_generation(
                config_path=self.config_path,
                base_dir=self.base_dir,
                domain=domain,
                workbook_cache=workbook_cache,
            )
            self.log_task_done(
                step="can",
                domain=domain,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(success=True, message=f"{domain} CAN 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            error_message = str(error)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            # 对中央域做“无用例则安静跳过”的特殊处理：不再视为失败，只返回提示信息
            if (
                domain == SECTION_CENTRAL
                and "未配置输入路径：请配置 [CENTRAL] 的 input_excel" in error_message
            ):
                self.log_task_skip(
                    step="can",
                    domain=domain,
                    reason="missing_central_input_excel",
                    elapsed_ms=elapsed_ms,
                )
                return TaskResult(
                    success=True,
                    message="CENTRAL CAN 未生成（未配置输入路径，已按要求跳过）",
                    detail=traceback_text,
                )
            # 其它异常仍按失败处理，便于前端与日志排查
            self.log_task_failed(step="can", domain=domain, error=error, elapsed_ms=elapsed_ms)
            return TaskResult(
                success=False,
                message=f"{domain} CAN 生成失败: {error}",
                detail=traceback_text,
            )

    def run_xml(
        self,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
        *,
        workbook_cache: Dict[str, Any] | None = None,
    ) -> TaskResult:
        """执行 XML 生成任务。

        Args:
            domain: 生成域，默认 LR_REAR。

        Returns:
            TaskResult: 执行结果。
        """
        started = self.log_task_start(step="xml", domain=domain)
        try:
            run_xml_generation(
                config_path=self.config_path,
                base_dir=self.base_dir,
                domain=domain,
                workbook_cache=workbook_cache,
            )
            self.log_task_done(
                step="xml",
                domain=domain,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(success=True, message=f"{domain} XML 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            error_message = str(error)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            # 中央域未配置 XML 输入 Excel 时也按“跳过”处理
            if (
                domain == SECTION_CENTRAL
                and "未配置 Xml_Input_Excel 或 xml_input_excel" in error_message
            ):
                self.log_task_skip(
                    step="xml",
                    domain=domain,
                    reason="missing_central_xml_input_excel",
                    elapsed_ms=elapsed_ms,
                )
                return TaskResult(
                    success=True,
                    message="CENTRAL XML 未生成（未配置 Xml_Input_Excel，已按要求跳过）",
                    detail=traceback_text,
                )
            self.log_task_failed(step="xml", domain=domain, error=error, elapsed_ms=elapsed_ms)
            return TaskResult(
                success=False,
                message=f"{domain} XML 生成失败: {error}",
                detail=traceback_text,
            )

    def run_cin(self, domain: str = DEFAULT_DOMAIN_LR_REAR) -> TaskResult:
        """执行 CIN 生成任务。

        Args:
            domain: 生成域，默认 LR_REAR。

        Returns:
            TaskResult: 执行结果。
        """
        started = self.log_task_start(step="cin", domain=domain)
        try:
            run_cin_generation(domain=domain)
            self.log_task_done(
                step="cin",
                domain=domain,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(success=True, message=f"{domain} CIN 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            self.log_task_failed(
                step="cin",
                domain=domain,
                error=error,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(
                success=False,
                message=f"{domain} CIN 生成失败: {error}",
                detail=traceback_text,
            )

    def run_did_info(self, domain: str | None = None) -> TaskResult:
        """执行 DIDInfo（ResetDid）生成任务。

        Args:
            domain: 可选生成域，不传则默认 LR_REAR。

        Returns:
            TaskResult: 执行结果。
        """
        run_domain = domain or DEFAULT_DOMAIN_LR_REAR
        started = self.log_task_start(step="did_info", domain=run_domain)
        try:
            run_resetdid_generation(domain=domain)
            self.log_task_done(
                step="did_info",
                domain=run_domain,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(success=True, message="ResetDid 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            error_message = str(error)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            # 未配置 ResetDid_Value 配置表时，按“静默跳过”处理，不视为失败，只返回提示信息
            missing_didinfo_label = f"未配置 {LABEL_RESETDID_VALUE_CONFIG_TABLE}"
            if missing_didinfo_label in error_message:
                self.log_task_skip(
                    step="did_info",
                    domain=run_domain,
                    reason="missing_resetdid_value_config_table",
                    elapsed_ms=elapsed_ms,
                )
                return TaskResult(
                    success=True,
                    message=f"ResetDid 未生成（未配置 {LABEL_RESETDID_VALUE_CONFIG_TABLE}，已按要求跳过）",
                    detail=traceback_text,
                )
            self.log_task_failed(step="did_info", domain=run_domain, error=error, elapsed_ms=elapsed_ms)
            return TaskResult(
                success=False,
                message=f"ResetDid 生成失败: {error}",
                detail=traceback_text,
            )

    def run_did_config(self, domain: str | None = None) -> TaskResult:
        """执行 DIDConfig 生成任务。

        Args:
            domain: 可选生成域，不传则默认 LR_REAR。

        Returns:
            TaskResult: 执行结果。
        """
        run_domain = domain or DEFAULT_DOMAIN_LR_REAR
        started = self.log_task_start(step="did_config", domain=run_domain)
        try:
            run_didconfig_generation(domain=domain)
            self.log_task_done(
                step="did_config",
                domain=run_domain,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(success=True, message="DIDConfig 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            error_message = str(error)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            # 未配置 DID_Config 配置表/节时，按“静默跳过”处理，不视为失败，只返回提示信息
            if (
                "未配置 DID_Config 配置表" in error_message
                or "未配置 DID_Config 配置节" in error_message
                or "未配置 DID_Config 输出目录" in error_message
            ):
                self.log_task_skip(
                    step="did_config",
                    domain=run_domain,
                    reason="missing_did_config_inputs",
                    elapsed_ms=elapsed_ms,
                )
                return TaskResult(
                    success=True,
                    message="DIDConfig 未生成（未配置 DID_Config 配置表，已按要求跳过）",
                    detail=traceback_text,
                )
            self.log_task_failed(step="did_config", domain=run_domain, error=error, elapsed_ms=elapsed_ms)
            return TaskResult(
                success=False,
                message=f"DIDConfig 生成失败: {error}",
                detail=traceback_text,
            )

    def run_uart(self, *, workbook_cache: Dict[str, Any] | None = None) -> TaskResult:
        """执行 UART 生成任务。

        Returns:
            TaskResult: 执行结果。
        """
        started = self.log_task_start(step="uart", domain=SECTION_CENTRAL)
        try:
            run_uart_generation(workbook_cache=workbook_cache)
            self.log_task_done(
                step="uart",
                domain=SECTION_CENTRAL,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(success=True, message="UART 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            self.log_task_failed(
                step="uart",
                domain=SECTION_CENTRAL,
                error=error,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(
                success=False,
                message=f"UART 生成失败: {error}",
                detail=traceback_text,
            )

    def run_soa(self, domain: str = SECTION_CENTRAL) -> TaskResult:
        """执行 SOA 节点生成任务。

        Args:
            domain: 生成域，默认 CENTRAL。

        Returns:
            TaskResult: 执行结果。
        """
        started = self.log_task_start(step="soa", domain=domain)
        try:
            run_soa_generation(
                config_path=self.config_path,
                base_dir=self.base_dir,
                domain=domain,
            )
            self.log_task_done(
                step="soa",
                domain=domain,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(success=True, message=f"{domain} SOA Node 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            self.log_task_failed(
                step="soa",
                domain=domain,
                error=error,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            return TaskResult(
                success=False,
                message=f"{domain} SOA Node 生成失败: {error}",
                detail=traceback_text,
            )


