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
from typing import Any, Dict

from infra.config import read_fixed_config
from infra.filesystem import (
    ProjectPaths,
    resolve_main_config_path,
    resolve_main_config_write_path,
)
from services.config_manager import ConfigManager
from services.config_constants import (
    DEPRECATED_INPUT_EXCEL_DIR_OPTION_CANDIDATES,
    DEFAULT_DID_CONFIG_FILENAME,
    OPTION_CASE_LEVELS,
    OPTION_CASE_MODELS,
    OPTION_CASE_PLATFORMS,
    OPTION_CASE_TARGET_VERSIONS,
    OPTION_CIN_INPUT_EXCEL,
    OPTION_DIDINFO_INPUTS,
    OPTION_INPUT_EXCEL,
    OPTION_INPUTS,
    OPTION_LOG_LEVEL_MIN,
    OPTION_OUTPUT_DIR,
    OPTION_OUTPUT_FILENAME,
    OPTION_SELECTED_SHEETS,
    SECTION_CONFIG_ENUM,
    SECTION_DID_CONFIG,
    SECTION_IOMAPPING,
    SECTION_LR_REAR,
    SECTION_PATHS,
    STATE_KEY_LR_CAN_INPUT,
    STATE_KEY_LR_CIN_EXCEL,
    STATE_KEY_LR_DIDCONFIG_EXCEL,
    STATE_KEY_LR_DIDINFO_EXCEL,
    STATE_KEY_LR_IO_EXCEL,
    STATE_KEY_LR_LEVELS,
    STATE_KEY_LR_LOG_LEVEL,
    STATE_KEY_LR_MODELS,
    STATE_KEY_LR_OUT_ROOT,
    STATE_KEY_LR_PLATFORMS,
    STATE_KEY_LR_SELECTED_SHEETS,
    STATE_KEY_LR_TARGET_VERSIONS,
    VALID_LOG_LEVELS,
    cin_input_excel_value_from_ui_path,
    input_excel_value_from_ui_path,
    didinfo_inputs_value_from_ui_single_path,
    io_inputs_value_from_ui_single_path,
)


@dataclass
class ConfigPaths:
    """配置相关路径信息。"""

    base_dir: str
    config_path: str


class ConfigService:
    """
    配置服务：封装主配置文件 / 固定配置文件的访问。

    使用方式（后续在 web/routes 或 app.py 中）：
        svc = ConfigService.from_base_dir(base_dir)
        cfg = svc.load_main_config()
        lr_rear = svc.get_section_dict(cfg, "LR_REAR")
        svc.update_section("LR_REAR", {"input_excel": "xxx.xlsx"})
    """

    def __init__(
        self,
        paths: ConfigPaths,
        *,
        config_manager: ConfigManager | None = None,
    ) -> None:
        self.paths = paths
        self.config_manager = config_manager or ConfigManager(
            paths.base_dir,
            config_path=paths.config_path,
        )

    # ------------------------------------------------------------------
    # 构造方法
    # ------------------------------------------------------------------
    @classmethod
    def from_base_dir(cls, base_dir: str, config_filename: str = "Configuration.ini") -> "ConfigService":
        """从项目根目录创建 ConfigService 实例。
        参数:
            base_dir: 项目根目录。
            config_filename: 非标准文件名时按该名单一路径读写；标准名则使用默认 Configuration.ini 解析与写回。
        返回: ConfigService 实例。
        """
        project_paths = ProjectPaths.from_base_dir(base_dir, config_filename=config_filename)
        if config_filename not in (None, "Configuration.ini"):
            config_path = resolve_main_config_path(
                base_dir,
                config_filename=config_filename,
            )
            return cls(
                ConfigPaths(
                    base_dir=project_paths.base_dir,
                    config_path=config_path,
                ),
                config_manager=ConfigManager(
                    project_paths.base_dir,
                    config_path=config_path,
                ),
            )
        return cls(
            ConfigPaths(
                base_dir=project_paths.base_dir,
                config_path=resolve_main_config_write_path(base_dir),
            ),
            config_manager=ConfigManager(project_paths.base_dir, config_path=None),
        )

    # ------------------------------------------------------------------
    # 读取配置
    # ------------------------------------------------------------------
    def load_main_config(self) -> configparser.ConfigParser:
        """读取主配置文件。无参数。返回: ConfigParser 实例（不存在则为空）。"""
        return self.config_manager.load_config()

    def load_fixed_config(self) -> Dict[str, str]:
        """读取固定配置文件（键值优先级高于主配置）。"""
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
        normalized_values = {
            str(key): "" if value is None else str(value)
            for key, value in values.items()
        }
        self.config_manager.update_domain_config(section, normalized_values)

    # ------------------------------------------------------------------
    # 预留：专用 LR_REAR / PATHS 操作接口（方便路由调用）
    # ------------------------------------------------------------------
    def get_lr_rear(self) -> Dict[str, str]:
        """读取 [LR_REAR] 节内容为字典。无参数。返回: 节内键值对字典。"""
        cfg = self.load_main_config()
        return self.get_section_dict(cfg, SECTION_LR_REAR)

    def save_lr_rear(self, data: Dict[str, Any]) -> None:
        """更新 [LR_REAR] 节并写回文件。参数: data — 选项名到值的字典。无返回值。"""
        self.update_section(SECTION_LR_REAR, data)

    def build_lr_rear_section_data(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """将 LR_REAR 页面请求体映射为 [LR_REAR] 节键值。"""
        lr_data: Dict[str, str] = {}

        levels = payload.get(STATE_KEY_LR_LEVELS)
        if levels is not None:
            lr_data[OPTION_CASE_LEVELS] = levels if str(levels).strip() else "ALL"

        platforms = payload.get(STATE_KEY_LR_PLATFORMS)
        if platforms is not None:
            lr_data[OPTION_CASE_PLATFORMS] = str(platforms).strip()

        models = payload.get(STATE_KEY_LR_MODELS)
        if models is not None:
            lr_data[OPTION_CASE_MODELS] = str(models).strip()

        out_root = payload.get(STATE_KEY_LR_OUT_ROOT)
        if out_root is not None:
            lr_data[OPTION_OUTPUT_DIR] = str(out_root).strip()

        selected_sheets = payload.get(STATE_KEY_LR_SELECTED_SHEETS)
        if selected_sheets is not None:
            lr_data[OPTION_SELECTED_SHEETS] = str(selected_sheets).strip()

        log_level = str(payload.get(STATE_KEY_LR_LOG_LEVEL) or "").strip().lower()
        if log_level in VALID_LOG_LEVELS:
            lr_data[OPTION_LOG_LEVEL_MIN] = log_level

        can_input = payload.get(STATE_KEY_LR_CAN_INPUT)
        if can_input is not None:
            lr_data[OPTION_INPUT_EXCEL] = input_excel_value_from_ui_path(can_input)

        did_path = payload.get(STATE_KEY_LR_DIDINFO_EXCEL)
        if did_path is not None:
            did_val = didinfo_inputs_value_from_ui_single_path(did_path)
            if did_val:
                lr_data[OPTION_DIDINFO_INPUTS] = did_val

        cin_raw = payload.get(STATE_KEY_LR_CIN_EXCEL)
        if cin_raw is not None:
            cin_val = cin_input_excel_value_from_ui_path(cin_raw)
            if cin_val:
                lr_data[OPTION_CIN_INPUT_EXCEL] = cin_val

        return lr_data

    def get_paths(self) -> Dict[str, str]:
        """读取 [PATHS] 节内容为字典。"""
        cfg = self.load_main_config()
        return self.get_section_dict(cfg, SECTION_PATHS)

    # ------------------------------------------------------------------
    # 从 app.py 迁移的 LR_REAR 相关更新逻辑（第一阶段：仅封装 LR_REAR / PATHS 等）
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_level(v: Any) -> str:
        """levels 空则写 ALL。"""
        if v is None:
            return "ALL"
        level_text = str(v).strip()
        return level_text if level_text else "ALL"

    @staticmethod
    def normalize_selected_sheets_str(sheets_str: Any) -> str:
        """
        将前端传来的 selected_sheets 字符串归一化为「仅文件名|sheet」格式，
        行为保持与 app.py 中的 normalize_selected_sheets_str 一致。
        """
        if not sheets_str or not str(sheets_str).strip():
            return ""
        parts: list[str] = []
        normalized_str = unicodedata.normalize("NFC", str(sheets_str).strip())
        for item in normalized_str.split(","):
            item = item.strip()
            if "|" in item:
                table, sheet = item.split("|", 1)
                key = unicodedata.normalize("NFC", os.path.basename(str(table).strip()))
                sheet_name = unicodedata.normalize("NFC", str(sheet).strip())
                parts.append(f"{key}|{sheet_name}")
            elif item:
                parts.append(item)
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
        if not cfg.has_section(SECTION_LR_REAR):
            cfg.add_section(SECTION_LR_REAR)

        # 筛选器：levels 空则 ALL；平台/车型/Target Version 选什么写什么，空表示全部生成
        cfg.set(
            SECTION_LR_REAR,
            OPTION_CASE_LEVELS,
            self.normalize_level(preset_data.get(STATE_KEY_LR_LEVELS, "ALL")),
        )
        cfg.set(
            SECTION_LR_REAR,
            OPTION_CASE_PLATFORMS,
            (preset_data.get(STATE_KEY_LR_PLATFORMS) or "").strip(),
        )
        cfg.set(
            SECTION_LR_REAR,
            OPTION_CASE_MODELS,
            (preset_data.get(STATE_KEY_LR_MODELS) or "").strip(),
        )
        cfg.set(
            SECTION_LR_REAR,
            OPTION_CASE_TARGET_VERSIONS,
            (preset_data.get(STATE_KEY_LR_TARGET_VERSIONS) or "").strip(),
        )

        # 输出目录：仅写 LR_REAR，自此不再把各页面业务配置回写到 PATHS
        out_root = preset_data.get(STATE_KEY_LR_OUT_ROOT, "")
        if out_root:
            cfg.set(SECTION_LR_REAR, OPTION_OUTPUT_DIR, out_root)

        # CAN 输入路径：仅写 LR_REAR
        can_input = preset_data.get(STATE_KEY_LR_CAN_INPUT)
        if can_input:
            val = input_excel_value_from_ui_path(can_input)
            for sec in [SECTION_LR_REAR]:
                if cfg.has_section(sec):
                    for option_name in DEPRECATED_INPUT_EXCEL_DIR_OPTION_CANDIDATES:
                        cfg.remove_option(sec, option_name)
            if not cfg.has_section(SECTION_LR_REAR):
                cfg.add_section(SECTION_LR_REAR)
            cfg.set(SECTION_LR_REAR, OPTION_INPUT_EXCEL, val)

        # IO_MAPPING
        io_val = io_inputs_value_from_ui_single_path(preset_data.get(STATE_KEY_LR_IO_EXCEL))
        if io_val:
            if not cfg.has_section(SECTION_IOMAPPING):
                cfg.add_section(SECTION_IOMAPPING)
            cfg.set(SECTION_IOMAPPING, OPTION_INPUTS, io_val)

        # DID_CONFIG + CONFIG_ENUM
        didconfig_path = str(preset_data.get(STATE_KEY_LR_DIDCONFIG_EXCEL, "") or "").strip()
        if didconfig_path:
            if not cfg.has_section(SECTION_DID_CONFIG):
                cfg.add_section(SECTION_DID_CONFIG)
            cfg.set(SECTION_DID_CONFIG, OPTION_INPUT_EXCEL, didconfig_path)
            if out_root:
                cfg.set(SECTION_DID_CONFIG, OPTION_OUTPUT_DIR, out_root)
            if not cfg.has_option(SECTION_DID_CONFIG, OPTION_OUTPUT_FILENAME):
                cfg.set(SECTION_DID_CONFIG, OPTION_OUTPUT_FILENAME, DEFAULT_DID_CONFIG_FILENAME)

            if not cfg.has_section(SECTION_CONFIG_ENUM):
                cfg.add_section(SECTION_CONFIG_ENUM)
            cfg.set(
                SECTION_CONFIG_ENUM,
                OPTION_INPUTS,
                didinfo_inputs_value_from_ui_single_path(didconfig_path),
            )

        # ResetDid_Value 配置表（didinfo_inputs）
        did_val = didinfo_inputs_value_from_ui_single_path(preset_data.get(STATE_KEY_LR_DIDINFO_EXCEL, ""))
        if did_val:
            if not cfg.has_section(SECTION_LR_REAR):
                cfg.add_section(SECTION_LR_REAR)
            cfg.set(SECTION_LR_REAR, OPTION_DIDINFO_INPUTS, did_val)

        # Clib 配置表（cin_input_excel）
        cin_path = cin_input_excel_value_from_ui_path(preset_data.get(STATE_KEY_LR_CIN_EXCEL, ""))
        if cin_path:
            if not cfg.has_section(SECTION_LR_REAR):
                cfg.add_section(SECTION_LR_REAR)
            cfg.set(SECTION_LR_REAR, OPTION_CIN_INPUT_EXCEL, cin_path)

        # 勾选的 sheet 与日志生成选择
        lr_sheets = self.normalize_selected_sheets_str(preset_data.get(STATE_KEY_LR_SELECTED_SHEETS) or "")
        if lr_sheets:
            cfg.set(SECTION_LR_REAR, OPTION_SELECTED_SHEETS, lr_sheets)
        elif cfg.has_option(SECTION_LR_REAR, OPTION_SELECTED_SHEETS):
            cfg.remove_option(SECTION_LR_REAR, OPTION_SELECTED_SHEETS)

        log_level = (
            (preset_data.get(STATE_KEY_LR_LOG_LEVEL) or preset_data.get("c_log_level") or preset_data.get("d_log_level") or "info")
            .strip()
            .lower()
        )
        if log_level in VALID_LOG_LEVELS:
            cfg.set(SECTION_LR_REAR, OPTION_LOG_LEVEL_MIN, log_level)

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

