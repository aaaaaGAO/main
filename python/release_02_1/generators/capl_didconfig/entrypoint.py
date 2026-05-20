#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDConfig 生成入口模块。

根据 DID 配置 Excel 生成 DIDConfig.txt，供 TaskService 与命令行调用。
具体实现委托同包下 service.DIDConfigGeneratorService。
"""

from __future__ import annotations

from typing import Any

from .service import DIDConfigGeneratorService


def run_generation_workflow(domain: str | None = None):
    """DIDConfig 生成主编排，委托 Service 完成读配置、初始化日志、解析 Excel、写 DIDConfig、清理。

    功能：创建 DIDConfigGeneratorService 并执行 run_pipeline，内部完成所有步骤。

    形参：domain — 为 ``DTC`` 时从 ``[DTC]`` 读取路径；未传则读 ``[LR_REAR]``。

    返回：Service 内部可能返回输出路径等；本入口不向外返回该值。
    """
    service = DIDConfigGeneratorService()
    return service.run_pipeline(domain=domain)


class DIDConfigEntrypointWorkflowUtility:
    """DIDConfig 入口编排统一工具类。"""

    @staticmethod
    def run_generation_workflow(*args: Any, **kwargs: Any) -> Any:
        return run_generation_workflow(*args, **kwargs)

    @classmethod
    def run_generation(cls, domain: str | None = None) -> None:
        """DIDConfig 生成主入口，供 TaskService 与命令行调用。"""
        cls.run_generation_workflow(domain=domain)


def run_generation(domain: str | None = None):
    """兼容入口：转发到 DIDConfigEntrypointWorkflowUtility.run_generation。"""
    DIDConfigEntrypointWorkflowUtility.run_generation(domain=domain)


if __name__ == "__main__":
    DIDConfigEntrypointWorkflowUtility.run_generation()
