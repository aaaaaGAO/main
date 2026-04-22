#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAPL CIN 生成入口模块。

将「读配置 → 映射加载 → 读 Clib Excel → 步骤翻译 → 写 .cin」串联成完整流水线，
供 TaskService 与命令行调用。具体实现位于同包下 runtime、runtime_io、service。
"""

from __future__ import annotations

import importlib
import importlib.util
import os

from core.run_context import tee_stdout_stderr, restore_stdout_stderr, clear_run_logger
from services.config_constants import (
    CIN_RUNTIME_KEY_CFG,
    CIN_RUNTIME_KEY_CONFIG_ENUM_CTX,
    CIN_RUNTIME_KEY_CONFIG_PATH,
    CIN_RUNTIME_KEY_INPUT_EXCEL_PATH,
    CIN_RUNTIME_KEY_INPUT_SHEET,
    CIN_RUNTIME_KEY_IO_MAPPING_CTX,
    DEFAULT_DOMAIN_LR_REAR,
)
from .runtime import CINEntrypointSupport
from .service import CINGeneratorService
from .runtime_io import (
    reset_runtime_state,
    setup_generator_logger,
    load_mapping_context,
)

PROGRESS_LEVEL = 15
if importlib.util.find_spec("utils.logger") is not None:
    utils_logger_module = importlib.import_module("utils.logger")
    PROGRESS_LEVEL = getattr(utils_logger_module, "PROGRESS_LEVEL", 15)


def run_generation_workflow(domain: str = DEFAULT_DOMAIN_LR_REAR):
    """将 CIN 生成的各原子步骤串联为完整流水线并执行。

    功能：重置状态 → 解析 base_dir → 初始化日志并劫持 stdout/stderr
    → 读配置得到 runtime 字典 → 按 domain 加载 io_mapping 与 config_enum
    → 调用 CINGeneratorService.run_pipeline 完成读 Clib、翻译、写 .cin。

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
        runtime = CINEntrypointSupport.load_runtime_config(base_dir, domain=domain)
        sheet_title = CINEntrypointSupport.detect_sheet_title(
            runtime[CIN_RUNTIME_KEY_INPUT_EXCEL_PATH], runtime[CIN_RUNTIME_KEY_INPUT_SHEET]
        )
        if logger:
            logger.log(
                PROGRESS_LEVEL,
                f"处理Excel={os.path.basename(runtime[CIN_RUNTIME_KEY_INPUT_EXCEL_PATH])} sheet名={sheet_title}",
            )
        io_ctx, enum_ctx = load_mapping_context(
            runtime[CIN_RUNTIME_KEY_CFG], base_dir, runtime[CIN_RUNTIME_KEY_CONFIG_PATH], domain=domain
        )
        runtime[CIN_RUNTIME_KEY_IO_MAPPING_CTX] = io_ctx
        runtime[CIN_RUNTIME_KEY_CONFIG_ENUM_CTX] = enum_ctx
        service = CINGeneratorService(logger=logger)
        out_path = service.run_pipeline(runtime)
        if not out_path:
            print("[cin] 未读取到任何有效的 Name/Step 记录，未生成文件。")
        else:
            print(f">>> 任务完成！已生成: {out_path}")
        if logger:
            clear_run_logger(logger)
    finally:
        restore_stdout_stderr(old_stdout, old_stderr)
        log_mgr.clear()


def run_generation(domain: str = DEFAULT_DOMAIN_LR_REAR):
    """CIN 生成主入口，供 TaskService 与命令行调用。

    功能：执行 run_generation_workflow，完成从配置读取到 .cin 写出的整条流水线。

    形参：domain — 业务域（LR_REAR / CENTRAL / DTC），默认 LR_REAR。
    返回：无。
    """
    run_generation_workflow(domain=domain)


class CINEntrypointWorkflowUtility:
    """CIN 入口编排统一工具类。"""

    run_generation_workflow = staticmethod(run_generation_workflow)
    run_generation = staticmethod(run_generation)


if __name__ == "__main__":
    run_generation()
