#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成器配置模块（供 CAN/CIN/XML/DIDInfo/DIDConfig/UART 复用）

封装「读主配置文件 + 固定配置文件」与「按 section/option 取路径、输出名等」，
各生成器通过 GeneratorConfig 实例统一读配置，避免各脚本内重复 _read_config / _read_fixed_config 逻辑。
"""

from __future__ import annotations

import configparser
import os
from typing import Optional, Sequence

from infra.config import (
    read_config_if_exists,
    read_config_tolerant_duplicates,
    read_fixed_config,
)
from infra.filesystem import resolve_main_config_path
from services.config_constants import SECTION_PATHS


class GeneratorConfig:
    """
    生成器配置封装类。

    功能：
      - 统一加载主配置文件与固定配置文件。
      - 提供 get(section, key, fallback)、get_fixed(key, fallback)，优先固定配置再主配置。
      - 提供 config_path、base_dir、raw_config、fixed_config 供需要直接访问的调用方。

    使用方式：
      config = GeneratorConfig(base_dir, tolerant_duplicates=False)
      config.load()
      value = config.get("PATHS", "Output_Dir", fallback="./output")
      mapping_excel = config.get_fixed("mapping_excel") or config.get("PATHS", "Mapping_Excel", fallback="")
    """

    def __init__(
        self,
        base_dir: str,
        *,
        config_path: Optional[str] = None,
        tolerant_duplicates: bool = False,
    ):
        """初始化生成器配置封装。参数：base_dir — 工程根目录；config_path — 配置文件路径，None 时自动查找；tolerant_duplicates — 是否容忍同节重复 option 并去重。返回：无返回值。"""
        self.base_dir = os.path.abspath(base_dir)
        self._config_path = config_path
        self._tolerant_duplicates = tolerant_duplicates
        self._config: Optional[configparser.ConfigParser] = None
        self._fixed_config: Optional[dict[str, str]] = None
        self._loaded = False

    def load(self) -> "GeneratorConfig":
        """加载主配置文件与固定配置文件到内存，可链式调用。
        无参数。使用 self.base_dir / self._config_path。返回: self，便于链式调用。
        """
        if self._config_path is None:
            self._config_path = resolve_main_config_path(self.base_dir)
        if self._config_path is None or not os.path.exists(self._config_path):
            self._config = configparser.ConfigParser()
            self._config.optionxform = str
            self._fixed_config = read_fixed_config(self.base_dir)
            self._loaded = True
            return self
        if self._tolerant_duplicates:
            self._config = read_config_tolerant_duplicates(self._config_path)
        else:
            self._config = read_config_if_exists(self._config_path)
        self._fixed_config = read_fixed_config(self.base_dir)
        self._loaded = True
        return self

    def get(self, section: str, key: str, fallback: str = "") -> str:
        """
        获取配置值：优先从固定配置取（key 或 key 小写），再从主配置的 section/key 取。
        形参：section — 节名；key — 选项名；fallback — 未找到时的默认值。
        返回：配置值字符串。
        """
        if not self._loaded:
            self.load()
        if self._fixed_config:
            v = self._fixed_config.get(key) or self._fixed_config.get(key.lower() if key else "")
            if v is not None:
                return (v or "").strip()
        if self._config is None:
            return fallback
        try:
            return (self._config.get(section, key, fallback=fallback) or "").strip()
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def get_fixed(self, key: str, fallback: str = "") -> str:
        """仅从 FixedConfig 取指定键。参数: key — 固定配置项名；fallback — 未找到时的默认值。返回: 配置值字符串。"""
        if not self._loaded:
            self.load()
        if self._fixed_config and key in self._fixed_config:
            return (self._fixed_config.get(key) or "").strip()
        return fallback

    def get_from_section(self, section: str, key: str, fallback: str = "") -> str:
        """仅从主配置指定节读取键值（不读取 FixedConfig）。"""
        if not self._loaded:
            self.load()
        if self._config is None:
            return fallback
        try:
            return (self._config.get(section, key, fallback=fallback) or "").strip()
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def get_required_from_section(self, section: str, key: str) -> str:
        """仅从主配置指定节读取必填键；缺失或为空时抛错。"""
        value = self.get_from_section(section, key, fallback="")
        if value:
            return value
        raise ValueError(f"缺少必填配置: [{section}] {key}")

    def get_first(
        self,
        candidates: Sequence[tuple[str, str]],
        fallback: str = "",
    ) -> str:
        """按候选顺序获取第一个非空配置值。参数：candidates — [(section, option), ...] 候选列表；fallback — 所有候选均为空时返回的默认值。返回：第一个非空配置值或 fallback。"""
        for section, key in candidates:
            value = self.get(section, key, fallback="")
            if value:
                return value
        return fallback

    def has_section(self, section: str) -> bool:
        """判断主配置是否包含指定节。参数: section — 节名。返回: True/False。"""
        if not self._loaded:
            self.load()
        return self._config is not None and self._config.has_section(section)

    def has_option(self, section: str, option: str) -> bool:
        """判断主配置指定节是否包含指定选项。参数: section — 节名；option — 选项名。返回: True/False。"""
        if not self._loaded:
            self.load()
        return self._config is not None and self._config.has_option(section, option)

    @property
    def config_path(self) -> Optional[str]:
        """当前使用的配置文件路径。"""
        return self._config_path

    @property
    def config_dir(self) -> str:
        """配置文件所在目录（用于解析相对路径）。"""
        if self._config_path and os.path.isfile(self._config_path):
            return os.path.dirname(os.path.abspath(self._config_path))
        return self.base_dir

    @property
    def raw_config(self) -> configparser.ConfigParser:
        """原始主配置对象，供需要直接 .options() / .get() 的调用方使用。"""
        if not self._loaded:
            self.load()
        return self._config or configparser.ConfigParser()

    @property
    def fixed_config(self) -> dict[str, str]:
        """固定配置字典。"""
        if not self._loaded:
            self.load()
        return self._fixed_config or {}
