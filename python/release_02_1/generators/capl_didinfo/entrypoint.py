#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDInfo 生成入口模块。

根据 DID 信息 Excel 与 ResetDid_Value 配置表生成 DIDInfo.txt，
供 TaskService 与命令行调用。具体实现委托同包下 service.DIDInfoGeneratorService。
"""

from __future__ import annotations

from .service import DIDInfoGeneratorService


def execute_workflow():
    """DIDInfo 生成主编排，委托 Service 完成读配置、初始化日志、解析 Excel、写 DIDInfo、清理。

    功能：创建 DIDInfoGeneratorService 并执行 run_legacy_pipeline，内部完成所有步骤。

    形参：无（配置与路径均从 Configuration.txt 及当前工作目录解析）。

    返回：Service 内部可能返回输出路径等；本入口不向外返回该值。
    """
    service = DIDInfoGeneratorService()
    return service.run_legacy_pipeline()


def main() -> None:
    """DIDInfo 生成主入口，供 TaskService 与命令行调用。

    功能：执行 execute_workflow，完成从配置到 DIDInfo.txt 的整条流水线。

    形参：无。

    返回：无。
    """
    execute_workflow()


if __name__ == "__main__":
    main()
