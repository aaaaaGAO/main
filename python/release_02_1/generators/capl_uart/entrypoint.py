#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UART 生成入口模块。

从当前主配置文件与 UART 通信矩阵 Excel 生成 Uart.txt（串口参数与 IVIToMCU/MCUToIVI 等），
供 TaskService 与命令行调用。具体实现委托同包下 service.UARTGeneratorService。
"""

from __future__ import annotations

import sys
import traceback
from typing import Any

from .service import UARTGeneratorService


def run_generation(*, workbook_cache: dict[str, Any] | None = None) -> None:
    """UART 生成主流程，供 TaskService 与命令行调用。

    功能：调用 UARTGeneratorService.run_pipeline，内部完成配置解析、Excel 解析、
    文本拼装与写入（[UARTRS232]、[IVIToMCU]、[MCUToIVI] 等段）。

    参数：
        workbook_cache：可选工作簿缓存字典；传入后可在同一生成流程中复用
            已打开 workbook，降低重复 load 开销。

    返回：无。
    """
    UARTGeneratorService().run_pipeline(workbook_cache=workbook_cache)


class UARTEntrypointWorkflowUtility:
    """UART 入口编排统一工具类。"""

    @staticmethod
    def run_generation(*args: Any, **kwargs: Any) -> Any:
        return run_generation(*args, **kwargs)


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
        run_generation()
    except KeyboardInterrupt:
        print("\n用户中断执行", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print(f"\n程序执行出错: {error}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if sys.stderr is not None:
            try:
                sys.stderr.flush()
            except (AttributeError, OSError):
                pass
        sys.exit(1)
