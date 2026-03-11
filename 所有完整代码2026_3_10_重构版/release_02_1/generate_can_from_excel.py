#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAPL CAN 自动化生成工具

本脚本为执行入口，将「读配置 → 映射加载 → 校验 → 读表翻译 → 写 .can」串联成完整流水线。
编排与实现分离：具体实现位于 generators/capl_can/（runtime_io、service、translator 等）。

步骤说明：
  ① 读配置 — 解析 Configuration.txt，得到输入 Excel、输出目录、筛选条件等（GeneratorConfig）
  ② 初始化日志 — 创建 generate_can_from_excel.log，并将 stdout/stderr 劫持到该 logger
  ③ 加载映射上下文 — 加载 IO 信号名→Path、Configuration 枚举表，供步骤参数替换与枚举翻译
  ④ 环境校验 — 从 CIN Excel 加载 Clib 名称集合，供步骤里 Clib 关键字的合法性校验
  ⑤⑥⑦ 核心生成 — Service 内部：读 Excel → 等级/平台/车型筛选 → 步骤关键字/IO/枚举翻译 → 写单用例 .can + Master.can → 输出汇总日志
"""

from __future__ import annotations

import argparse

from core.run_context import tee_stdout_stderr, restore_stdout_stderr
from generators.capl_can.runtime import CANEntrypointSupport
from generators.capl_can.service import CANGeneratorService
from generators.capl_can.runtime_io import (
    CANRuntimeContext,
    reset_runtime_state,
    set_can_runtime_context,
    setup_generator_logger,
    load_mapping_context,
    load_clib_context,
    legacy_read_cases,
)

# ============================================================
# 【核心编排逻辑】 步骤 ① 至 ⑦
# ============================================================


def execute_workflow(config_path=None, base_dir=None, domain="LR_REAR"):
    """将 CAN 生成的各原子步骤串联为完整流水线并执行。

    功能：按顺序执行「重置状态 → 读配置 → 初始化日志并劫持标准输出 → 加载映射与 Clib 校验 → 调用 Service 完成读表、翻译、写 .can、汇总」。

    参数：
        config_path — 配置文件路径；None 时在 base_dir 下查找 Configuration.txt。
        base_dir — 工程根目录；None 时由 resolve_base_dir 自动解析（打包为 exe 目录，开发为脚本所在目录）。
        domain — 业务域，如 LR_REAR / CENTRAL / DTC，用于读取对应域的配置节与映射。

    返回：无返回值。结果通过日志文件与生成的 .can 文件体现。
    """
    # 重置全局运行时状态，避免多次执行或 Web 二次点击时沿用上一次的 io_ctx / enum_ctx / clib 集合
    reset_runtime_state()
    # 解析真实工程根目录（打包环境为 exe 所在目录，开发环境为传入的 base_dir 或脚本所在目录）
    resolved_base_dir = CANEntrypointSupport.resolve_base_dir(base_dir)

    # ① 读配置：得到 GeneratorConfig（含 raw_config、config_path、base_dir 等），供后续步骤读取输入输出路径与筛选条件
    gconfig = CANEntrypointSupport.load_generator_config(resolved_base_dir, config_path)

    # 初始化日志管理器（写入 log/parse/generate_can_from_excel.log）并劫持 stdout/stderr，使 print 与子模块输出统一写入该日志
    log_mgr = setup_generator_logger(resolved_base_dir)
    logger = log_mgr.setup()
    old_stdout, old_stderr = tee_stdout_stderr(logger)

    try:
        print(f">>> 开始执行 [{domain}] 域生成任务...")

        # ② & ③ 加载映射上下文：从配置的 [IOMAPPING] / [CONFIG_ENUM] 读 Excel，构建 Name→Path、Name→Values 枚举；结果 io_ctx、enum_ctx 传入 Service 并注入 CANRuntimeContext 供兼容入口 legacy_read_cases 使用
        io_ctx, enum_ctx = load_mapping_context(gconfig, resolved_base_dir, domain=domain)
        # ④ 环境校验：从 CIN Excel 读取 Clib 名称集合，供步骤解析时校验 Clib 关键字
        clib_names_set = load_clib_context(gconfig, resolved_base_dir, domain=domain)
        can_ctx = CANRuntimeContext(
            io_mapping_ctx=io_ctx,
            config_enum_ctx=enum_ctx,
            clib_names_set=clib_names_set,
        )
        set_can_runtime_context(can_ctx)

        # ⑤、⑥、⑦ 核心 Service 调度：读用例 Excel → 过滤 → 步骤翻译（关键字 + io_mapping + config_enum）→ 写每个用例 .can + Master.can → 写 per-sheet 小日志与汇总
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


# ============================================================
# 【程序入口】
# ============================================================


def main(config_path=None, base_dir=None, domain="LR_REAR"):
    """命令行与程序化调用的统一入口，解析目录与配置后执行 CAN 生成流水线。

    功能：接收可选配置路径与工程根目录，调用 execute_workflow 完成整条流水线。

    参数：
        config_path — 配置文件路径；None 时在 base_dir 下查找 Configuration.txt。
        base_dir — 工程根目录；None 时自动解析。
        domain — 业务域，默认 LR_REAR。

    返回：无返回值。
    """
    execute_workflow(config_path=config_path, base_dir=base_dir, domain=domain)


# ============================================================
# 【兼容性 API】 供其他模块（如 Web、一键生成）调用
# ============================================================


def read_cases_from_excel_for_can(*args, **kwargs):
    """兼容性转发：将「从 Excel 读取 CAN 用例并做筛选与步骤翻译」委托给 runtime_io.legacy_read_cases。

    功能：与旧版脚本保持相同调用方式，内部执行 legacy_read_cases（读 Excel → 等级/平台/车型与 Sheet 筛选 → 步骤翻译）。

    参数：与 generators.capl_can.runtime_io.legacy_read_cases 一致（excel_path、keyword_specs、allowed_levels 等）。

    返回：(sheet_cases 字典, stats 统计字典)。
    """
    return legacy_read_cases(*args, **kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CAN 生成工具入口：从 Excel 用例表生成 CAPL .can 文件。")
    parser.add_argument("--config", help="配置文件路径（默认在工程根目录下查找 Configuration.txt）")
    parser.add_argument("--domain", default="LR_REAR", help="业务域：LR_REAR / CENTRAL / DTC")
    args = parser.parse_args()
    main(config_path=args.config, domain=args.domain)
