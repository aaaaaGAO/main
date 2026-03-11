#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置服务（ConfigService）

目标：
- 把原 app.py 里零散的 INI 读写 / 清洗逻辑集中到一个地方管理
- 对上只暴露“读/写业务配置”的方法，不再在路由层直接操作 configparser

当前状态：
- 提供基础的读取 / 保存 / 获取分节字典能力
- 复杂的重复节清洗、格式化写回，可从 app.py 逐步迁移到 TODO 标记的方法中
"""

from __future__ import annotations

import configparser
import os
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Optional

from infra.config import read_fixed_config


@dataclass
class ConfigPaths:
    """配置相关路径信息。"""

    base_dir: str
    config_path: str


class ConfigService:
    """
    配置服务：封装 Configuration.txt / FixedConfig.txt 的访问。

    使用方式（后续在 web/routes 或 app.py 中）：
        svc = ConfigService.from_base_dir(base_dir)
        cfg = svc.load_main_config()
        lr_rear = svc.get_section_dict(cfg, "LR_REAR")
        svc.update_section("LR_REAR", {"input_excel": "xxx.xlsx"})
    """

    def __init__(self, paths: ConfigPaths) -> None:
        self.paths = paths

    # ------------------------------------------------------------------
    # 构造方法
    # ------------------------------------------------------------------
    @classmethod
    def from_base_dir(cls, base_dir: str, config_filename: str = "Configuration.txt") -> "ConfigService":
        """从项目根目录创建 ConfigService 实例。
        参数:
            base_dir: 项目根目录。
            config_filename: 主配置文件名，默认 Configuration.txt；不存在时尝试 Configuration_can.txt。
        返回: ConfigService 实例。
        """
        base_dir = os.path.abspath(base_dir)
        cfg_path = os.path.join(base_dir, config_filename)
        if not os.path.exists(cfg_path):
            # 兼容旧的 Configuration_can.txt 命名
            alt_path = os.path.join(base_dir, "Configuration_can.txt")
            cfg_path = alt_path if os.path.exists(alt_path) else cfg_path
        return cls(ConfigPaths(base_dir=base_dir, config_path=cfg_path))

    # ------------------------------------------------------------------
    # 读取配置
    # ------------------------------------------------------------------
    def load_main_config(self) -> configparser.ConfigParser:
        """读取主配置文件。无参数。返回: ConfigParser 实例（不存在则为空）。"""
        cfg = configparser.ConfigParser()
        if os.path.exists(self.paths.config_path):
            try:
                cfg.read(self.paths.config_path, encoding="utf-8")
            except Exception:
                # 兼容部分历史文件中混杂的非法字符
                with open(self.paths.config_path, "r", encoding="utf-8", errors="replace") as f:
                    cfg.read_file(f)
        return cfg

    def load_fixed_config(self) -> Dict[str, str]:
        """读取 FixedConfig.txt（键值优先级高于主配置）。"""
        return read_fixed_config(self.paths.base_dir)

    # ------------------------------------------------------------------
    # 查询 / 更新
    # ------------------------------------------------------------------
    @staticmethod
    def get_section_dict(cfg: configparser.ConfigParser, section: str) -> Dict[str, str]:
        """将配置中指定节转为键值字典。
        参数: cfg — 已读入的 ConfigParser；section — 节名。
        返回: 该节内所有选项的字典；节不存在则返回空字典。
        """
        if not cfg.has_section(section):
            return {}
        return {k: v for k, v in cfg.items(section)}

    def update_section(self, section: str, values: Dict[str, Any]) -> None:
        """更新指定配置节并写回主配置文件。
        参数: section — 节名；values — 选项名到值的字典（None 会转为空串）。
        无返回值。
        """
        cfg = self.load_main_config()
        if not cfg.has_section(section):
            cfg.add_section(section)
        for key, val in values.items():
            cfg.set(section, str(key), "" if val is None else str(val))

        # TODO: 将 app.py 中的“格式化写回逻辑”迁移到独立的 _write_formatted_config()，这里调用
        with open(self.paths.config_path, "w", encoding="utf-8") as f:
            cfg.write(f)

    # ------------------------------------------------------------------
    # 预留：专用 LR_REAR / PATHS 操作接口（方便路由调用）
    # ------------------------------------------------------------------
    def get_lr_rear(self) -> Dict[str, str]:
        """读取 [LR_REAR] 节内容为字典。无参数。返回: 节内键值对字典。"""
        cfg = self.load_main_config()
        return self.get_section_dict(cfg, "LR_REAR")

    def save_lr_rear(self, data: Dict[str, Any]) -> None:
        """更新 [LR_REAR] 节并写回文件。参数: data — 选项名到值的字典。无返回值。"""
        self.update_section("LR_REAR", data)

    def get_paths(self) -> Dict[str, str]:
        """读取 [PATHS] 节内容为字典。"""
        cfg = self.load_main_config()
        return self.get_section_dict(cfg, "PATHS")

    # ------------------------------------------------------------------
    # 从 app.py 迁移的 LR_REAR 相关更新逻辑（第一阶段：仅封装 LR_REAR / PATHS 等）
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_level(v: Any) -> str:
        """levels 空则写 ALL。"""
        if v is None:
            return "ALL"
        s = str(v).strip()
        return s if s else "ALL"

    @staticmethod
    def _normalize_selected_sheets_str(sheets_str: Any) -> str:
        """
        将前端传来的 selected_sheets 字符串归一化为「仅文件名|sheet」格式，
        行为保持与 app.py 中的 _normalize_selected_sheets_str 一致。
        """
        if not sheets_str or not str(sheets_str).strip():
            return ""
        parts: list[str] = []
        normalized_str = unicodedata.normalize("NFC", str(sheets_str).strip())
        for p in normalized_str.split(","):
            p = p.strip()
            if "|" in p:
                table, sheet = p.split("|", 1)
                key = unicodedata.normalize("NFC", os.path.basename(str(table).strip()))
                sheet_name = unicodedata.normalize("NFC", str(sheet).strip())
                parts.append(f"{key}|{sheet_name}")
            elif p:
                parts.append(p)
        return ",".join(parts)

    def update_lr_rear_and_related(self, cfg: configparser.ConfigParser, preset_data: Dict[str, Any]) -> None:
        """
        按照原 app.py /api/save_preset 中的逻辑，更新：
        - [LR_REAR]   : case_levels/平台/车型/input_excel/output_dir/didinfo/cin/selected_sheets/log_level_min
        - [IOMAPPING] : inputs
        - [DID_CONFIG]: input_excel/output_dir/output_filename
        - [CONFIG_ENUM]: inputs

        注意：
        - 不负责 CENTRAL/DTC/FILTER 等部分，保持与原函数分段一致，以便分阶段迁移。
        - cfg 为已经加载并做过重复节清理的 ConfigParser 实例。
        """
        # 确保节存在
        if not cfg.has_section("LR_REAR"):
            cfg.add_section("LR_REAR")

        # 筛选器：levels 空则 ALL；平台/车型/Target Version 选什么写什么，空表示全部生成
        cfg.set("LR_REAR", "case_levels", self._normalize_level(preset_data.get("levels", "ALL")))
        cfg.set("LR_REAR", "case_platforms", (preset_data.get("platforms") or "").strip())
        cfg.set("LR_REAR", "case_models", (preset_data.get("models") or "").strip())
        cfg.set("LR_REAR", "case_target_versions", (preset_data.get("target_versions") or "").strip())

        # 输出目录：仅写 LR_REAR，自此不再把各页面业务配置回写到 PATHS
        out_root = preset_data.get("out_root", "")
        if out_root:
            cfg.set("LR_REAR", "output_dir", out_root)

        # CAN 输入路径：仅写 LR_REAR
        can_input = preset_data.get("can_input")
        if can_input:
            val = can_input
            for sec in ["LR_REAR"]:
                if cfg.has_section(sec):
                    cfg.remove_option(sec, "input_excel_dir")
                    cfg.remove_option(sec, "Input_Excel_Dir")
            if not cfg.has_section("LR_REAR"):
                cfg.add_section("LR_REAR")
            cfg.set("LR_REAR", "input_excel", val)

        # IO_MAPPING
        if preset_data.get("io_excel"):
            if not cfg.has_section("IOMAPPING"):
                cfg.add_section("IOMAPPING")
            cfg.set("IOMAPPING", "inputs", f"{preset_data['io_excel']} | *")

        # DID_CONFIG + CONFIG_ENUM
        if preset_data.get("didconfig_excel"):
            if not cfg.has_section("DID_CONFIG"):
                cfg.add_section("DID_CONFIG")
            cfg.set("DID_CONFIG", "input_excel", preset_data["didconfig_excel"])
            if out_root:
                cfg.set("DID_CONFIG", "output_dir", out_root)
            if not cfg.has_option("DID_CONFIG", "output_filename"):
                cfg.set("DID_CONFIG", "output_filename", "DIDConfig.txt")

            if not cfg.has_section("CONFIG_ENUM"):
                cfg.add_section("CONFIG_ENUM")
            cfg.set("CONFIG_ENUM", "inputs", f"{preset_data['didconfig_excel']} | *")

        # ResetDid_Value 配置表（didinfo_inputs）
        didinfo_excel = preset_data.get("didinfo_excel", "")
        if didinfo_excel and didinfo_excel.strip():
            if not cfg.has_section("LR_REAR"):
                cfg.add_section("LR_REAR")
            cfg.set("LR_REAR", "didinfo_inputs", f"{didinfo_excel} | *")

        # Clib 配置表（cin_input_excel）
        cin_excel = preset_data.get("cin_excel", "")
        if cin_excel and cin_excel.strip():
            if not cfg.has_section("LR_REAR"):
                cfg.add_section("LR_REAR")
            cfg.set("LR_REAR", "cin_input_excel", cin_excel)

        # 勾选的 sheet 与日志生成选择
        lr_sheets = self._normalize_selected_sheets_str(preset_data.get("selected_sheets") or "")
        if lr_sheets:
            cfg.set("LR_REAR", "selected_sheets", lr_sheets)
        elif cfg.has_option("LR_REAR", "selected_sheets"):
            cfg.remove_option("LR_REAR", "selected_sheets")

        log_level = (
            (preset_data.get("log_level") or preset_data.get("c_log_level") or preset_data.get("d_log_level") or "info")
            .strip()
            .lower()
        )
        if log_level in ("info", "warning", "error"):
            cfg.set("LR_REAR", "log_level_min", log_level)

    # ------------------------------------------------------------------
    # 预留：去重 / 清理 / 导入导出（从 app.py 迁移）
    # ------------------------------------------------------------------
    def clean_duplicate_sections(self) -> None:
        """
        TODO: 从 app.py 迁移“重复节清理”逻辑到这里。

        建议拆分为：
        - _detect_duplicates()
        - _merge_section()
        - _write_formatted_config()
        """
        raise NotImplementedError("clean_duplicate_sections() 逻辑待从 app.py 迁移。")

