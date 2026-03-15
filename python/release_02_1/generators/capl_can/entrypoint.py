#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAPL CAN 生成入口模块。

将「读配置 → 映射加载 → Clib 校验 → 读表翻译 → 写 .can」串联成完整流水线，
供 TaskService 与命令行调用。具体实现位于同包下 runtime、runtime_io、service。
"""

from __future__ import annotations

import argparse

from core.run_context import tee_stdout_stderr, restore_stdout_stderr
from .runtime import CANEntrypointSupport
from .service import CANGeneratorService
from .runtime_io import (
    CANRuntimeContext,
    reset_runtime_state,
    set_can_runtime_context,
    setup_generator_logger,
    load_mapping_context,
    load_clib_context,
    legacy_read_cases,
)


def execute_workflow(config_path=None, base_dir=None, domain="LR_REAR"):
    """将 CAN 生成的各原子步骤串联为完整流水线并执行。

    功能：重置运行时状态 → 解析工程根目录 → 读配置 → 初始化日志并劫持 stdout/stderr
    → 加载 IO 映射与 Config 枚举 → 加载 Clib 名称集合用于步骤校验
    → 调用 CANGeneratorService.run_legacy_pipeline 完成读表、翻译、写 .can 与 Master.can。

    形参：
        config_path：配置文件路径；None 时在 base_dir 下查找 config/Configuration.txt。
        base_dir：工程根目录；None 时由 resolve_base_dir 自动解析（打包为 exe 所在目录）。
        domain：业务域，如 "LR_REAR" / "CENTRAL" / "DTC"，用于读取对应域的配置节与映射。

    返回：无。结果通过日志文件与生成的 .can 文件体现。
    """
    reset_runtime_state()
    resolved_base_dir = CANEntrypointSupport.resolve_base_dir(base_dir)
    gconfig = CANEntrypointSupport.load_generator_config(resolved_base_dir, config_path)
    log_mgr = setup_generator_logger(resolved_base_dir)
    logger = log_mgr.setup()
    old_stdout, old_stderr = tee_stdout_stderr(logger)

    try:
        print(f">>> 开始执行 [{domain}] 域生成任务...")
        io_ctx, enum_ctx = load_mapping_context(gconfig, resolved_base_dir, domain=domain)
        clib_names_set = load_clib_context(gconfig, resolved_base_dir, domain=domain)
        can_ctx = CANRuntimeContext(
            io_mapping_ctx=io_ctx,
            config_enum_ctx=enum_ctx,
            clib_names_set=clib_names_set,
        )
        set_can_runtime_context(can_ctx)
        service = CANGeneratorService(base_dir=resolved_base_dir)
        service.run_legacy_pipeline(
            gconfig,
            base_dir=resolved_base_dir,
            domain=domain,
            run_dirs=log_mgr.run_dirs,
            io_mapping_ctx=io_ctx,
            config_enum_ctx=enum_ctx,
            main_log_path=log_mgr.primary_log_path,
        )
        print(f">>> 任务完成！日志已保存至: {log_mgr.primary_log_path}")
    finally:
        restore_stdout_stderr(old_stdout, old_stderr)
        log_mgr.clear()


def main(config_path=None, base_dir=None, domain="LR_REAR"):
    """CAN 生成统一入口，供 TaskService 与命令行调用。

    功能：接收可选配置路径、工程根目录与业务域，调用 execute_workflow 完成整条流水线。

    形参：
        config_path：配置文件路径；None 时在 base_dir/config 下使用 Configuration.txt。
        base_dir：工程根目录；None 时自动解析。
        domain：业务域，默认 "LR_REAR"。

    返回：无。
    """
    execute_workflow(config_path=config_path, base_dir=base_dir, domain=domain)


def read_cases_from_excel_for_can(*args, **kwargs):
    """从 Excel 读取 CAN 用例并做筛选与步骤翻译的兼容性入口。

    功能：委托 runtime_io.legacy_read_cases，与旧版调用方式一致（读 Excel → 等级/平台/车型与 Sheet 筛选 → 步骤翻译）。

    形参：与 runtime_io.legacy_read_cases 一致（如 excel_path、keyword_specs、allowed_levels 等），通过 *args/**kwargs 透传。

    返回：(sheet_cases 字典, stats 统计字典)。
    """
    return legacy_read_cases(*args, **kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CAN 生成工具：从 Excel 用例表生成 CAPL .can 文件。")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--domain", default="LR_REAR", help="业务域：LR_REAR / CENTRAL / DTC")
    args = parser.parse_args()
    main(config_path=args.config, domain=args.domain)
