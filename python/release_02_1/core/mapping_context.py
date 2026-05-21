#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一映射上下文：一次性加载 io_mapping 与 config_enum，供 CAN / CIN 等生成器共用。
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from typing import Optional

from core.translator.config_enum import ConfigEnumContext, ConfigEnumUtility
from core.translator.io_mapping import IOMappingContext, IOMappingUtility
from services.config_constants import DEFAULT_DOMAIN_LR_REAR


@dataclass
class MappingContext:
    """封装 io_mapping 与 config_enum 上下文，由 from_config 统一加载。"""

    io_mapping: Optional[IOMappingContext] = None
    config_enum: Optional[ConfigEnumContext] = None

    @classmethod
    def from_config(
        cls,
        config: configparser.ConfigParser,
        *,
        base_dir: Optional[str] = None,
        config_path: Optional[str] = None,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
    ) -> "MappingContext":
        """从 Configuration 一次性加载 io_mapping 与 config_enum 上下文。参数：config — 已读入的 ConfigParser 或同类对象；base_dir — 项目根目录；config_path — 配置文件路径（可选）；domain — 配置域（如 LR_REAR/CENTRAL/DTC）。返回：MappingContext 实例，含 io_mapping 与 config_enum（可能为 None）。"""
        return cls(
            io_mapping=IOMappingUtility.load_context_from_config(
                config,
                base_dir=base_dir,
                config_path=config_path,
                domain=domain,
            ),
            config_enum=ConfigEnumUtility.load_context_from_config(
                config,
                base_dir=base_dir,
                config_path=config_path,
                domain=domain,
            ),
        )
