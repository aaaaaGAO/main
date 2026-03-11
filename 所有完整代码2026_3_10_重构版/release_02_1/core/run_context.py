#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成器运行上下文（供 CAN/CIN/XML/DIDInfo/DIDConfig/UART 复用）

- clear_run_logger() : 关闭并清空 logger 的 handlers，使下次运行能重新 setup_logging 并写入新的 log_时间戳 目录
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from utils.logger import TeeToLogger


def clear_run_logger(logger: Optional[logging.Logger]) -> None:
    """关闭并清除 logger 的所有 handlers，便于下次运行重新 setup 并写入新日志目录。
    参数：logger — 本次运行使用的 Logger 实例，None 时无操作。
    返回：无返回值。
    """
    if logger is None:
        return
    for handler in logger.handlers[:]:
        try:
            handler.close()
        except Exception:
            pass
        logger.removeHandler(handler)


def restore_stdout_stderr(
    old_stdout,
    old_stderr,
) -> None:
    """恢复 sys.stdout / sys.stderr 到重定向前的状态（与 tee_stdout_stderr 配对使用）。
    参数：old_stdout, old_stderr — 重定向前保存的原始流。
    返回：无返回值。
    """
    if old_stdout is not None:
        sys.stdout = old_stdout
    if old_stderr is not None:
        sys.stderr = old_stderr


def tee_stdout_stderr(
    logger: logging.Logger,
    *,
    level_stdout: int = logging.INFO,
    level_stderr: int = logging.ERROR,
    error_prefixes: tuple[str, ...] = ("错误", "[错误]", "[error]"),
    warning_prefixes: tuple[str, ...] = ("警告", "[警告]", "[warn]"),
    skip_prefixes: tuple[str, ...] = (),
) -> tuple:
    """将 stdout/stderr 重定向到 TeeToLogger，使 print 与子模块输出写入 logger。
    参数：logger — 目标 Logger；level_stdout / level_stderr — 输出等级；error_prefixes / warning_prefixes / skip_prefixes — Tee 过滤前缀。
    返回：(old_stdout, old_stderr)，供 finally 中 restore_stdout_stderr 恢复。
    """
    old_stdout, old_stderr = sys.stdout, sys.stderr
    if sys.__stdout__ is not None and sys.__stderr__ is not None:
        sys.stdout = TeeToLogger(
            logger,
            level_stdout,
            sys.__stdout__,
            error_prefixes=error_prefixes,
            warning_prefixes=warning_prefixes,
            skip_prefixes=skip_prefixes,
        )
        sys.stderr = TeeToLogger(
            logger,
            level_stderr,
            sys.__stderr__,
            error_prefixes=error_prefixes,
            warning_prefixes=warning_prefixes,
            skip_prefixes=skip_prefixes,
        )
    return (old_stdout, old_stderr)
