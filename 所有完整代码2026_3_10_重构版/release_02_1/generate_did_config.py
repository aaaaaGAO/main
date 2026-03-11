#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAPL DIDConfig 自动化生成工具

本脚本为执行入口，将 DIDConfig 生成委托给 generators.capl_didconfig.service 执行。

步骤说明（在 Service.run_legacy_pipeline 内部完成）：
  ① 读配置 — 从 [DID_CONFIG] 读 input_excel、output_filename、output_dir
  ② 初始化日志 — 双日志（解析表 + 生成）与 stdout/stderr Tee
  ③ 解析 Excel — 逐 Sheet 定位表头（Name/Byte/Bit）与行
  ④ 拼装 DIDConfig 文本并写入 output_dir
  ⑤ 清理 logger

编排与实现分离：具体实现位于 generators/capl_didconfig/（runtime_io、runtime、service）。
"""

from __future__ import annotations

from generators.capl_didconfig.service import DIDConfigGeneratorService


def execute_workflow():
    """DIDConfig 生成主编排，委托 Service 完成 ① 读配置 → ② 初始化日志 → ③ 解析 Excel → ④ 写 DIDConfig → ⑤ 清理。

    功能：创建 DIDConfigGeneratorService 并执行 run_legacy_pipeline，内部完成所有步骤。

    参数：无（配置与路径均从 Configuration.txt 及当前工作目录解析）。

    返回：无返回值（Service 内部可能返回路径等，本入口不向外返回）。
    """
    service = DIDConfigGeneratorService()
    return service.run_legacy_pipeline()


def main():
    """DIDConfig 生成主入口，供命令行与 TaskService 调用。

    功能：执行 execute_workflow，完成「读配置 → 初始化日志 → 解析 Excel → 写 DIDConfig.txt」整条流水线。

    参数：无。

    返回：无返回值。
    """
    execute_workflow()


if __name__ == "__main__":
    main()
