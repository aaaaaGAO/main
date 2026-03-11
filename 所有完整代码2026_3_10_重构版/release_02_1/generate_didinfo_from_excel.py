#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAPL DIDInfo 自动化生成工具

本脚本为执行入口，将 DIDInfo 生成委托给 generators.capl_didinfo.service 执行。

步骤说明（在 Service.run_legacy_pipeline 内部完成）：
  ① 读配置 — DID 输入 Excel、输出路径、车型列、输入列表（从 Configuration.txt）
  ② 初始化日志 — 双日志与 stdout/stderr Tee
  ③ 解析 Excel — 定位表头（Configure DID, Length, Byte, Bit）与车型列，逐行解析
  ④ 按 Sheet/车型生成 DIDInfo 片段并写入输出文件
  ⑤ 清理 logger

编排与实现分离：具体实现位于 generators/capl_didinfo/（runtime_io、runtime、service）。
"""

from __future__ import annotations

from generators.capl_didinfo.service import DIDInfoGeneratorService


def execute_workflow():
    """DIDInfo 生成主编排，委托 Service 完成 ① 读配置 → ② 初始化日志 → ③ 解析 Excel → ④ 写 DIDInfo → ⑤ 清理。

    功能：创建 DIDInfoGeneratorService 并执行 run_legacy_pipeline，内部完成所有步骤。

    参数：无（配置与路径均从 Configuration.txt 及当前工作目录解析）。

    返回：无返回值（Service 内部可能返回路径等，本入口不向外返回）。
    """
    service = DIDInfoGeneratorService()
    return service.run_legacy_pipeline()


def main() -> None:
    """DIDInfo 生成主入口，供命令行与 TaskService 调用。

    功能：执行 execute_workflow，完成 DIDInfo 从 Excel 到输出文件的整条流水线。

    参数：无。

    返回：无返回值。
    """
    execute_workflow()


if __name__ == "__main__":
    main()
