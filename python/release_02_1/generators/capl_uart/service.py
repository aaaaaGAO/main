#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UART 生成调度 service，通过 .runtime 委托根脚本实现。"""

from __future__ import annotations

import sys
import traceback
import os
from typing import Any

from infra.excel.workbook import ExcelService
from services.config_constants import SECTION_CENTRAL, SECTION_PATHS, UART_COMM_CFG_KEYS

from . import runtime as rt


class UARTGeneratorService:
    """接管 UART 主编排流程的 service。"""

    def run_pipeline(self, *, workbook_cache: dict[str, Any] | None = None) -> None:
        rt.flush_std_streams()
        base_dir, config_path = rt.resolve_runtime_paths()

        print("=" * 60, flush=True)
        print("从当前主配置文件生成 Uart.txt 文件", flush=True)
        print("=" * 60, flush=True)

        logger = rt.setup_logging(base_dir)
        try:
            rt.get_parse_logger(base_dir)
        except Exception:
            pass

        orig_stdout = sys.stdout
        if sys.stdout is not None:
            try:
                sys.stdout = rt.build_stdout_tee(logger, sys.stdout)
            except Exception:
                orig_stdout = None

        try:
            config = rt.load_config_with_repair(config_path, logger)
            if not config.has_section(SECTION_CENTRAL) and not config.has_section(SECTION_PATHS):
                raise ValueError("配置文件缺少 [CENTRAL] 节")

            uart_rs232_config = rt.read_uart_rs232_config(config)
            if uart_rs232_config:
                print(f"\n读取串口通信配置: {uart_rs232_config}", flush=True)
                print(
                    f" 找到 {len(uart_rs232_config)} 个有效配置项，将生成[UARTRS232]节",
                    flush=True,
                )
            elif config.has_section(SECTION_CENTRAL) and any(
                config.has_option(SECTION_CENTRAL, item_key) for item_key in UART_COMM_CFG_KEYS
            ):
                print("警告: 配置项存在但所有值都为空，跳过[UARTRS232]节生成", flush=True)
            else:
                print("未找到串口通信配置", flush=True)

            if uart_rs232_config and uart_rs232_config.get("frameTypeIs8676"):
                frame_type_value = uart_rs232_config.get("frameTypeIs8676")
            else:
                frame_type_value = rt.read_frame_type_value(config)

            input_excel, _, output_path = rt.resolve_io_paths(config, base_dir)
            print(f"\n输入文件: {input_excel}", flush=True)
            print(f"输出文件: {output_path}", flush=True)
            print(f"FrameTypeIs8676 = {frame_type_value}", flush=True)

            ivi_to_mcu_messages: list = []
            mcu_to_ivi_messages: list = []
            uart_workbook = None
            normalized_excel_path = os.path.normcase(os.path.abspath(input_excel))
            should_close_workbook = workbook_cache is None
            try:
                print(f"\n读取 Excel 文件: {input_excel}")
                if workbook_cache is not None:
                    uart_workbook = workbook_cache.get(normalized_excel_path)
                if uart_workbook is None:
                    uart_workbook = ExcelService.open_workbook(
                        input_excel,
                        data_only=True,
                        read_only=True,
                    )
                    if workbook_cache is not None:
                        workbook_cache[normalized_excel_path] = uart_workbook
                print("\n读取 IVIToMCU sheet...")
                ivi_to_mcu_messages = rt.read_uart_excel_data(
                    input_excel,
                    sheet_name="IVIToMCU",
                    workbook=uart_workbook,
                )
                print(f"找到 {len(ivi_to_mcu_messages)} 个消息")
                for msg in ivi_to_mcu_messages:
                    print(f"  - Msg:0x{msg['msg_id']} {msg['message_name']} ({len(msg['signals'])} 个信号)")

                print("读取 MCUToIVI sheet...", flush=True)
                mcu_to_ivi_messages = rt.read_uart_excel_data(
                    input_excel,
                    sheet_name="MCUToIVI",
                    workbook=uart_workbook,
                )
                print(f"找到 {len(mcu_to_ivi_messages)} 个消息")
                for msg in mcu_to_ivi_messages:
                    print(f"  - Msg:0x{msg['msg_id']} {msg['message_name']} ({len(msg['signals'])} 个信号)")
            except FileNotFoundError as file_error:
                if uart_rs232_config:
                    print(
                        f"警告: 未找到或未选择有效的 UART 通信矩阵 Excel（{file_error}），"
                        "将仅根据串口通信配置生成 [UARTRS232] 段。",
                        flush=True,
                    )
                else:
                    raise
            finally:
                if should_close_workbook and uart_workbook is not None:
                    try:
                        uart_workbook.close()
                    except Exception:
                        pass

            if not ivi_to_mcu_messages and not mcu_to_ivi_messages:
                if uart_rs232_config:
                    print(
                        "提示: IVIToMCU / MCUToIVI 均无数据，已根据串口通信配置生成 Uart.txt（仅含 [UARTRS232] 时无矩阵段）。",
                        flush=True,
                    )
                else:
                    raise ValueError(
                        "IVIToMCU 和 MCUToIVI 两个 sheet 均解析失败（表头缺少必填列或 sheet 不存在），"
                        "且未配置串口通信参数（uart_comm_*），无法生成 Uart.txt"
                    )

            print("\n生成文件...", flush=True)
            uart_content = rt.generate_uart_content(
                frame_type_value,
                ivi_to_mcu_messages,
                mcu_to_ivi_messages,
                uart_rs232_config,
            )
            uart_content = uart_content.replace("\r\n", "\n").replace("\n", "\r\n")
            rt.write_text_safe(output_path, uart_content)
            print("文件已保存（utf-8 或 gb18030）", flush=True)

            print(f"\n文件已生成: {output_path}", flush=True)
            print("=" * 60, flush=True)
        except Exception as error:
            print(f"错误: {error}")
            print("\n详细错误信息:")
            traceback.print_exc()
            raise
        finally:
            if orig_stdout is not None:
                sys.stdout = orig_stdout
