#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UART 运行期委托：从 runtime_io 取实现，供 UARTGeneratorService 无 hooks 调用。
"""

from __future__ import annotations

from .runtime_io import UARTExcelParser, UARTGenerationUtility

build_stdout_tee = UARTGenerationUtility.build_stdout_tee
flush_std_streams = UARTGenerationUtility.flush_std_streams
generate_uart_content = UARTGenerationUtility.generate_uart_content
get_parse_logger = UARTGenerationUtility.get_parse_logger
load_config_with_repair = UARTGenerationUtility.load_config_with_repair
read_frame_type_value = UARTGenerationUtility.read_frame_type_value
read_uart_excel_data = UARTExcelParser.read_uart_excel_data
read_uart_rs232_config = UARTGenerationUtility.read_uart_rs232_config
resolve_io_paths = UARTGenerationUtility.resolve_io_paths
resolve_runtime_paths = UARTGenerationUtility.resolve_runtime_paths
setup_logging = UARTGenerationUtility.setup_logging
write_text_safe = UARTGenerationUtility.write_text_safe

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
