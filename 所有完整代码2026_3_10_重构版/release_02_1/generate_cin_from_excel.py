#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAPL CIN 自动化生成工具

本脚本为执行入口，将「读配置 → 映射加载 → 读 Clib Excel → 步骤翻译 → 写 .cin」串联成完整流水线。
编排与实现分离：具体实现位于 generators/capl_cin/（runtime_io、runtime、service）。

步骤说明：
  ① 读配置 — 从 Configuration.txt 读 Clib 输入 Excel、映射表路径、输出目录与文件名
  ② 信号映射 — 加载 io_mapping 与 Configuration 枚举上下文，供步骤参数替换与枚举翻译
  ③ 关键字加载 — 加载关键字与 CAPL 函数映射表（在 load_mapping_context 之后由 Service 内部使用）
  ④ 读 Clib Excel — 按 Name/Step 列读取，按 Name 聚合为 (Name, 步骤行列表)
  ⑤ 解析与渲染 — 用映射表 + io_mapping + config_enum 将步骤行转为 CAPL 代码
  ⑥ 写 .cin 与日志 — 输出 .cin 文件并写日志
"""

from __future__ import annotations

import os
import sys

from core.run_context import tee_stdout_stderr, restore_stdout_stderr, clear_run_logger
from generators.capl_cin.runtime import CINEntrypointSupport
from generators.capl_cin.service import CINGeneratorService
from generators.capl_cin.runtime_io import (
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

# ============================================================
# 【核心编排逻辑】 步骤 ① 至 ⑥
# ============================================================


def execute_workflow():
    """将 CIN 生成的各原子步骤串联为完整流水线并执行。

    功能：重置状态 → 解析 base_dir → 初始化日志并劫持 stdout/stderr → 读配置得到 runtime 字典 →
    加载 io_mapping 与 config_enum 上下文 → 调用 CINGeneratorService.run_legacy_pipeline 完成读 Clib、翻译、写 .cin。

    参数：无（配置与路径均从 Configuration.txt 及当前工作目录解析）。

    返回：无返回值。
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

        # ① 读配置：得到 input_excel_path、input_sheet、output_dir、output_cin_filename、映射表路径等
        runtime = CINEntrypointSupport.load_runtime_config(base_dir)
        sheet_title = CINEntrypointSupport.detect_sheet_title(
            runtime["input_excel_path"], runtime["input_sheet"]
        )
        if logger:
            logger.log(
                PROGRESS_LEVEL,
                f"处理Excel={os.path.basename(runtime['input_excel_path'])} sheet名={sheet_title}",
            )

        # ② & ③ 加载映射上下文：io_ctx 用于步骤里 J_ 开头的 Name→Path 与 Values 枚举；enum_ctx 用于 Set_Config 的枚举翻译
        io_ctx, enum_ctx = load_mapping_context(
            runtime["cfg"], base_dir, runtime["config_path"]
        )
        runtime["io_mapping_ctx"] = io_ctx
        runtime["config_enum_ctx"] = enum_ctx

        # ④、⑤、⑥ 执行 CIN 生成：读 Clib Name/Step → 按关键字与映射翻译每行 → 拼装 .cin 内容 → 写入输出目录
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


# ============================================================
# 【程序入口】
# ============================================================


def main():
    """CIN 生成主入口，无参数，直接执行 execute_workflow。

    功能：供命令行与 TaskService 调用，执行完整的 CIN 生成流水线。

    参数：无。

    返回：无返回值。
    """
    execute_workflow()


# ============================================================
# 【兼容性 API】 供其他模块调用
# ============================================================


def read_clib_steps_from_excel_for_cin(excel_path, clib_sheet=None):
    """兼容性转发：从 Clib Excel 读取 Name/Step 并按 Name 聚合，委托 runtime_io.read_clib_steps。

    功能：与旧版脚本保持相同调用方式，返回 (sheet_title, [(name, step_items), ...])。

    参数：
        excel_path — Clib Excel 文件路径。
        clib_sheet — 指定 Sheet 名；None 时由内部自动选择。

    返回：(sheet_title, 按 Name 聚合的步骤列表)。
    """
    return read_clib_steps(excel_path, clib_sheet=clib_sheet)


def load_unified_keyword_specs(excel_path, sheet_names):
    """兼容性：读取关键字-CAPL 映射表，告警通过 print 输出到 stderr。

    功能：加载映射表 Excel 的指定 Sheet，返回 full_key -> KeywordSpec 字典。

    参数：excel_path — 映射表 xlsx 路径；sheet_names — Sheet 名列表。

    返回：关键字规格字典。
    """
    return load_keyword_specs(
        excel_path,
        sheet_names,
        warn=lambda msg: print(f"[cin] 警告: {msg}", file=sys.stderr),
    )


if __name__ == "__main__":
    main()
