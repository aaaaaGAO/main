#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务服务（TaskService）

职责：
- 作为 Web 层与 generators 包内入口之间的“调度中间层”
- 统一封装：运行哪个生成任务（CAN / XML / CIN / DIDINFO / DIDCONFIG / UART）、
  base_dir / config_path、异常捕获与结果封装。
- 调用方式：from generators.capl_can.entrypoint import main，不再依赖根目录 generate_*.py。
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass
from typing import Any, Dict, Optional

from infra.filesystem import resolve_main_config_path
from services.config_constants import DEFAULT_DOMAIN_LR_REAR, SECTION_CENTRAL
from generators.capl_can.entrypoint import main as can_main
from generators.capl_cin.entrypoint import main as cin_main
from generators.capl_didconfig.entrypoint import main as didconfig_main
from generators.capl_didinfo.entrypoint import main as didinfo_main
from generators.capl_uart.entrypoint import main as uart_main
from generators.capl_xml.entrypoint import main as xml_main


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
    def run_can(self, domain: str = DEFAULT_DOMAIN_LR_REAR) -> TaskResult:
        """运行 CAN 生成任务。

        功能：切换工作目录到 self.base_dir 后调用 generators.capl_can.entrypoint.main；中央域未配置 input_excel 时按“跳过”处理不视为失败。

        形参：domain — 业务域（LR_REAR / CENTRAL / DTC），默认 LR_REAR。
        返回：TaskResult（success、message、detail）。
        """
        try:
            # 确保工作目录在工程根目录，便于底层脚本按相对路径找到配置/输入文件
            os.chdir(self.base_dir)
            can_main(
                config_path=self.config_path,
                base_dir=self.base_dir,
                domain=domain,
            )
            return TaskResult(success=True, message=f"{domain} CAN 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            error_message = str(error)
            # 对中央域做“无用例则安静跳过”的特殊处理：不再视为失败，只返回提示信息
            if (
                domain == SECTION_CENTRAL
                and "未配置输入路径：请配置 [CENTRAL] 的 input_excel" in error_message
            ):
                print(f"CAN 执行跳过（中央域未配置 input_excel）: {error}")
                return TaskResult(
                    success=True,
                    message="CENTRAL CAN 未生成（未配置输入路径，已按要求跳过）",
                    detail=traceback_text,
                )
            # 其它异常仍按失败处理，便于前端与日志排查
            print(f"CAN 执行崩溃: {error}")
            return TaskResult(
                success=False,
                message=f"{domain} CAN 生成失败: {error}",
                detail=traceback_text,
            )

    def run_xml(self, domain: str = DEFAULT_DOMAIN_LR_REAR) -> TaskResult:
        """运行 XML 生成任务。

        功能：切换工作目录后调用 generators.capl_xml.entrypoint.main；中央域未配置 Xml_Input_Excel 时按“跳过”处理。

        形参：domain — 业务域，默认 LR_REAR。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            print(
                f"[TaskService.run_xml] cwd={os.getcwd()!r}, config_path={self.config_path!r}, "
                f"base_dir={self.base_dir!r}, domain={domain!r}"
            )
            # 传递 base_dir 和 config_path，保持与 CAN 生成使用同一份配置
            xml_main(
                config_path=self.config_path,
                base_dir=self.base_dir,
                domain=domain,
            )
            return TaskResult(success=True, message=f"{domain} XML 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            error_message = str(error)
            # 中央域未配置 XML 输入 Excel 时也按“跳过”处理
            if (
                domain == SECTION_CENTRAL
                and "未配置 Xml_Input_Excel 或 xml_input_excel" in error_message
            ):
                print(
                    f"[TaskService.run_xml] 中央域未配置 Xml_Input_Excel，按要求跳过 XML 生成: {error}"
                )
                return TaskResult(
                    success=True,
                    message="CENTRAL XML 未生成（未配置 Xml_Input_Excel，已按要求跳过）",
                    detail=traceback_text,
                )
            print(f"[TaskService.run_xml] XML 生成报错详情:\n{traceback_text}")
            return TaskResult(
                success=False,
                message=f"{domain} XML 生成失败: {error}",
                detail=traceback_text,
            )

    def run_cin(self, domain: str = DEFAULT_DOMAIN_LR_REAR) -> TaskResult:
        """运行 CIN 生成任务。

        功能：切换工作目录后调用 generators.capl_cin.entrypoint.main；domain 用于按域加载 io_mapping 与日志级别。

        形参：domain — 业务域（LR_REAR / CENTRAL / DTC），默认 LR_REAR。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            cin_main(domain=domain)
            return TaskResult(success=True, message=f"{domain} CIN 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            return TaskResult(
                success=False,
                message=f"{domain} CIN 生成失败: {error}",
                detail=traceback_text,
            )

    def run_did_info(self) -> TaskResult:
        """运行 DIDInfo 生成任务。

        功能：切换工作目录后调用 generators.capl_didinfo.entrypoint.main；未配置 ResetDid_Value 配置表时按“跳过”处理不视为失败。

        形参：无。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            didinfo_main()
            return TaskResult(success=True, message="DIDInfo 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            error_message = str(error)
            # 未配置 ResetDid_Value 配置表时，按“静默跳过”处理，不视为失败，只返回提示信息
            if "未配置 ResetDid_Value 配置表" in error_message:
                print(f"DIDInfo 执行跳过（未配置 ResetDid_Value 配置表）: {error}")
                return TaskResult(
                    success=True,
                    message="DIDInfo 未生成（未配置 ResetDid_Value 配置表，已按要求跳过）",
                    detail=traceback_text,
                )
            return TaskResult(
                success=False,
                message=f"DIDInfo 生成失败: {error}",
                detail=traceback_text,
            )

    def run_did_config(self) -> TaskResult:
        """运行 DIDConfig 生成任务。

        功能：切换工作目录后调用 generators.capl_didconfig.entrypoint.main。

        形参：无。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            didconfig_main()
            return TaskResult(success=True, message="DIDConfig 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            error_message = str(error)
            # 未配置 DID_Config 配置表/节时，按“静默跳过”处理，不视为失败，只返回提示信息
            if "未配置 DID_Config 配置表" in error_message or "未配置 DID_Config 配置节" in error_message:
                print(f"DIDConfig 执行跳过（{error_message}）: {error}")
                return TaskResult(
                    success=True,
                    message="DIDConfig 未生成（未配置 DID_Config 配置表，已按要求跳过）",
                    detail=traceback_text,
                )
            return TaskResult(
                success=False,
                message=f"DIDConfig 生成失败: {error}",
                detail=traceback_text,
            )

    def run_uart(self) -> TaskResult:
        """运行 UART 生成任务。

        功能：切换工作目录后调用 generators.capl_uart.entrypoint.main。

        形参：无。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            uart_main()
            return TaskResult(success=True, message="UART 生成完成")
        except Exception as error:
            traceback_text = traceback.format_exc()
            return TaskResult(
                success=False,
                message=f"UART 生成失败: {error}",
                detail=traceback_text,
            )

