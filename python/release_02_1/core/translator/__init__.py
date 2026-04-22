#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.translator：领域层翻译器（统一入口）

提供配置与 Excel 映射的加载与查询，供解析器、生成器将“名称”转为“路径/枚举值”：

导出符号说明：
- load_io_mapping_from_config(cfg, base_dir) -> IOMappingContext
  从主配置文件加载 IO 映射表；解析失败抛出 IOMappingParseError。
- IOMappingContext : 按 Name 查 Path 等，供步骤翻译使用。
- load_config_enum_from_config(cfg, base_dir) -> ConfigEnumContext
  从配置加载 configuration 枚举；解析失败抛出 ConfigEnumParseError。
- ConfigEnumContext : 按配置项名查枚举值。
- load_keyword_specs_from_excel(...) -> list[KeywordSpec]
  从 Excel 加载关键字规格，用于步骤解析与生成。
- KeywordSpec : 关键字规格数据（名称、参数等）。
"""

from core.translator.config_enum import ConfigEnumContext, ConfigEnumParseError, load_config_enum_from_config
from core.translator.io_mapping import IOMappingContext, IOMappingParseError, load_io_mapping_from_config
from core.translator.keyword_mapping import KeywordSpec, load_keyword_specs_from_excel

__all__ = [
    "load_io_mapping_from_config",
    "IOMappingContext",
    "IOMappingParseError",
    "load_config_enum_from_config",
    "ConfigEnumContext",
    "ConfigEnumParseError",
    "load_keyword_specs_from_excel",
    "KeywordSpec",
]

