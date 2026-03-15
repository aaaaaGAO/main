#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators.capl_uart：UART 生成器

根据配置与输入生成 UART 相关脚本或数据。

导出符号说明：
- UARTGeneratorService : 生成服务入口。具体构造参数与 run 接口见 service 模块。
  调用方通过此类执行 UART 生成任务。
"""

from .service import UARTGeneratorService


__all__ = ["UARTGeneratorService"]
