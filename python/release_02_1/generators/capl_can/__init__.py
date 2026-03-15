#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators.capl_can：CAPL CAN 用例生成器

从 Excel 用例表生成 CAN 域 CAPL 脚本，组织流程：Excel 仓库 -> 步骤翻译 -> 渲染 -> 写文件。

导出符号与用途说明：
- CANGeneratorService(base_dir=None, ...) : 总调度服务，继承 BaseGeneratorTask；base_dir 为工程根目录。
- CANExcelRepository : Excel 用例数据访问，按 sheet/行读取用例。
- CANStepTranslator : 将步骤行翻译为 CAPL 代码片段（结合 io_mapping、config_enum、keyword_specs）。
- CANFileRenderer : 将翻译结果渲染为完整 .can 文件内容。
- CANEntrypointSupport : 入口/运行时支持（供外部调用 run 时注入配置与运行时参数）。
- log_progress_or_info : 进度或普通日志输出封装。
"""

from .excel_repo import CANExcelRepository
from .logging import log_progress_or_info
from .renderer import CANFileRenderer
from .runtime import CANEntrypointSupport
from .service import CANGeneratorService
from .translator import CANStepTranslator

__all__ = [
    "CANExcelRepository",
    "CANEntrypointSupport",
    "CANFileRenderer",
    "CANGeneratorService",
    "CANStepTranslator",
    "log_progress_or_info",
]
