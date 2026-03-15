#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDConfig 生成入口模块。

根据 DID 配置 Excel 生成 DIDConfig.txt，供 TaskService 与命令行调用。
具体实现委托同包下 service.DIDConfigGeneratorService。
"""

from __future__ import annotations

from .service import DIDConfigGeneratorService


def execute_workflow():
    """DIDConfig 生成主编排，委托 Service 完成读配置、初始化日志、解析 Excel、写 DIDConfig、清理。

    功能：创建 DIDConfigGeneratorService 并执行 run_legacy_pipeline，内部完成所有步骤。

    形参：无（配置与路径均从 Configuration.txt 及当前工作目录解析）。

    返回：Service 内部可能返回输出路径等；本入口不向外返回该值。
    """
    service = DIDConfigGeneratorService()
    return service.run_legacy_pipeline()


def main():
    """DIDConfig 生成主入口，供 TaskService 与命令行调用。

    功能：执行 execute_workflow，完成「读配置 → 初始化日志 → 解析 Excel → 写 DIDConfig.txt」整条流水线。

    形参：无。

    返回：无。
    """
    execute_workflow()


if __name__ == "__main__":
    main()
