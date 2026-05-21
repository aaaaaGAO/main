#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用于 caseid_clean_dup.log 的“同进程去重”过滤器。

背景：
- 一键生成流程里，CAN 与 XML 两个模块都可能记录“用例ID清洗/重复”到同一个 log 文件；
- 若两边输出的消息字符串相同，会导致日志出现重复行。

目标：
- 在同一个 Python 进程中，同一条消息只写入一次（不影响业务逻辑，只影响日志）。
- 每次新任务开始时需调用 LogDedupManager.reset() 清空去重集合，否则 Web 二次点击时
  相同内容会被误判为重复而不再写入新日志目录。
"""

from __future__ import annotations

import logging
from typing import ClassVar, Set


class LogDedupManager:
    """同进程日志去重状态管理器（为 run_context 重置提供统一入口）。"""

    _seen: ClassVar[Set[str]] = set()

    @classmethod
    def reset(cls) -> None:
        """清空去重集合，供每次新任务开始时调用（如 RunLogContext.reset）。"""
        cls._seen.clear()


class DedupOnceFilter(logging.Filter):
    """同进程去重：相同 message 仅保留第一次。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """同进程去重：相同 message 仅放行第一次。参数: record — 日志记录。返回: True 放行，False 丢弃。"""
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        if msg in LogDedupManager._seen:
            return False
        LogDedupManager._seen.add(msg)
        # 防止极端情况下集合无限增长（保守上限）
        if len(LogDedupManager._seen) > 200000:
            LogDedupManager._seen.clear()
        return True
