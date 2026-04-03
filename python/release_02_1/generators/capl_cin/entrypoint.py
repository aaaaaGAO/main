#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAPL CIN 生成入口模块。

将「读配置 → 映射加载 → 读 Clib Excel → 步骤翻译 → 写 .cin」串联成完整流水线，
供 TaskService 与命令行调用。具体实现位于同包下 runtime、runtime_io、service。
"""

from __future__ import annotations

import os
import sys

from core.run_context import tee_stdout_stderr, restore_stdout_stderr, clear_run_logger
from services.config_constants import DEFAULT_DOMAIN_LR_REAR
from .runtime import CINEntrypointSupport
from .service import CINGeneratorService
from .runtime_io import (
    reset_runtime_state,
    setup_generator_logger,
    load_mapping_context,
    read_clib_steps,
    load_keyword_specs,
)

try:
    from utils.logger import PROGRESS_LEVEL
except ImportError:
    PROGRESS_LEVEL = 15


def execute_workflow(domain: str = DEFAULT_DOMAIN_LR_REAR):
    """将 CIN 生成的各原子步骤串联为完整流水线并执行。

    功能：重置状态 → 解析 base_dir → 初始化日志并劫持 stdout/stderr
    → 读配置得到 runtime 字典 → 按 domain 加载 io_mapping 与 config_enum
    → 调用 CINGeneratorService.run_legacy_pipeline 完成读 Clib、翻译、写 .cin。

    形参：domain — 业务域（LR_REAR / CENTRAL / DTC），用于映射与日志级别，默认 LR_REAR。
    返回：无。
    """
    reset_runtime_state()
    base_dir = CINEntrypointSupport.resolve_base_dir()
    log_mgr = setup_generator_logger(base_dir)
    logger = log_mgr.setup()
    old_stdout, old_stderr = tee_stdout_stderr(
        logger,
        error_prefixes=("[cin][ERROR]", "[错误]", "[error]"),
        warning_prefixes=("[cin] 警告", "[警告]", "[warn]", "[dup]"),
    )

    try:
        print(">>> 开始执行 CIN 生成任务...", flush=True)
        runtime = CINEntrypointSupport.load_runtime_config(base_dir)
        sheet_title = CINEntrypointSupport.detect_sheet_title(
            runtime["input_excel_path"], runtime["input_sheet"]
        )
        if logger:
            logger.log(
                PROGRESS_LEVEL,
                f"处理Excel={os.path.basename(runtime['input_excel_path'])} sheet名={sheet_title}",
            )
        io_ctx, enum_ctx = load_mapping_context(
            runtime["cfg"], base_dir, runtime["config_path"], domain=domain
        )
        runtime["io_mapping_ctx"] = io_ctx
        runtime["config_enum_ctx"] = enum_ctx
        service = CINGeneratorService(logger=logger)
        out_path = service.run_legacy_pipeline(runtime)
        if not out_path:
            print("[cin] 未读取到任何有效的 Name/Step 记录，未生成文件。")
        else:
            print(f">>> 任务完成！已生成: {out_path}")
        if logger:
            clear_run_logger(logger)
    finally:
        restore_stdout_stderr(old_stdout, old_stderr)
        log_mgr.clear()


def main(domain: str = DEFAULT_DOMAIN_LR_REAR):
    """CIN 生成主入口，供 TaskService 与命令行调用。

    功能：执行 execute_workflow，完成从配置读取到 .cin 写出的整条流水线。

    形参：domain — 业务域（LR_REAR / CENTRAL / DTC），默认 LR_REAR。
    返回：无。
    """
    execute_workflow(domain=domain)


def read_clib_steps_from_excel_for_cin(excel_path, clib_sheet=None):
    """从 Clib Excel 读取 Name/Step 并按 Name 聚合的兼容性入口。

    功能：委托 runtime_io.read_clib_steps，与旧版调用方式一致。

    形参：
        excel_path：Clib Excel 文件路径。
        clib_sheet：指定 Sheet 名；None 时由内部自动选择。

    返回：(sheet_title, [(name, step_items), ...])，按 Name 聚合的步骤列表。
    """
    return read_clib_steps(excel_path, clib_sheet=clib_sheet)


def load_unified_keyword_specs(excel_path, sheet_names):
    """加载关键字到 CAPL 函数映射表的兼容性入口。

    功能：读取映射表 Excel 的指定 Sheet，返回 full_key -> KeywordSpec 字典；告警通过 stderr 输出。

    形参：
        excel_path：映射表 xlsx 路径。
        sheet_names：Sheet 名列表。

    返回：关键字规格字典。
    """
    return load_keyword_specs(
        excel_path,
        sheet_names,
        warn=lambda msg: print(f"[cin] 警告: {msg}", file=sys.stderr),
    )


if __name__ == "__main__":
    main()
