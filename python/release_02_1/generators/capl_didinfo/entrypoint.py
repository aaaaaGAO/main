#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDInfo 生成入口模块。

根据 DID 信息 Excel 与 ResetDid_Value 配置表生成 DIDInfo.txt，
供 TaskService 与命令行调用。具体实现委托同包下 service.DIDInfoGeneratorService。
"""

from __future__ import annotations

from typing import Any

from .service import DIDInfoGeneratorService


def run_generation_workflow(domain: str | None = None):
    """DIDInfo 生成主编排，委托 Service 完成读配置、初始化日志、解析 Excel、写 DIDInfo、清理。

    功能：创建 DIDInfoGeneratorService 并执行 run_pipeline，内部完成所有步骤。

    形参：domain — 业务域；为 ``DTC`` 时仅从 ``[DTC]`` 读取；未传则视为 ``LR_REAR``，且仅从 ``[LR_REAR]`` 读取（不再跨节读 ``[PATHS]``）。

    返回：Service 内部可能返回输出路径等；本入口不向外返回该值。
    """
    service = DIDInfoGeneratorService()
    return service.run_pipeline(domain=domain)


def run_generation(domain: str | None = None) -> None:
    """DIDInfo 生成主入口，供 TaskService 与命令行调用。

    功能：执行 run_generation_workflow，完成从配置到 DIDInfo.txt 的整条流水线。

    形参：domain — 同 run_generation_workflow。

    返回：无。
    """
    run_generation_workflow(domain=domain)


class DIDInfoEntrypointWorkflowUtility:
    """DIDInfo 入口编排统一工具类。"""

    @staticmethod
    def run_generation_workflow(*args: Any, **kwargs: Any) -> Any:
        return run_generation_workflow(*args, **kwargs)

    @staticmethod
    def run_generation(*args: Any, **kwargs: Any) -> Any:
        return run_generation(*args, **kwargs)


if __name__ == "__main__":
    run_generation()
