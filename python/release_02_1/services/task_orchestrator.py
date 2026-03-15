#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业务逻辑层（TaskOrchestrator）

目标：收纳 generate_lr、generate_central、generate_dtc 的组合逻辑。
职责：不关心 HTTP 请求，只负责：校验（可选）-> 调用底层生成器 -> 收集成功/失败清单。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.config_manager import ConfigManager
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
    "LR_REAR": ["did_config", "did_info", "cin", "uart", "can", "xml"],
    "CENTRAL": ["uart", "can", "xml"],
    "DTC": ["did_config", "did_info", "cin", "can", "xml"],
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

    def _patch_config_for_dtc_did_cin(self) -> Optional[Dict[str, Dict[str, str]]]:
        """
        运行 DTC 的 DID/CIN 前：把 [DTC] / [DTC_CONFIG_ENUM] 的路径临时写入 [DID_CONFIG] / [LR_REAR]，
        以便现有生成器（只读 DID_CONFIG/LR_REAR）能用到 DTC 的表。返回 backup 供 _restore_config_after_dtc_did_cin 恢复。
        """
        cfg = self._config_manager._reload()
        if not cfg.has_section("DTC"):
            return None
        backup: Dict[str, Dict[str, str]] = {}
        if cfg.has_section("DID_CONFIG"):
            backup["DID_CONFIG"] = dict(cfg.items("DID_CONFIG"))
        if cfg.has_section("LR_REAR"):
            backup["LR_REAR"] = dict(cfg.items("LR_REAR"))

        d = dict(cfg.items("DTC"))
        out_dir = (d.get("output_dir") or "").strip()
        didinfo = (d.get("didinfo_inputs") or "").strip()
        cin_excel = (d.get("cin_input_excel") or "").strip()

        if not cfg.has_section("DID_CONFIG"):
            cfg.add_section("DID_CONFIG")
        if cfg.has_section("DTC_CONFIG_ENUM"):
            inputs_raw = (cfg.get("DTC_CONFIG_ENUM", "inputs", fallback="") or "").strip()
            first = inputs_raw.split("|")[0].strip() if inputs_raw else ""
            if first:
                cfg.set("DID_CONFIG", "input_excel", first)
        if out_dir:
            cfg.set("DID_CONFIG", "output_dir", out_dir)

        if not cfg.has_section("LR_REAR"):
            cfg.add_section("LR_REAR")
        if out_dir:
            cfg.set("LR_REAR", "output_dir", out_dir)
        if didinfo:
            cfg.set("LR_REAR", "didinfo_inputs", didinfo)
        if cin_excel:
            cfg.set("LR_REAR", "cin_input_excel", cin_excel)

        # 仅针对 DTC 域相关配置做 patch，因此附带生成的 uds 也只限定在 DTC
        self._config_manager._write_formatted_config(cfg, uds_domains=["DTC"])
        return backup

    def _restore_config_after_dtc_did_cin(
        self,
        backup: Optional[Dict[str, Dict[str, str]]],
        *,
        uds_domain: str,
    ) -> None:
        """DTC 的 DID/CIN 跑完后恢复 [DID_CONFIG] / [LR_REAR]，避免覆盖第一界面配置。"""
        if not backup:
            return
        cfg = self._config_manager._reload()
        for section, items in backup.items():
            if not cfg.has_section(section):
                cfg.add_section(section)
            for key in list(cfg.options(section)):
                cfg.remove_option(section, key)
            for key, value in items.items():
                cfg.set(section, key, value)
        # 恢复后只刷当前任务域的 uds，避免其它域被连带覆盖
        self._config_manager._write_formatted_config(cfg, uds_domains=[uds_domain])

    def _patch_did_config_output_dir_for_domain(
        self,
        config_section: str,
    ) -> Optional[Dict[str, Dict[str, str]]]:
        """
        运行 DIDConfig 前：把当前域的 output_dir 临时写入 [DID_CONFIG]，
        使「在哪个界面运行就生成到哪里」。返回 DID_CONFIG 备份供结束后恢复。
        仅当 [DID_CONFIG] 已存在时才 patch，避免新建只有 output_dir 的节导致生成器因缺 input_excel 直接不生成。
        """
        cfg = self._config_manager._reload()
        if not cfg.has_section(config_section):
            return None
        out_dir = (cfg.get(config_section, "output_dir", fallback="") or "").strip()
        if not out_dir:
            return None
        if not cfg.has_section("DID_CONFIG"):
            return None
        backup: Dict[str, Dict[str, str]] = {"DID_CONFIG": dict(cfg.items("DID_CONFIG"))}
        cfg.set("DID_CONFIG", "output_dir", out_dir)
        # 仅针对当前域的 DIDConfig 输出目录做 patch，对应 uds 也只生成当前域
        self._config_manager._write_formatted_config(cfg, uds_domains=[config_section])
        return backup

    def _restore_did_config(
        self,
        backup: Optional[Dict[str, Dict[str, str]]],
        *,
        uds_domain: str,
    ) -> None:
        """DIDConfig 跑完后恢复 [DID_CONFIG]（仅恢复 output_dir 等，不破坏其它节）。"""
        if not backup:
            return
        self._restore_config_after_dtc_did_cin(backup, uds_domain=uds_domain)

    def _resolve_uart_path(self) -> Optional[str]:
        """解析 UART 矩阵文件路径；不存在则返回 None。"""
        cfg = self._config_manager._reload()
        base_dir = self._task_service.base_dir
        uart_excel_raw = ""
        if cfg.has_section("CENTRAL"):
            uart_excel_raw = (cfg.get("CENTRAL", "uart_excel", fallback="") or "").strip()
        if not uart_excel_raw and cfg.has_section("PATHS"):
            uart_excel_raw = (cfg.get("PATHS", "Uart_Input_Excel", fallback="") or "").strip()
        if not uart_excel_raw:
            uart_excel_raw = "input/MCU_CDCU_CommunicationMatrix.xlsx"
        path = uart_excel_raw.replace("/", os.sep)
        if not os.path.isabs(path):
            path = os.path.join(base_dir, path)
        path = os.path.normpath(path)
        return path if os.path.isfile(path) else None

    def _run_generic_bundle(
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
        from services.run_validator import validate_for_domain

        reset_run_context()
        set_run_domain(config_section)
        messages: List[str] = []
        detail_parts: List[str] = []
        results: Dict[str, TaskResult] = {}

        if validate_before_run:
            ok, errors = validate_for_domain(
                config_section,
                self._task_service.base_dir,
                self._task_service.config_path,
                self._config_manager,
            )
            if not ok:
                return OrchestratorResult(
                    success=False,
                    messages=["校验未通过"],
                    detail="\n".join(errors),
                    extra=None,
                )

        steps = _BUNDLE_SPEC.get(config_section, [])
        dtc_did_cin_backup: Optional[Dict[str, Dict[str, str]]] = None
        if config_section == "DTC":
            dtc_did_cin_backup = self._patch_config_for_dtc_did_cin()
        # 只要当前任务流包含 did_config，就先把 [DID_CONFIG].output_dir 同步为当前域的输出目录，避免路径“写死”
        did_config_output_backup: Optional[Dict[str, Dict[str, str]]] = None
        if "did_config" in steps and run_did:
            did_config_output_backup = self._patch_did_config_output_dir_for_domain(config_section)

        for step in steps:
            if step == "did_config":
                if not run_did:
                    continue
                r = self._task_service.run_did_config()
                results["did_config"] = r
                messages.append(r.message)
                if not r.success:
                    if dtc_did_cin_backup is not None:
                        self._restore_config_after_dtc_did_cin(
                            dtc_did_cin_backup, uds_domain=config_section
                        )
                    if did_config_output_backup is not None:
                        self._restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=r.detail or "", extra=results)
                if r.detail:
                    detail_parts.append(r.detail)

            elif step == "did_info":
                if not run_did:
                    continue
                r = self._task_service.run_did_info()
                results["did_info"] = r
                messages.append(r.message)
                if not r.success:
                    if dtc_did_cin_backup is not None:
                        self._restore_config_after_dtc_did_cin(
                            dtc_did_cin_backup, uds_domain=config_section
                        )
                    if did_config_output_backup is not None:
                        self._restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=r.detail or "", extra=results)
                if r.detail:
                    detail_parts.append(r.detail)

            elif step == "cin":
                if not run_cin:
                    continue
                r = self._task_service.run_cin(domain=config_section)
                results["cin"] = r
                messages.append(r.message)
                if not r.success:
                    if dtc_did_cin_backup is not None:
                        self._restore_config_after_dtc_did_cin(
                            dtc_did_cin_backup, uds_domain=config_section
                        )
                    if did_config_output_backup is not None:
                        self._restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=r.detail or "", extra=results)
                if r.detail:
                    detail_parts.append(r.detail)

            elif step == "uart":
                # 仅中央域执行 UART 生成并创建 generate_uart_from_config.log；左右后域/DTC 不涉及 UART 则不生成该日志
                if not run_uart or config_section != "CENTRAL":
                    continue
                uart_path = self._resolve_uart_path()
                if uart_path:
                    r = self._task_service.run_uart()
                    results["uart"] = r
                    messages.append(r.message)
                    if not r.success:
                        if did_config_output_backup is not None:
                            self._restore_did_config(did_config_output_backup)
                        return OrchestratorResult(success=False, messages=messages, detail=r.detail or "", extra=results)
                    if r.detail:
                        detail_parts.append(r.detail)
                else:
                    messages.append("跳过 UART 生成（未配置有效矩阵文件）")

            elif step == "can":
                if not run_can:
                    continue
                r = self._task_service.run_can(domain=config_section)
                results["can"] = r
                messages.append(r.message)
                if not r.success:
                    if did_config_output_backup is not None:
                        self._restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=r.detail or "", extra=results)
                if r.detail:
                    detail_parts.append(r.detail)

            elif step == "xml":
                if not run_xml:
                    continue
                r = self._task_service.run_xml(domain=config_section)
                results["xml"] = r
                messages.append(r.message)
                if not r.success:
                    if dtc_did_cin_backup is not None:
                        self._restore_config_after_dtc_did_cin(
                            dtc_did_cin_backup, uds_domain=config_section
                        )
                    if did_config_output_backup is not None:
                        self._restore_did_config(
                            did_config_output_backup, uds_domain=config_section
                        )
                    return OrchestratorResult(success=False, messages=messages, detail=r.detail or "", extra=results)
                if r.detail:
                    detail_parts.append(r.detail)

        if dtc_did_cin_backup is not None:
            self._restore_config_after_dtc_did_cin(
                dtc_did_cin_backup, uds_domain=config_section
            )
        if did_config_output_backup is not None:
            self._restore_did_config(did_config_output_backup, uds_domain=config_section)

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
        return self._run_generic_bundle(
            "LR_REAR",
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
        return self._run_generic_bundle(
            "CENTRAL",
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
        return self._run_generic_bundle(
            "DTC",
            run_can=run_can,
            run_xml=run_xml,
            run_cin=run_cin,
            run_did=run_did,
            run_uart=False,
            validate_before_run=validate_before_run,
        )
