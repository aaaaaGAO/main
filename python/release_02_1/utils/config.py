#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置中心（供所有生成器复用）

- read_config()       : 读取 Configuration.txt（委托 core.common.config_access）
- read_fixed_config() : 读取 FixedConfig.txt（委托 core.common.config_access）
- ConfigCenter        : 单例，统一管理 Configuration.txt + FixedConfig.txt
"""

from __future__ import annotations

import configparser
import unicodedata
from pathlib import Path
from typing import Optional

from core.common.config_access import (
    read_config as _read_config,
    read_config_tolerant_duplicates as _read_config_tolerant_duplicates,
    read_fixed_config as _read_fixed_config,
)
from utils.path_utils import find_config_path, get_base_dir


def read_config(config_path: str) -> configparser.ConfigParser:
    """读取 Configuration.txt，保留选项名大小写。参数: config_path — 配置文件路径。返回: ConfigParser。"""
    return _read_config(config_path)


def read_config_tolerant_duplicates(config_path: str) -> configparser.ConfigParser:
    """读取 Configuration.txt，同节内重复选项去重后解析。参数: config_path — 配置文件路径。返回: ConfigParser。"""
    return _read_config_tolerant_duplicates(config_path)


def read_fixed_config(base_dir: str) -> dict[str, str]:
    """从 FixedConfig.txt 读取固定配置项。参数: base_dir — 工程根目录。返回: {key: value} 字典。"""
    return _read_fixed_config(base_dir)


class ConfigCenter:
    """
    全局配置中心（单例）。

    职责：
    - 统一读取 Configuration.txt + FixedConfig.txt
    - 提供 NFC 归一化的路径获取
    - 供所有生成器共享配置数据

    使用方式：
        center = ConfigCenter(base_dir)   # 首次加载
        center = ConfigCenter()           # 后续获取同一实例（若 base_dir 未变）

    注意：Web 每次生成任务可能修改 Configuration.txt，需要调用 reload() 刷新。
    """

    _instance: Optional[ConfigCenter] = None
    _base_dir: Optional[str] = None

    def __new__(cls, base_dir: str | None = None):
        if cls._instance is None or (base_dir and base_dir != cls._base_dir):
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, base_dir: str | None = None):
        if self._initialized and not base_dir:
            return
        if base_dir:
            self._base_dir = base_dir
        elif not self._base_dir:
            self._base_dir = get_base_dir()
        self._load()
        self._initialized = True

    def _load(self) -> None:
        config_path = find_config_path(self._base_dir)
        if config_path:
            self.config_path = config_path
            self.raw_config = read_config(config_path)
        else:
            self.config_path = None
            self.raw_config = configparser.ConfigParser()
            self.raw_config.optionxform = str

        self.fixed_config = read_fixed_config(self._base_dir)

    def reload(self) -> None:
        """重新加载配置文件（Web 场景下每次任务前调用）。"""
        self._load()

    @property
    def base_dir(self) -> str:
        return self._base_dir

    def get(self, section: str, key: str, fallback: str = "") -> str:
        """
        获取配置值，优先 FixedConfig，其次 Configuration.txt。
        """
        fixed_val = self.fixed_config.get(key)
        if fixed_val is not None:
            return fixed_val
        try:
            return self.raw_config.get(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def get_path(self, section: str, key: str, fallback: str = "") -> Path:
        """
        获取路径值：统一 NFC 归一化 + 转为 Path 对象。
        """
        raw = self.get(section, key, fallback)
        if not raw:
            return Path(fallback) if fallback else Path()
        normalized = unicodedata.normalize("NFC", raw.strip())
        return Path(normalized)

    def has_section(self, section: str) -> bool:
        return self.raw_config.has_section(section)

    def has_option(self, section: str, key: str) -> bool:
        return self.raw_config.has_option(section, key)

    @staticmethod
    def reset() -> None:
        """重置单例（仅用于测试）。"""
        ConfigCenter._instance = None
        ConfigCenter._base_dir = None
