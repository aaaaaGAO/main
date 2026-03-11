#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infra：基础设施层（纯技术实现）

本包不直接导出符号，作为命名空间聚合以下子包，供 services、core、generators 引用：

- config     : 配置 I/O — read_config(config_path)、read_fixed_config(base_dir)、split_input_lines 等。
- excel      : Excel 引擎与表头解析（底层读写、列索引解析）。
- filesystem : 路径与文件系统 — get_base_dir、find_config_path、get_project_root。
- logger     : 日志 — PROGRESS_LEVEL、过滤器、TeeToLogger、get_log_level_from_config、get_error_module 等。

目标：收敛配置/Excel/日志/路径等 I/O 与技术细节，为上层提供稳定 API。
"""

__all__ = []

