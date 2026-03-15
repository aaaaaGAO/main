#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators.capl_didconfig：DID 配置生成器

根据配置与输入生成 DID 相关配置脚本/数据。

导出符号说明：
- DIDConfigGeneratorService : 生成服务入口。具体构造参数与 run 接口见 service 模块。
  调用方通过此类执行 DID 配置生成任务。
"""

from .service import DIDConfigGeneratorService

__all__ = ["DIDConfigGeneratorService"]