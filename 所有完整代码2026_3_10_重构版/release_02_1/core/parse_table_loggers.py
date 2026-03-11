#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析表格日志（run_dirs.parse_dir）专用 logger 工具。

目标：
- Clib_Matrix.log：Clib 配置表（关键字集）解析/表头错误
- TestCases.log：测试用例表（CAN/XML）导入时表头必填列错误；可选列（等级/平台/车型/用例类型）缺失时的 warning（默认该维度均符合要求）
- Uart_Matrix.log：UART 通信矩阵表（IVIToMCU/MCUToIVI）表头必填列错误
- caseid_clean_dup.log：用例ID清洗/重复（带空格、非法字符、重复）
"""

from __future__ import annotations

import logging
import logging.handlers
import os

from core.caseid_log_dedup import DedupOnceFilter
from core.log_run_context import ensure_run_log_dirs
from utils.logger import get_log_level_from_config


def _get_parse_file_logger(base_dir: str, *, filename: str, logger_name: str) -> logging.Logger:
    """获取或创建「解析表格日志」目录下的文件 Logger，同进程复用同一路径的 handler。
    参数: base_dir — 项目根；filename — 日志文件名；logger_name — Logger 名称。
    返回: 配置好的 Logger，写入 base_dir/log/.../解析表格日志/filename。
    """
    run_dirs = ensure_run_log_dirs(base_dir)
    parse_dir = run_dirs.parse_dir
    os.makedirs(parse_dir, exist_ok=True)

    log_path = os.path.join(parse_dir, filename)
    desired_path = os.path.abspath(log_path)

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # 同进程多次运行：若 logger 指向旧路径，则重建 handler
    has_desired = any(
        isinstance(h, logging.FileHandler) and os.path.abspath(getattr(h, "baseFilename", "")) == desired_path
        for h in logger.handlers
    )
    if logger.handlers and not has_desired:
        for h in logger.handlers[:]:
            try:
                h.close()
            except Exception:
                pass
            logger.removeHandler(h)

    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=20,
            encoding="utf-8",
        )
        # 与「日志生成选择」一致：只写入 >= log_level_min 的级别（info/warning/error）
        fh.setLevel(get_log_level_from_config(base_dir, section=None))
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def get_clib_matrix_logger(base_dir: str) -> logging.Logger:
    """获取 Clib 矩阵表解析日志 Logger。参数: base_dir — 项目根。返回: Logger，写入 Clib_Matrix.log。"""
    return _get_parse_file_logger(base_dir, filename="Clib_Matrix.log", logger_name="parse.Clib_Matrix")


def get_testcases_parse_logger(base_dir: str) -> logging.Logger:
    """获取测试用例表解析日志 Logger。参数: base_dir — 项目根。返回: Logger，写入 TestCases.log。"""
    return _get_parse_file_logger(base_dir, filename="TestCases.log", logger_name="parse.TestCases")


def get_uart_matrix_logger(base_dir: str) -> logging.Logger:
    """获取 UART 通信矩阵表解析日志 Logger（IVIToMCU/MCUToIVI）。参数: base_dir — 项目根。返回: Logger。"""
    return _get_parse_file_logger(base_dir, filename="Uart_Matrix.log", logger_name="parse.Uart_Matrix")


def get_caseid_clean_dup_logger(base_dir: str) -> logging.Logger:
    """获取用例 ID 清洗/重复专用 Logger（caseid_clean_dup.log），带 DedupOnceFilter 同进程去重。
    参数: base_dir — 项目根。返回: Logger。
    """
    logger = _get_parse_file_logger(base_dir, filename="caseid_clean_dup.log", logger_name="parse.caseid_clean_dup")
    # 为 caseid 专用 logger 添加同进程去重
    for h in logger.handlers:
        if not any(isinstance(f, DedupOnceFilter) for f in getattr(h, "filters", [])):
            h.addFilter(DedupOnceFilter())
    return logger
