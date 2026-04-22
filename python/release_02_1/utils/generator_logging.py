#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成器日志公共常量与约定（CAN / CIN / XML 等共用）。

- CASEID_LOG_PATTERNS : 委托 generators.capl_cin.constants（用例ID 清洗/重复类日志过滤模式）
- 日志级别：前端选择 info -> 输出 INFO+WARNING+ERROR；warning -> WARNING+ERROR；error -> 仅 ERROR。
  各生成器在设置 FileHandler 时请使用 utils.logger.get_log_level_from_config(base_dir) 作为 fh.setLevel()，
  以实现与前端 log_level_min 一致。
"""

from __future__ import annotations

# 委托 generators.capl_cin.constants，保持现有调用稳定
from generators.capl_cin.constants import CASEID_LOG_PATTERNS
