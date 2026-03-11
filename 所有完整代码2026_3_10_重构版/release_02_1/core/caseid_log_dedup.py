#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用于 caseid_clean_dup.log 的“同进程去重”过滤器。

背景：
- 一键生成流程里，CAN 与 XML 两个模块都可能记录“用例ID清洗/重复”到同一个 log 文件；
- 若两边输出的消息字符串相同，会导致日志出现重复行。

目标：
- 在同一个 Python 进程中，同一条消息只写入一次（不影响业务逻辑，只影响日志）。
- 每次新任务开始时需调用 reset_dedup_filter() 清空去重集合，否则 Web 二次点击时
  相同内容会被误判为重复而不再写入新日志目录。
"""

from __future__ import annotations

import logging
from typing import Set

_SEEN: Set[str] = set()


def reset_dedup_filter() -> None:
    """清空去重集合，供每次新任务开始时调用（如 log_run_context.reset_run_context）。"""
    _SEEN.clear()


class DedupOnceFilter(logging.Filter):
    """同进程去重：相同 message 仅保留第一次。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """同进程去重：相同 message 仅放行第一次。参数: record — 日志记录。返回: True 放行，False 丢弃。"""
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        if msg in _SEEN:
            return False
        _SEEN.add(msg)
        # 防止极端情况下集合无限增长（保守上限）
        if len(_SEEN) > 200000:
            _SEEN.clear()
        return True
