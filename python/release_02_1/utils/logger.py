#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志工具（供所有生成器复用）

提供：
- PROGRESS_LEVEL        : 进度日志等级（25），不受 log_level_min 限制
- ProgressOnlyFilter    : 仅允许 PROGRESS 消息
- ExcludeProgressFilter : 排除 PROGRESS 消息
- SubstringFilter       : 按子串 include/exclude 过滤
- ExcludeSubstringsFilter : 排除包含指定子串的消息
- ProgressFormatter     : PROGRESS 等级隐藏级别名；"解析 Excel 文件" 行去掉 INFO
- TeeToLogger           : 把 print 输出同步写入 logger（可配置前缀/启动触发）
- get_log_level_from_config() : 从当前主配置文件读取 log_level_min
- get_error_module()    : 根据错误文本判断所属模块
"""

from __future__ import annotations

import configparser
import logging
import os
import re
from typing import Callable, Optional, Sequence

from infra.filesystem import resolve_main_config_path
from services.config_constants import DEFAULT_DOMAIN_LR_REAR, OPTION_LOG_LEVEL_MIN
from core.error_module import ErrorModuleResolver
from core.log_run_context import get_run_domain

PROGRESS_LEVEL = 25
logging.addLevelName(PROGRESS_LEVEL, "PROGRESS")


# ── 过滤器 ──────────────────────────────────────────────────

class ProgressOnlyFilter(logging.Filter):
    """仅允许 PROGRESS_LEVEL 的日志通过。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == PROGRESS_LEVEL


class ExcludeProgressFilter(logging.Filter):
    """排除 PROGRESS_LEVEL 的日志。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno != PROGRESS_LEVEL


class SubstringFilter(logging.Filter):
    """
    通过"消息包含子串"来过滤日志。

    - include=True  : 仅保留包含任意 pattern 的记录
    - include=False : 排除包含任意 pattern 的记录
    """

    def __init__(self, patterns: Sequence[str], *, include: bool):
        super().__init__()
        self.patterns = tuple(patterns)
        self.include = include

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        hit = any(pattern_text in msg for pattern_text in self.patterns)
        return hit if self.include else (not hit)


class ExcludeSubstringsFilter(logging.Filter):
    """排除包含指定子串的日志行（同时过滤重复的时间戳解析行）。"""

    TIMESTAMP_PARSE_PATTERN = re.compile(
        r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s+解析 Excel 文件:"
    )

    def __init__(self, *substrings: str):
        super().__init__()
        self.substrings = tuple(substring for substring in substrings if substring)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        if any(substring in msg for substring in self.substrings):
            return False
        if self.TIMESTAMP_PARSE_PATTERN.match(msg):
            return False
        return True


# ── 格式化器 ────────────────────────────────────────────────

class ProgressFormatter(logging.Formatter):
    """
    友好显示日志：
    - PROGRESS 等级：只输出时间 + 消息（隐藏级别名）
    - 「解析 Excel 文件:」行：去掉级别前缀（不显示 INFO）
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        - PROGRESS_LEVEL：仅输出“时间 + 两个空格 + 消息”（不带级别名），便于进度类日志阅读。
        - 其他级别（INFO/ERROR 等）：使用标准格式，包含 LEVEL 标签。
        """
        msg = record.getMessage()
        if record.levelno == PROGRESS_LEVEL:
            # 形如：2026-03-03 13:24:52,856  解析 Excel 文件: ...
            ts = self.formatTime(record, self.datefmt)
            return f"{ts}  {msg}"
        return super().format(record)


# ── TeeToLogger ─────────────────────────────────────────────

FORMATTED_LOG_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s+"
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)"
)
TIMESTAMP_PARSE_EXCEL_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s+解析 Excel 文件:"
)


class TeeToLogger:
    """
    把 print 输出同时写到 logger（并保留控制台输出）。

    可配置参数：
    - error_prefixes   : 匹配这些前缀的消息用 ERROR 写入
    - warning_prefixes : 匹配这些前缀的消息用 WARNING 写入
    - skip_prefixes    : 匹配这些前缀的消息跳过不写日志
    - start_trigger    : 出现该字符串后才开始写入日志
    - msg_cleaner      : 对消息做清洗（返回清洗后的字符串）
    - use_reentry_guard: 启用递归锁防止 logger 内部 write 导致的死循环
    - strip_whitespace : 用 strip() 处理空行（True）或 rstrip('\\r')（False）
    """

    def __init__(
        self,
        logger: logging.Logger,
        level: int,
        original,
        *,
        error_prefixes: Sequence[str] = (),
        warning_prefixes: Sequence[str] = (),
        skip_prefixes: Sequence[str] = (),
        start_trigger: str | None = None,
        msg_cleaner: Callable[[str], str] | None = None,
        use_reentry_guard: bool = False,
        strip_whitespace: bool = True,
    ):
        self.logger = logger
        self.level = level
        self.original = original
        self.buffer_text = ""
        self.has_started_logging = start_trigger is None
        self.start_trigger_text = start_trigger
        self.error_prefixes = tuple(error_prefixes)
        self.warning_prefixes = tuple(warning_prefixes)
        self.skip_prefixes = tuple(skip_prefixes)
        self.message_cleaner = msg_cleaner
        self.use_reentry_guard = use_reentry_guard
        self.strip_whitespace = strip_whitespace
        self.is_logging_in_progress = False

    def write(self, text_chunk: str) -> int:
        if self.use_reentry_guard and self.is_logging_in_progress:
            try:
                if self.original:
                    self.original.write(text_chunk)
            except Exception:
                pass
            return len(text_chunk)

        try:
            if self.original:
                self.original.write(text_chunk)
        except Exception:
            pass

        self.buffer_text += text_chunk
        while "\n" in self.buffer_text:
            line, self.buffer_text = self.buffer_text.split("\n", 1)
            if self.strip_whitespace:
                msg = line.strip()
            else:
                msg = line.rstrip("\r")
            if not msg:
                continue

            if self.start_trigger_text and not self.has_started_logging:
                if self.start_trigger_text in msg:
                    self.has_started_logging = True
                else:
                    continue

            # 若消息本身已经是带时间戳的完整日志行（由 logging.Formatter 输出），
            # 则无需再通过 logger 写入一次，避免出现
            # "时间 ERROR 时间 消息" 这种重复叠加的情况。
            # 直接跳过，仅保留原 handler 已经写入的内容。
            if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s+", msg):
                continue

            if FORMATTED_LOG_PATTERN.match(msg):
                continue
            if TIMESTAMP_PARSE_EXCEL_PATTERN.match(msg):
                continue

            if any(msg.startswith(prefix) for prefix in self.skip_prefixes):
                continue

            clean_msg = self.message_cleaner(msg) if self.message_cleaner else msg
            if not clean_msg:
                continue

            try:
                if self.use_reentry_guard:
                    self.is_logging_in_progress = True

                if any(msg.startswith(prefix) for prefix in self.error_prefixes):
                    self.logger.error(clean_msg)
                elif any(msg.startswith(prefix) for prefix in self.warning_prefixes):
                    self.logger.warning(clean_msg)
                else:
                    self.logger.log(self.level, clean_msg)
            finally:
                if self.use_reentry_guard:
                    self.is_logging_in_progress = False

        return len(text_chunk)

    def flush(self) -> None:
        try:
            if self.original:
                self.original.flush()
        except Exception:
            pass


# ── 工具函数 ────────────────────────────────────────────────

def get_log_level_from_config(
    base_dir: str,
    section: str | None = DEFAULT_DOMAIN_LR_REAR,
) -> int:
    """从当前主配置文件的指定 section 读取 log_level_min 并转为 logging 级别。
    参数: base_dir — 工程根目录；section — 配置节名，None 时使用当前运行域（set_run_domain）。
    返回: logging 等级（如 INFO/WARNING/ERROR）。文件不存在或读取失败时返回 INFO。
    """
    level_map = {
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    try:
        if section is None:
            try:
                section = get_run_domain() or DEFAULT_DOMAIN_LR_REAR
            except Exception:
                section = DEFAULT_DOMAIN_LR_REAR
        cfg = configparser.ConfigParser()
        config_path = resolve_main_config_path(base_dir)
        cfg.read(config_path, encoding="utf-8")
        level_str = cfg.get(section, OPTION_LOG_LEVEL_MIN, fallback="info").strip().lower()
        return level_map.get(level_str, logging.INFO)
    except Exception:
        return logging.INFO


def get_error_module(fail_text: str) -> str:
    """根据错误原因返回所属模块名称（用于日志「错误模块【xxx】」）。参数: fail_text — 失败原因文案。返回: 模块名字符串。"""
    return ErrorModuleResolver.resolve(fail_text)


def is_progress_message(msg: str) -> bool:
    """判断是否为「正常进度」类消息（不受 log_level_min 限制）。参数: msg — 日志消息。返回: bool。"""
    if not msg or not isinstance(msg, str):
        return False
    progress_prefixes = (
        "解析 Excel 文件:",
        "处理Excel=",
        "生成文件:",
        "目录模式 CAN 生成汇总",
        "Master .can 文件已生成",
        "所有文件生成完成",
        # 同时处理历史/新文案两种写法（带「文件的」与不带）
        "未生成 .can 文件的 Excel 汇总",
        "未生成 .can 的 Excel 汇总",
        # XML 侧未生成汇总前缀
        "未生成 XML 文件的 Excel 汇总",
        "  Excel=",
        "  [未生成汇总] Excel=",
    )
    return any(progress_prefix in msg for progress_prefix in progress_prefixes)


def log_progress_or_info(
    logger_instance: logging.Logger,
    msg: str,
    main_logger: Optional[logging.Logger] = None,
) -> None:
    """进度类消息用 PROGRESS_LEVEL 写，否则用 info。参数: logger_instance — 主 logger；msg — 消息；main_logger — 可选同步写入。无返回值。"""
    if is_progress_message(msg):
        logger_instance.log(PROGRESS_LEVEL, msg)
        if main_logger and logger_instance is not main_logger:
            main_logger.log(PROGRESS_LEVEL, msg)
    else:
        logger_instance.info(msg)
        if main_logger and logger_instance is not main_logger:
            main_logger.info(msg)
