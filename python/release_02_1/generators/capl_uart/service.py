#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UART 生成调度 service。不再依赖 UARTLegacyHooks，通过 .runtime 委托根脚本实现。"""

from __future__ import annotations

import sys
import traceback

from . import runtime as _rt


class UARTGeneratorService:
    """接管 UART 旧版主编排流程的 service。"""

    def run_legacy_pipeline(self) -> None:
        _rt.flush_std_streams()
        base_dir, config_path = _rt.resolve_runtime_paths()

        print("=" * 60, flush=True)
        print("从 Configuration.txt 生成 Uart.txt 文件", flush=True)
        print("=" * 60, flush=True)

        logger = _rt.setup_logging(base_dir)
        try:
            _rt.get_parse_logger(base_dir)
        except Exception:
            pass

        orig_stdout = sys.stdout
        if sys.stdout is not None:
            try:
                sys.stdout = _rt.build_stdout_tee(logger, sys.stdout)
            except Exception:
                orig_stdout = None

        try:
            config = _rt.load_config_with_repair(config_path, logger)
            if not config.has_section("CENTRAL") and not config.has_section("PATHS"):
                raise ValueError("配置文件缺少 [CENTRAL] 节")

            uart_rs232_config = _rt.read_uart_rs232_config(config)
            if uart_rs232_config:
                print(f"\n读取串口通信配置: {uart_rs232_config}", flush=True)
                print(
                    f" 找到 {len(uart_rs232_config)} 个有效配置项，将生成[UARTRS232]节",
                    flush=True,
                )
            elif config.has_section("CENTRAL") and any(
                config.has_option("CENTRAL", k)
                for k in (
                    "uart_comm_port",
                    "uart_comm_baudrate",
                    "uart_comm_dataBits",
                    "uart_comm_stopBits",
                    "uart_comm_kHANDSHAKE_DISABLED",
                    "uart_comm_parity",
                    "uart_comm_frameTypeIs8676",
                )
            ):
                print("警告: 配置项存在但所有值都为空，跳过[UARTRS232]节生成", flush=True)
            else:
                print("未找到串口通信配置", flush=True)

            if uart_rs232_config and uart_rs232_config.get("frameTypeIs8676"):
                frame_type_value = uart_rs232_config.get("frameTypeIs8676")
            else:
                frame_type_value = _rt.read_frame_type_value(config)

            input_excel, _, output_path = _rt.resolve_io_paths(config, base_dir)
            print(f"\n输入文件: {input_excel}", flush=True)
            print(f"输出文件: {output_path}", flush=True)
            print(f"FrameTypeIs8676 = {frame_type_value}", flush=True)

            print(f"\n读取 Excel 文件: {input_excel}")
            print("\n读取 IVIToMCU sheet...")
            ivi_to_mcu_messages = _rt.read_uart_excel_data(input_excel, sheet_name="IVIToMCU")
            print(f"找到 {len(ivi_to_mcu_messages)} 个消息")
            for msg in ivi_to_mcu_messages:
                print(f"  - Msg:0x{msg['msg_id']} {msg['message_name']} ({len(msg['signals'])} 个信号)")

            print("读取 MCUToIVI sheet...", flush=True)
            mcu_to_ivi_messages = _rt.read_uart_excel_data(input_excel, sheet_name="MCUToIVI")
            print(f"找到 {len(mcu_to_ivi_messages)} 个消息")
            for msg in mcu_to_ivi_messages:
                print(f"  - Msg:0x{msg['msg_id']} {msg['message_name']} ({len(msg['signals'])} 个信号)")

            if not ivi_to_mcu_messages and not mcu_to_ivi_messages:
                raise ValueError(
                    "IVIToMCU 和 MCUToIVI 两个 sheet 均解析失败（表头缺少必填列或 sheet 不存在），无法生成 Uart.txt"
                )

            print("\n生成文件...", flush=True)
            uart_content = _rt.generate_uart_content(
                frame_type_value,
                ivi_to_mcu_messages,
                mcu_to_ivi_messages,
                uart_rs232_config,
            )
            uart_content = uart_content.replace("\r\n", "\n").replace("\n", "\r\n")
            _rt.write_text_safe(output_path, uart_content)
            print("文件已保存（utf-8 或 gb18030）", flush=True)

            print(f"\n文件已生成: {output_path}", flush=True)
            print("=" * 60, flush=True)
        except Exception as e:
            print(f"错误: {e}")
            print("\n详细错误信息:")
            traceback.print_exc()
            raise
        finally:
            if orig_stdout is not None:
                sys.stdout = orig_stdout
