#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators.capl_didinfo：DID 信息生成器

根据配置与 Excel/输入生成 DID 信息脚本或数据。

导出符号说明：
- DIDInfoGeneratorService : 生成服务入口。具体构造参数与 run 接口见 service 模块。
  调用方通过此类执行 DID 信息生成任务。
"""

from .service import DIDInfoGeneratorService

__all__ = ["DIDInfoGeneratorService"]
