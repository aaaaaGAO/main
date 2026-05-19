#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ResetDid_Value 生成入口模块。

根据 DID Excel 矩阵与界面配置的 ResetDid_Value 表生成输出文件，
供 TaskService 与命令行调用。具体实现委托同包下 ``ResetDidGeneratorService``.
"""

from __future__ import annotations

from .service import ResetDidGeneratorService


def run_generation_workflow(domain: str | None = None):
    """ResetDid 生成主编排，委托 Service 完成读配置、初始化日志、解析 Excel、写产物、清理。

    功能：创建 ``ResetDidGeneratorService`` 并执行 ``run_pipeline``，内部完成所有步骤。

    形参：domain — 业务域；为 ``DTC`` 时仅从 ``[DTC]`` 读取；未传则视为 ``LR_REAR``，
    且仅从 ``[LR_REAR]`` 读取（不再跨节读 ``[PATHS]``）。

    返回：Service 内部可能无副作用；本入口不向外返回输出路径。
    """
    service = ResetDidGeneratorService()
    return service.run_pipeline(domain=domain)


def run_generation(domain: str | None = None) -> None:
    """ResetDid 生成主入口，供 TaskService 与命令行调用。

    功能：执行 ``run_generation_workflow``，完成从配置到输出文件的整条流水线。

    形参：domain — 同 ``run_generation_workflow``。

    返回：无。
    """
    run_generation_workflow(domain=domain)


if __name__ == "__main__":
    run_generation()
