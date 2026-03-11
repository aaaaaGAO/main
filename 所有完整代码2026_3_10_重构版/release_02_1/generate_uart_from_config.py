#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UART 生成入口脚本

本脚本为执行入口，从 Configuration.txt 与 UART 通信矩阵 Excel 生成 Uart.txt 文件。

步骤说明：
  ① 读配置 — 从 [PATHS] 读 UART 输入/输出路径、FrameTypeIs8676；从 [CENTRAL] 读串口参数（端口、波特率等）
  ② 读 Excel — 打开配置的 UART 通信矩阵，按 IVIToMCU / MCUToIVI 两个 Sheet 读取消息与信号
  ③ 生成 Uart.txt — 含 [UARTRS232]（串口参数）、[IVIToMCU]、[MCUToIVI] 三段；未配置串口时仅生成后两段

编排与实现分离：具体实现位于 generators/capl_uart/（runtime_io、service）。
使用方式：python generate_uart_from_config.py
"""

import sys
import traceback

from generators.capl_uart.service import UARTGeneratorService


def main() -> None:
    """UART 生成主流程：读配置 → 读 Excel（IVIToMCU / MCUToIVI）→ 生成 Uart.txt → 写入输出目录。

    功能：调用 UARTGeneratorService.run_legacy_pipeline，内部完成配置解析、Excel 解析、文本拼装与写入。

    参数：无（配置与路径均从 Configuration.txt 及 FixedConfig.txt 读取）。

    返回：无返回值。
    """
    UARTGeneratorService().run_legacy_pipeline()


if __name__ == "__main__":
    if sys.stdout is not None:
        try:
            sys.stdout.flush()
        except (AttributeError, OSError):
            pass
    if sys.stderr is not None:
        try:
            sys.stderr.flush()
        except (AttributeError, OSError):
            pass
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断执行", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n程序执行出错: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if sys.stderr is not None:
            try:
                sys.stderr.flush()
            except (AttributeError, OSError):
                pass
        sys.exit(1)
