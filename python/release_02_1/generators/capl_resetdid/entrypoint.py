#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ResetDid_Value 生成入口模块。

根据 DID Excel 矩阵与界面配置的 ResetDid_Value 表生成输出文件，
供 TaskService 与命令行调用。具体实现委托同包下 ``ResetDidGeneratorService``.
"""

from __future__ import annotations

from .service import ResetDidGeneratorService

class ResetDidEntrypointWorkflowUtility:
    """ResetDid 入口编排统一工具类。"""

    @classmethod
    def run_generation(cls, domain: str | None = None) -> None:
        """ResetDid 生成主编排，委托 Service 完成读配置、初始化日志、解析 Excel、写产物、清理。

        参数：
            domain：业务域；为 ``DTC`` 时仅从 ``[DTC]`` 读取；未传则视为 ``LR_REAR``，
                且仅从 ``[LR_REAR]`` 读取（不再跨节读 ``[PATHS]``）。

        返回：
            None：生成结果通过日志与产物落盘体现。
        """
        service = ResetDidGeneratorService()
        service.run_pipeline(domain=domain)


def run_generation(domain: str | None = None) -> None:
    """兼容入口：转发到 ResetDidEntrypointWorkflowUtility.run_generation。"""
    ResetDidEntrypointWorkflowUtility.run_generation(domain=domain)


if __name__ == "__main__":
    ResetDidEntrypointWorkflowUtility.run_generation()
