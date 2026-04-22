#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators.capl_xml：XML 用例/配置生成器

根据配置与 Excel 输入生成 XML 格式的用例或配置。

导出符号说明：
- XMLGeneratorService : 生成服务入口。具体构造参数与 run 接口见 service 模块。
  调用方通过此类执行 XML 生成任务。
"""

from .service import XMLGeneratorService
from .entrypoint import run_generation

__all__ = ["XMLGeneratorService", "run_generation"]
