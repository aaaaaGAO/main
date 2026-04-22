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
from infra.filesystem import resolve_fixed_config_path, resolve_main_config_path


class GeneratorConfig:
    CONFIG_CACHE: dict[tuple[str, str, bool], tuple[float, float, configparser.ConfigParser, dict[str, str]]] = {}

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
        self.config_path_value = config_path
        self.tolerant_duplicates = tolerant_duplicates
        self.config_parser: Optional[configparser.ConfigParser] = None
        self.fixed_config_data: Optional[dict[str, str]] = None
        self.loaded = False

    def load(self) -> "GeneratorConfig":
        """加载主配置文件与固定配置文件到内存，可链式调用。
        无参数。使用 self.base_dir / self.config_path_value。返回: self，便于链式调用。
        """
        if self.config_path_value is None:
            self.config_path_value = resolve_main_config_path(self.base_dir)
        if self.config_path_value is None or not os.path.exists(self.config_path_value):
            self.config_parser = configparser.ConfigParser()
            self.config_parser.optionxform = str
            self.fixed_config_data = read_fixed_config(self.base_dir)
            self.loaded = True
            return self
        abs_config_path = os.path.abspath(self.config_path_value)
        fixed_config_path = resolve_fixed_config_path(self.base_dir)
        main_mtime = os.path.getmtime(abs_config_path)
        fixed_mtime = os.path.getmtime(fixed_config_path) if os.path.exists(fixed_config_path) else -1.0
        cache_key = (self.base_dir, abs_config_path, self.tolerant_duplicates)
        cached = self.CONFIG_CACHE.get(cache_key)
        if cached and cached[0] == main_mtime and cached[1] == fixed_mtime:
            self.config_parser = self.clone_config_parser(cached[2])
            self.fixed_config_data = dict(cached[3])
            self.loaded = True
            return self
        if self.tolerant_duplicates:
            self.config_parser = read_config_tolerant_duplicates(self.config_path_value)
        else:
            self.config_parser = read_config_if_exists(self.config_path_value)
        self.fixed_config_data = read_fixed_config(self.base_dir)
        self.CONFIG_CACHE[cache_key] = (
            main_mtime,
            fixed_mtime,
            self.clone_config_parser(self.config_parser),
            dict(self.fixed_config_data or {}),
        )
        self.loaded = True
        return self

    @staticmethod
    def clone_config_parser(source: configparser.ConfigParser) -> configparser.ConfigParser:
        """
        深拷贝主配置 `ConfigParser`：保留 `optionxform`、各节**原始**选项值（`raw=True`），避免多实例共享。

        参数：source — 已加载的源解析器。返回：新 `ConfigParser` 实例。
        """
        cloned = configparser.ConfigParser()
        cloned.optionxform = str
        if source.defaults():
            cloned.read_dict({configparser.DEFAULTSECT: dict(source.defaults())})
        for section_name in source.sections():
            cloned.read_dict({section_name: dict(source.items(section_name, raw=True))})
        return cloned

    def get(self, section: str, item_key: str, fallback: str = "") -> str:
        """
        获取配置值：优先从固定配置取（key 或 key 小写），再从主配置的 section/key 取。
        形参：section — 节名；key — 选项名；fallback — 未找到时的默认值。
        返回：配置值字符串。
        """
        if not self.loaded:
            self.load()
        if self.fixed_config_data:
            fixed_value = self.fixed_config_data.get(item_key) or self.fixed_config_data.get(
                item_key.lower() if item_key else ""
            )
            if fixed_value is not None:
                return (fixed_value or "").strip()
        if self.config_parser is None:
            return fallback
        try:
            return (self.config_parser.get(section, item_key, fallback=fallback) or "").strip()
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def get_fixed(self, item_key: str, fallback: str = "") -> str:
        """仅从 FixedConfig 取指定键。参数: key — 固定配置项名；fallback — 未找到时的默认值。返回: 配置值字符串。"""
        if not self.loaded:
            self.load()
        if self.fixed_config_data and item_key in self.fixed_config_data:
            return (self.fixed_config_data.get(item_key) or "").strip()
        return fallback

    def get_from_section(self, section: str, item_key: str, fallback: str = "") -> str:
        """仅从主配置指定节读取键值（不读取 FixedConfig）。"""
        if not self.loaded:
            self.load()
        if self.config_parser is None:
            return fallback
        try:
            return (self.config_parser.get(section, item_key, fallback=fallback) or "").strip()
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def get_required_from_section(self, section: str, item_key: str) -> str:
        """仅从主配置指定节读取必填键；缺失或为空时抛错。"""
        item_value = self.get_from_section(section, item_key, fallback="")
        if item_value:
            return item_value
        raise ValueError(f"缺少必填配置: [{section}] {item_key}")

    def coalesce_options_in_section(
        self,
        section_name: str,
        option_names: Sequence[str],
        *,
        fallback: str = "",
    ) -> str:
        """仅在同一配置节内，按选项名顺序取第一个非空值（使用 ``get``，含固定配置覆盖逻辑）；不跨节扫描。"""
        for item_key in option_names:
            item_value = self.get(section_name, item_key, fallback="").strip()
            if item_value:
                return item_value
        return fallback

    def has_section(self, section: str) -> bool:
        """判断主配置是否包含指定节。参数: section — 节名。返回: True/False。"""
        if not self.loaded:
            self.load()
        return self.config_parser is not None and self.config_parser.has_section(section)

    def has_option(self, section: str, option: str) -> bool:
        """判断主配置指定节是否包含指定选项。参数: section — 节名；option — 选项名。返回: True/False。"""
        if not self.loaded:
            self.load()
        return self.config_parser is not None and self.config_parser.has_option(section, option)

    @property
    def config_path(self) -> Optional[str]:
        """当前使用的配置文件路径。"""
        return self.config_path_value

    @property
    def config_dir(self) -> str:
        """配置文件所在目录（用于解析相对路径）。"""
        if self.config_path_value and os.path.isfile(self.config_path_value):
            return os.path.dirname(os.path.abspath(self.config_path_value))
        return self.base_dir

    @property
    def raw_config(self) -> configparser.ConfigParser:
        """原始主配置对象，供需要直接 .options() / .get() 的调用方使用。"""
        if not self.loaded:
            self.load()
        return self.config_parser or configparser.ConfigParser()

    @property
    def fixed_config(self) -> dict[str, str]:
        """固定配置字典。"""
        if not self.loaded:
            self.load()
        return self.fixed_config_data or {}
