#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UART 运行期委托：从 runtime_io 取实现，供 UARTGeneratorService 无 hooks 调用。
"""

from __future__ import annotations

from .runtime_io import (
    build_stdout_tee,
    flush_std_streams,
    generate_uart_content,
    get_parse_logger,
    load_config_with_repair,
    read_frame_type_value,
    read_uart_excel_data,
    read_uart_rs232_config,
    resolve_io_paths,
    resolve_runtime_paths,
    setup_logging,
    write_text_safe,
)

__all__ = [
    "build_stdout_tee",
    "flush_std_streams",
    "generate_uart_content",
    "get_parse_logger",
    "load_config_with_repair",
    "read_frame_type_value",
    "read_uart_excel_data",
    "read_uart_rs232_config",
    "resolve_io_paths",
    "resolve_runtime_paths",
    "setup_logging",
    "write_text_safe",
]
