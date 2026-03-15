#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIN/CAN 共用的 case-id 相关日志过滤常量。"""

# 这些模式用于从主日志中过滤掉已拆分到 `caseid_clean_dup.log` 的提示，
# 避免同一条“用例 ID 清洗/重复”信息在多个日志文件里重复出现。
CASEID_LOG_PATTERNS = (
    "用例ID为空，跳过",
    "[warn] 用例ID清洗",
    "[warn] 用例ID含中文已转拼音",
    "[dup] 用例ID重复",
)

__all__ = ["CASEID_LOG_PATTERNS"]
