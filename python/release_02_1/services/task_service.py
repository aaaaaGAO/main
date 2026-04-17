#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务服务（TaskService）

职责：
- 作为 Web 层与 generators 包内入口之间的“调度中间层”
- 统一封装：运行哪个生成任务（CAN / XML / CIN / DIDINFO / DIDCONFIG / UART）、
  base_dir / config_path、异常捕获与结果封装。
- 调用方式：from generators.capl_can.entrypoint import run_generation，不再依赖根目录 generate_*.py。
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
    """统一的任务执行结果结构，供 Web 层与编排层使用。

    属性：
        success：是否执行成功。
        message：简要结果消息（如「LR_REAR CAN 生成完成」）。
        detail：详情（如 traceback 文本），失败时便于排查。
        extra：可选扩展数据（如各子步结果字典）。
    """

    success: bool
    message: str
    detail: str = ""
    extra: Dict[str, Any] | None = None


class TaskService:
    """生成任务调度服务：封装对各 generators.*.entrypoint.main 的调用与异常处理，供 Web 与 TaskOrchestrator 使用。"""

    def __init__(self, base_dir: str, config_path: Optional[str] = None) -> None:
        """初始化任务服务，绑定工程根目录与配置文件路径。

        形参：
            base_dir：工程根目录，生成任务将在此目录下执行（影响相对路径解析）。
            config_path：配置文件路径；None 时自动解析当前主配置文件 `Configuration.ini`。

        返回：无。
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
        """从工程根目录创建 TaskService 实例。

        形参：base_dir — 工程根目录。
        返回：TaskService 实例（config_path 使用默认主配置路径解析规则）。
        """
        return cls(base_dir=base_dir)

    # ------------------------------------------------------------------
    # 各类生成任务封装
    # ------------------------------------------------------------------
    def log_task_start(self, *, step: str, domain: str) -> float:
        started = time.perf_counter()
        logger.info("[TaskService] event=start domain=%s step=%s", domain, step)
        return started

    def log_task_done(self, *, step: str, domain: str, elapsed_ms: float) -> None:
        logger.info(
            "[TaskService] event=done domain=%s step=%s success=true elapsed_ms=%.1f",
            domain,
            step,
            elapsed_ms,
        )

    def log_task_skip(self, *, step: str, domain: str, reason: str, elapsed_ms: float) -> None:
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
        logger.error(
            "[TaskService] event=failed domain=%s step=%s error_type=%s error=%s elapsed_ms=%.1f",
            domain,
            step,
            type(error).__name__,
            error,
            elapsed_ms,
        )

    def run_can(self, domain: str = DEFAULT_DOMAIN_LR_REAR) -> TaskResult:
        """运行 CAN 生成任务。

        功能：调用 generators.capl_can.entrypoint.main（传入 base_dir 与 config_path）；中央域未配置 input_excel 时按"跳过"处理不视为失败。

        形参：domain — 业务域（LR_REAR / CENTRAL / DTC），默认 LR_REAR。
        返回：TaskResult（success、message、detail）。
        """
        started = self.log_task_start(step="can", domain=domain)
        try:
            run_can_generation(
                config_path=self.config_path,
                base_dir=self.base_dir,
                domain=domain,
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

    def run_xml(self, domain: str = DEFAULT_DOMAIN_LR_REAR) -> TaskResult:
        """运行 XML 生成任务。

        功能：调用 generators.capl_xml.entrypoint.main（传入 base_dir 与 config_path）；中央域未配置 Xml_Input_Excel 时按"跳过"处理。

        形参：domain — 业务域，默认 LR_REAR。
        返回：TaskResult（success、message、detail）。
        """
        started = self.log_task_start(step="xml", domain=domain)
        try:
            run_xml_generation(
                config_path=self.config_path,
                base_dir=self.base_dir,
                domain=domain,
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
        """运行 CIN 生成任务。

        功能：调用 generators.capl_cin.entrypoint.main；domain 用于按域加载 io_mapping 与日志级别。

        形参：domain — 业务域（LR_REAR / CENTRAL / DTC），默认 LR_REAR。
        返回：TaskResult（success、message、detail）。
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
        """运行 ResetDid(DIDInfo) 生成任务。

        功能：调用 generators.capl_resetdid.entrypoint.main；未配置 ResetDid_Value 配置表时按"跳过"处理不视为失败。

        形参：domain — 为 ``DTC`` 时从 ``[DTC]`` 定点读取 didinfo 输入/输出；未传则沿用 LR/PATHS 逻辑。
        返回：TaskResult（success、message、detail）。
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
        """运行 DIDConfig 生成任务。

        功能：调用 generators.capl_didconfig.entrypoint.main。

        形参：domain — 为 ``DTC`` 时从 ``[DTC_CONFIG_ENUM]`` / ``[DTC]`` 定点读配置；未传则沿用 ``[DID_CONFIG]``。
        返回：TaskResult（success、message、detail）。
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

    def run_uart(self) -> TaskResult:
        """运行 UART 生成任务。

        功能：调用 generators.capl_uart.entrypoint.main。

        形参：无。
        返回：TaskResult（success、message、detail）。
        """
        started = self.log_task_start(step="uart", domain=SECTION_CENTRAL)
        try:
            run_uart_generation()
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
        """运行 SOA Node 生成任务（中央域服务通信矩阵）。"""
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

