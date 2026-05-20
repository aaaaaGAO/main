#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDConfig 生成入口模块。

根据 DID 配置 Excel 生成 DIDConfig.txt，供 TaskService 与命令行调用。
具体实现委托同包下 service.DIDConfigGeneratorService。
"""

from __future__ import annotations

from .service import DIDConfigGeneratorService

class DIDConfigEntrypointWorkflowUtility:
    """DIDConfig 入口编排统一工具类。"""

    @classmethod
    def run_generation(cls, domain: str | None = None) -> None:
        """DIDConfig 生成主编排，委托 Service 完成读配置、初始化日志、解析 Excel、写 DIDConfig、清理。

        参数：
            domain：为 ``DTC`` 时从 ``[DTC]`` 读取路径；未传则读 ``[LR_REAR]``。

        返回：
            None：生成结果通过日志与产物落盘体现。
        """
        service = DIDConfigGeneratorService()
        service.run_pipeline(domain=domain)


def run_generation(domain: str | None = None):
    """兼容入口：转发到 DIDConfigEntrypointWorkflowUtility.run_generation。"""
    DIDConfigEntrypointWorkflowUtility.run_generation(domain=domain)


if __name__ == "__main__":
    DIDConfigEntrypointWorkflowUtility.run_generation()
