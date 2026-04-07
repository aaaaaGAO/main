#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业务逻辑层（TaskOrchestrator）

目标：收纳 generate_lr、generate_central、generate_dtc 的组合逻辑。
职责：不关心 HTTP 请求，只负责：校验（可选）-> 调用底层生成器 -> 收集成功/失败清单。
"""

from __future__ import annotations

import os
from configparser import ConfigParser
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.config_manager import ConfigManager
from services.config_constants import (
    OPTION_CIN_INPUT_EXCEL,
    OPTION_DIDINFO_INPUTS,
    OPTION_INPUT_EXCEL,
    OPTION_INPUTS,
    OPTION_OUTPUT_DIR,
    SECTION_CENTRAL,
    SECTION_DID_CONFIG,
    SECTION_DTC,
    SECTION_DTC_CONFIG_ENUM,
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
    SECTION_LR_REAR: ["did_config", "did_info", "cin", "uart", "can", "xml"],
    SECTION_CENTRAL: ["uart", "can", "xml"],
    SECTION_DTC: ["did_config", "did_info", "cin", "can", "xml"],
}


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
        self._config_manager = ConfigManager.from_base_dir(base_dir)
        self._task_service = TaskService(base_dir=base_dir, config_path=config_path)

    @classmethod
    def from_base_dir(cls, base_dir: str, config_path: Optional[str] = None) -> "TaskOrchestrator":
        """从项目根目录创建编排器。参数: base_dir — 项目根；config_path — 可选主配置路径。返回: TaskOrchestrator 实例。"""
        return cls(base_dir=base_dir, config_path=config_path)

    @property
    def config_manager(self) -> ConfigManager:
        return self._config_manager

    @property
    def task_service(self) -> TaskService:
        return self._task_service

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
        uds_path = self._config_manager.resolve_uds_output_path(config, section)
        if uds_path and os.path.isfile(uds_path):
            message += f"{separator}UDS.txt 生成完成"
        return message

    def patch_config_for_dtc_did_cin(self) -> Optional[Dict[str, Dict[str, str]]]:
        """
        运行 DTC 的 DID/CIN 前：把 [DTC] / [DTC_CONFIG_ENUM] 的路径临时写入 [DID_CONFIG] / [LR_REAR]，
        以便现有生成器（只读 DID_CONFIG/LR_REAR）能用到 DTC 的表。返回 backup 供 restore_config_after_dtc_did_cin 恢复。
        """
        config = self._config_manager.load_config()
        if not config.has_section(SECTION_DTC):
            return None
        backup: Dict[str, Dict[str, str]] = {}
        if config.has_section(SECTION_DID_CONFIG):
            backup[SECTION_DID_CONFIG] = dict(config.items(SECTION_DID_CONFIG))
        if config.has_section(SECTION_LR_REAR):
            backup[SECTION_LR_REAR] = dict(config.items(SECTION_LR_REAR))

        dtc_section = dict(config.items(SECTION_DTC))
        output_dir = (dtc_section.get(OPTION_OUTPUT_DIR) or "").strip()
        didinfo_inputs = (dtc_section.get(OPTION_DIDINFO_INPUTS) or "").strip()
        cin_excel = (dtc_section.get(OPTION_CIN_INPUT_EXCEL) or "").strip()

        # 判断 DTC 界面是否“真正配置了自己专用的 DID/DIDInfo/Clib 表”
        dtc_config_enum_inputs_raw = ""
        if config.has_section(SECTION_DTC_CONFIG_ENUM):
            dtc_config_enum_inputs_raw = (
                config.get(SECTION_DTC_CONFIG_ENUM, OPTION_INPUTS, fallback="") or ""
            ).strip()
        dtc_cfg_enum_first = (
            dtc_config_enum_inputs_raw.replace(";", "|").split("|")[0].strip()
            if dtc_config_enum_inputs_raw
            else ""
        )
        has_any_dtc_tables = bool(dtc_cfg_enum_first or didinfo_inputs or cin_excel)

        # 如果第三个界面根本没配这些表，就认为本次应“按要求跳过 DID/DIDInfo”，
        # 因此要临时隐藏全局 [DID_CONFIG]/[LR_REAR] 中与 DID 相关的路径，避免误用第一个界面的配置。
        if not has_any_dtc_tables:
            if config.has_section(SECTION_DID_CONFIG) and config.has_option(
                SECTION_DID_CONFIG, OPTION_INPUT_EXCEL
            ):
                config.remove_option(SECTION_DID_CONFIG, OPTION_INPUT_EXCEL)
            if config.has_section(SECTION_LR_REAR):
                for option_name in (OPTION_DIDINFO_INPUTS, OPTION_CIN_INPUT_EXCEL):
                    if config.has_option(SECTION_LR_REAR, option_name):
                        config.remove_option(SECTION_LR_REAR, option_name)
            # 仅针对 DTC 域相关配置做 patch，因此附带生成的 uds 也只限定在 DTC
            self._config_manager.save_formatted_config(config, uds_domains=[SECTION_DTC])
            return backup

        if not config.has_section(SECTION_DID_CONFIG):
            config.add_section(SECTION_DID_CONFIG)
        if config.has_section(SECTION_DTC_CONFIG_ENUM):
            if dtc_cfg_enum_first:
                config.set(SECTION_DID_CONFIG, OPTION_INPUT_EXCEL, dtc_cfg_enum_first)
        if output_dir:
            config.set(SECTION_DID_CONFIG, OPTION_OUTPUT_DIR, output_dir)

        if not config.has_section(SECTION_LR_REAR):
            config.add_section(SECTION_LR_REAR)
        if output_dir:
            config.set(SECTION_LR_REAR, OPTION_OUTPUT_DIR, output_dir)
        if didinfo_inputs:
            config.set(SECTION_LR_REAR, OPTION_DIDINFO_INPUTS, didinfo_inputs)
        if cin_excel:
            config.set(SECTION_LR_REAR, OPTION_CIN_INPUT_EXCEL, cin_excel)

        # 仅针对 DTC 域相关配置做 patch，因此附带生成的 uds 也只限定在 DTC
        self._config_manager.save_formatted_config(config, uds_domains=[SECTION_DTC])
        return backup

    def restore_config_after_dtc_did_cin(
        self,
        backup: Optional[Dict[str, Dict[str, str]]],
        *,
        uds_domain: str,
    ) -> None:
        """DTC 的 DID/CIN 跑完后恢复 [DID_CONFIG] / [LR_REAR]，避免覆盖第一界面配置。"""
        if not backup:
            return
        config = self._config_manager.load_config()
        for section, items in backup.items():
            if not config.has_section(section):
                config.add_section(section)
            for option_name in list(config.options(section)):
                config.remove_option(section, option_name)
            for option_name, option_value in items.items():
                config.set(section, option_name, option_value)
        # 恢复后只刷当前任务域的 uds，避免其它域被连带覆盖
        self._config_manager.save_formatted_config(config, uds_domains=[uds_domain])

    def patch_did_config_output_dir_for_domain(
        self,
        config_section: str,
    ) -> Optional[Dict[str, Dict[str, str]]]:
        """
        运行 DIDConfig 前：把当前域的 output_dir 临时写入 [DID_CONFIG]，
        使「在哪个界面运行就生成到哪里」。返回 DID_CONFIG 备份供结束后恢复。
        仅当 [DID_CONFIG] 已存在时才 patch，避免新建只有 output_dir 的节导致生成器因缺 input_excel 直接不生成。
        """
        config = self._config_manager.load_config()
        if not config.has_section(config_section):
            return None
        output_dir = (config.get(config_section, OPTION_OUTPUT_DIR, fallback="") or "").strip()
        if not output_dir:
            return None
        if not config.has_section(SECTION_DID_CONFIG):
            return None
        backup: Dict[str, Dict[str, str]] = {
            SECTION_DID_CONFIG: dict(config.items(SECTION_DID_CONFIG))
        }
        config.set(SECTION_DID_CONFIG, OPTION_OUTPUT_DIR, output_dir)
        # 仅针对当前域的 DIDConfig 输出目录做 patch，对应 uds 也只生成当前域
        self._config_manager.save_formatted_config(config, uds_domains=[config_section])
        return backup

    def restore_did_config(
        self,
        backup: Optional[Dict[str, Dict[str, str]]],
        *,
        uds_domain: str,
    ) -> None:
        """DIDConfig 跑完后恢复 [DID_CONFIG]（仅恢复 output_dir 等，不破坏其它节）。"""
        if not backup:
            return
        self.restore_config_after_dtc_did_cin(backup, uds_domain=uds_domain)

    def resolve_uart_path(self, config: Optional[ConfigParser] = None) -> Optional[str]:
        """解析 UART 矩阵文件路径；文件不存在则返回 None。"""
        if config is None:
            config = self._config_manager.load_config()
        base_dir = self._task_service.base_dir
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
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """
        通用域编排：按 _BUNDLE_SPEC 顺序执行 did_config → did_info → cin → uart(可选) → can → xml。
        config_section 为 "LR_REAR" | "CENTRAL" | "DTC"。
        """
        reset_run_context()
        set_run_domain(config_section)
        messages: List[str] = []
        detail_parts: List[str] = []
        results: Dict[str, TaskResult] = {}

        if validate_before_run:
            is_valid, errors = validate_for_domain(
                config_section,
                self._task_service.base_dir,
                self._task_service.config_path,
                self._config_manager,
            )
            if not is_valid:
                return OrchestratorResult(
                    success=False,
                    messages=["校验未通过"],
                    detail="\n".join(errors),
                    extra=None,
                )

        bundle_steps = _BUNDLE_SPEC.get(config_section, [])
        dtc_did_cin_backup: Optional[Dict[str, Dict[str, str]]] = None
        if config_section == SECTION_DTC:
            dtc_did_cin_backup = self.patch_config_for_dtc_did_cin()
        # 只要当前任务流包含 did_config，就先把 [DID_CONFIG].output_dir 同步为当前域的输出目录，避免路径“写死”
        did_config_output_backup: Optional[Dict[str, Dict[str, str]]] = None
        if "did_config" in bundle_steps and run_did:
            did_config_output_backup = self.patch_did_config_output_dir_for_domain(config_section)

        for bundle_step in bundle_steps:
            if bundle_step == "did_config":
                if not run_did:
                    continue
                task_result = self._task_service.run_did_config()
                results["did_config"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    if dtc_did_cin_backup is not None:
                        self.restore_config_after_dtc_did_cin(
                            dtc_did_cin_backup, uds_domain=config_section
                        )
                    if did_config_output_backup is not None:
                        self.restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                if task_result.detail:
                    detail_parts.append(task_result.detail)

            elif bundle_step == "did_info":
                if not run_did:
                    continue
                task_result = self._task_service.run_did_info()
                results["did_info"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    if dtc_did_cin_backup is not None:
                        self.restore_config_after_dtc_did_cin(
                            dtc_did_cin_backup, uds_domain=config_section
                        )
                    if did_config_output_backup is not None:
                        self.restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                if task_result.detail:
                    detail_parts.append(task_result.detail)

            elif bundle_step == "cin":
                if not run_cin:
                    continue
                task_result = self._task_service.run_cin(domain=config_section)
                results["cin"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    if dtc_did_cin_backup is not None:
                        self.restore_config_after_dtc_did_cin(
                            dtc_did_cin_backup, uds_domain=config_section
                        )
                    if did_config_output_backup is not None:
                        self.restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                if task_result.detail:
                    detail_parts.append(task_result.detail)

            elif bundle_step == "uart":
                # 仅中央域执行 UART 生成并创建 generate_uart_from_config.log；左右后域/DTC 不涉及 UART 则不生成该日志
                if not run_uart or config_section != SECTION_CENTRAL:
                    continue
                cfg = self._config_manager.load_config()
                uart_matrix_path = self.resolve_uart_path(cfg)
                has_uart_comm = cfg.has_section(SECTION_CENTRAL) and any(
                    cfg.has_option(SECTION_CENTRAL, key) for key in UART_COMM_CFG_KEYS
                )
                if uart_matrix_path or has_uart_comm:
                    task_result = self._task_service.run_uart()
                    results["uart"] = task_result
                    messages.append(task_result.message)
                    if not task_result.success:
                        if did_config_output_backup is not None:
                            self.restore_did_config(
                                did_config_output_backup, uds_domain=config_section
                            )
                        return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                    if task_result.detail:
                        detail_parts.append(task_result.detail)
                else:
                    messages.append(
                        "跳过 UART 生成（无有效矩阵文件且 [CENTRAL] 未配置 uart_comm_*）"
                    )

            elif bundle_step == "can":
                if not run_can:
                    continue
                task_result = self._task_service.run_can(domain=config_section)
                results["can"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    if did_config_output_backup is not None:
                        self.restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                if task_result.detail:
                    detail_parts.append(task_result.detail)

            elif bundle_step == "xml":
                if not run_xml:
                    continue
                task_result = self._task_service.run_xml(domain=config_section)
                results["xml"] = task_result
                messages.append(task_result.message)
                if not task_result.success:
                    if dtc_did_cin_backup is not None:
                        self.restore_config_after_dtc_did_cin(
                            dtc_did_cin_backup, uds_domain=config_section
                        )
                    if did_config_output_backup is not None:
                        self.restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=task_result.detail or "", extra=results)
                if task_result.detail:
                    detail_parts.append(task_result.detail)

        if dtc_did_cin_backup is not None:
            self.restore_config_after_dtc_did_cin(
                dtc_did_cin_backup, uds_domain=config_section
            )
        if did_config_output_backup is not None:
            self.restore_did_config(did_config_output_backup, uds_domain=config_section)

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
        run_uart: bool = False,
        validate_before_run: bool = True,
    ) -> OrchestratorResult:
        """左右后域一键生成：DID → CIN → [UART 可选] → CAN → XML。
        参数: run_can/run_xml/run_cin/run_did — 是否执行对应生成；run_uart — 是否生成 UART；validate_before_run — 是否先校验。
        返回: OrchestratorResult（success、messages、detail）。
        """
        return self.run_generic_bundle(
            SECTION_LR_REAR,
            run_can=run_can,
            run_xml=run_xml,
            run_cin=run_cin,
            run_did=run_did,
            run_uart=run_uart,
            validate_before_run=validate_before_run,
        )

    def run_central_bundle(
        self,
        run_can: bool = True,
        run_xml: bool = True,
        run_uart: bool = True,
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
            validate_before_run=validate_before_run,
        )

    def run_dtc_bundle(
        self,
        run_can: bool = True,
        run_xml: bool = True,
        run_cin: bool = True,
        run_did: bool = True,
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
            run_uart=False,
            validate_before_run=validate_before_run,
        )
