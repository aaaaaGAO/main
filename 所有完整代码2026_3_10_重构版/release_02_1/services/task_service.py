#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务服务（TaskService）

职责：
- 作为 Web 层与底层 generate_*.py 脚本之间的“调度中间层”
- 统一封装：
  - 运行哪个生成任务（CAN / XML / CIN / DIDINFO / DIDCONFIG / UART）
  - 使用哪个 base_dir / config_path
  - 异常捕获与结果封装

使用场景：
- 在 web.routes.lr_rear / web.routes.central 中，通过 TaskService 触发实际的生成任务，
  避免在路由里直接 import generate_xxx 并写大量 try/except。
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass
from typing import Any, Dict, Optional

import generate_can_from_excel as can_gen
import generate_cin_from_excel as cin_gen
import generate_did_config as didconfig_gen
import generate_didinfo_from_excel as didinfo_gen
import generate_uart_from_config as uart_gen
import generate_xml_from_can as xml_gen


@dataclass
class TaskResult:
    """统一的任务执行结果结构，供 Web 层与编排层使用。
    属性：success — 是否成功；message — 简要消息；detail — 详情（如 traceback）；extra — 可选扩展数据。
    """

    success: bool
    message: str
    detail: str = ""
    extra: Dict[str, Any] | None = None


class TaskService:
    """生成任务调度服务：封装对各 generate_*.py 的调用与异常处理。"""

    def __init__(self, base_dir: str, config_path: Optional[str] = None) -> None:
        """初始化任务服务，绑定工程根目录与配置文件路径。
        参数：base_dir — 工程根目录；config_path — 配置文件路径，None 时在 base_dir 下查找 Configuration.txt。
        返回：无返回值。
        """
        self.base_dir = os.path.abspath(base_dir)
        if config_path is None:
            # 默认使用工程根下的 Configuration.txt / Configuration_can.txt
            cfg = os.path.join(self.base_dir, "Configuration.txt")
            if not os.path.exists(cfg):
                alt = os.path.join(self.base_dir, "Configuration_can.txt")
                cfg = alt if os.path.exists(alt) else cfg
            self.config_path = cfg
        else:
            self.config_path = os.path.abspath(config_path)

    # ------------------------------------------------------------------
    # 构造快捷方法
    # ------------------------------------------------------------------
    @classmethod
    def from_base_dir(cls, base_dir: str) -> "TaskService":
        """从工程根目录创建 TaskService 实例。参数：base_dir — 工程根目录。返回：TaskService 实例。"""
        return cls(base_dir=base_dir)

    # ------------------------------------------------------------------
    # 各类生成任务封装
    # ------------------------------------------------------------------
    def run_can(self, domain: str = "LR_REAR") -> TaskResult:
        """运行 CAN 生成任务：切换工作目录后调用 generate_can_from_excel.main。
        参数：domain — 业务域，默认 LR_REAR。
        返回：TaskResult（success、message、detail）。
        """
        try:
            # 确保工作目录在工程根目录，便于底层脚本按相对路径找到配置/输入文件
            os.chdir(self.base_dir)
            can_gen.main(
                config_path=self.config_path,
                base_dir=self.base_dir,
                domain=domain,
            )
            return TaskResult(success=True, message=f"{domain} CAN 生成完成")
        except Exception as e:
            tb = traceback.format_exc()
            msg = str(e)
            # 对中央域做“无用例则安静跳过”的特殊处理：不再视为失败，只返回提示信息
            if domain == "CENTRAL" and "未配置输入路径：请配置 [CENTRAL] 的 input_excel" in msg:
                print(f"CAN 执行跳过（中央域未配置 input_excel）: {e}")
                return TaskResult(
                    success=True,
                    message="CENTRAL CAN 未生成（未配置输入路径，已按要求跳过）",
                    detail=tb,
                )
            # 其它异常仍按失败处理，便于前端与日志排查
            print(f"CAN 执行崩溃: {e}")
            return TaskResult(success=False, message=f"{domain} CAN 生成失败: {e}", detail=tb)

    def run_xml(self, domain: str = "LR_REAR") -> TaskResult:
        """运行 XML 生成任务：切换工作目录后调用 generate_xml_from_can.main。
        参数：domain — 业务域，默认 LR_REAR。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            print(
                f"[TaskService.run_xml] cwd={os.getcwd()!r}, config_path={self.config_path!r}, "
                f"base_dir={self.base_dir!r}, domain={domain!r}"
            )
            # 传递 base_dir 和 config_path，保持与 CAN 生成使用同一份配置
            xml_gen.main(
                config_path=self.config_path,
                base_dir=self.base_dir,
                domain=domain,
            )
            return TaskResult(success=True, message=f"{domain} XML 生成完成")
        except Exception as e:
            tb = traceback.format_exc()
            msg = str(e)
            # 中央域未配置 XML 输入 Excel 时也按“跳过”处理
            if domain == "CENTRAL" and "未配置 Xml_Input_Excel 或 xml_input_excel" in msg:
                print(f"[TaskService.run_xml] 中央域未配置 Xml_Input_Excel，按要求跳过 XML 生成: {e}")
                return TaskResult(
                    success=True,
                    message="CENTRAL XML 未生成（未配置 Xml_Input_Excel，已按要求跳过）",
                    detail=tb,
                )
            print(f"[TaskService.run_xml] XML 生成报错详情:\n{tb}")
            return TaskResult(success=False, message=f"{domain} XML 生成失败: {e}", detail=tb)

    def run_cin(self) -> TaskResult:
        """运行 CIN 生成任务：切换工作目录后调用 generate_cin_from_excel.main。
        参数：无。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            cin_gen.main()
            return TaskResult(success=True, message="CIN 生成完成")
        except Exception as e:
            tb = traceback.format_exc()
            return TaskResult(success=False, message=f"CIN 生成失败: {e}", detail=tb)

    def run_did_info(self) -> TaskResult:
        """运行 DIDInfo 生成任务：切换工作目录后调用 generate_didinfo_from_excel.main。
        参数：无。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            didinfo_gen.main()
            return TaskResult(success=True, message="DIDInfo 生成完成")
        except Exception as e:
            tb = traceback.format_exc()
            msg = str(e)
            # 未配置 ResetDid_Value 配置表时，按“静默跳过”处理，不视为失败，只返回提示信息
            if "未配置 ResetDid_Value 配置表" in msg:
                print(f"DIDInfo 执行跳过（未配置 ResetDid_Value 配置表）: {e}")
                return TaskResult(
                    success=True,
                    message="DIDInfo 未生成（未配置 ResetDid_Value 配置表，已按要求跳过）",
                    detail=tb,
                )
            return TaskResult(success=False, message=f"DIDInfo 生成失败: {e}", detail=tb)

    def run_did_config(self) -> TaskResult:
        """运行 DIDConfig 生成任务：切换工作目录后调用 generate_did_config.main。
        参数：无。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            didconfig_gen.main()
            return TaskResult(success=True, message="DIDConfig 生成完成")
        except Exception as e:
            tb = traceback.format_exc()
            return TaskResult(success=False, message=f"DIDConfig 生成失败: {e}", detail=tb)

    def run_uart(self) -> TaskResult:
        """运行 UART 生成任务：切换工作目录后调用 generate_uart_from_config.main。
        参数：无。
        返回：TaskResult（success、message、detail）。
        """
        try:
            os.chdir(self.base_dir)
            uart_gen.main()
            return TaskResult(success=True, message="UART 生成完成")
        except Exception as e:
            tb = traceback.format_exc()
            return TaskResult(success=False, message=f"UART 生成失败: {e}", detail=tb)

