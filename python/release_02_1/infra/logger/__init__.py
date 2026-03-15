#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infra.logger：日志基础设施（底层）

导出符号与用途说明：
- PROGRESS_LEVEL : 进度日志级别常量，用于区分进度条与普通 info。
- ProgressOnlyFilter / ExcludeProgressFilter : 仅输出进度 / 排除进度的过滤器。
- SubstringFilter / ExcludeSubstringsFilter : 按子串包含/排除的过滤器。
- ProgressFormatter : 进度条格式器。
- TeeToLogger : 将 stdout 同时 tee 到 Logger，用于捕获打印输出。
- get_log_level_from_config(...) : 从配置读取日志级别。
- get_error_module(...) : 解析“错误模块”名称，用于错误归类。

当前阶段作为 infra 统一入口；业务进度规则可下沉到 generators。
"""

from infra.logger.api import (
    PROGRESS_LEVEL,
    ExcludeProgressFilter,
    ExcludeSubstringsFilter,
    ProgressFormatter,
    ProgressOnlyFilter,
    SubstringFilter,
    TeeToLogger,
    get_error_module,
    get_log_level_from_config,
)

__all__ = [
    "PROGRESS_LEVEL",
    "ProgressOnlyFilter",
    "ExcludeProgressFilter",
    "SubstringFilter",
    "ExcludeSubstringsFilter",
    "ProgressFormatter",
    "TeeToLogger",
    "get_log_level_from_config",
    "get_error_module",
]

