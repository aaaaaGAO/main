#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一映射上下文：一次性加载 io_mapping 与 config_enum，供 CAN / CIN 等生成器共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from core.translator.config_enum import ConfigEnumContext
    from core.translator.io_mapping import IOMappingContext


@dataclass
class MappingContext:
    """封装 io_mapping 与 config_enum 上下文，由 from_config 统一加载。"""

    io_mapping: Optional[Any] = None  # IOMappingContext | None
    config_enum: Optional[Any] = None  # ConfigEnumContext | None

    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        base_dir: Optional[str] = None,
        config_path: Optional[str] = None,
        domain: str = "LR_REAR",
    ) -> "MappingContext":
        """从 Configuration 一次性加载 io_mapping 与 config_enum 上下文。参数：config — 已读入的 ConfigParser 或兼容对象；base_dir — 项目根目录；config_path — 配置文件路径（可选）；domain — 配置域（如 LR_REAR/CENTRAL/DTC）。返回：MappingContext 实例，含 io_mapping 与 config_enum（可能为 None）。"""
        from core.translator.config_enum import load_config_enum_from_config
        from core.translator.io_mapping import load_io_mapping_from_config

        return cls(
            io_mapping=load_io_mapping_from_config(
                config,
                base_dir=base_dir,
                config_path=config_path,
                domain=domain,
            ),
            config_enum=load_config_enum_from_config(
                config,
                base_dir=base_dir,
                config_path=config_path,
                domain=domain,
            ),
        )
