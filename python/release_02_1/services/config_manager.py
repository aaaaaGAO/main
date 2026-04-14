#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理器（ConfigManager）— 基础设施层

目标：收纳所有对主配置文件的读、写、去重、格式化逻辑。
职责：提供 load_ui_data()（给前端显示）、save_ui_data()（保存预设）、
      update_domain_config()、save_formatted()、sync_to_file()。
线程安全：使用实例锁防止多线程同时写配置导致文件损坏。
"""

from __future__ import annotations

import configparser
import os
import re
import threading
import json
from typing import Any, Dict, List, Optional

from infra.config import read_config_if_exists, read_fixed_config
from infra.filesystem import (
    ProjectPaths,
    resolve_fixed_config_path,
    resolve_fixed_config_write_path,
    resolve_main_config_path,
    resolve_main_config_write_path,
    resolve_named_subdir,
)
from services.derived_config_files_service import DerivedConfigFilesService
from services.config_constants import (
    DEFAULT_UDS_FILENAME,
    CENTRAL_MANAGED_KEYS,
    CENTRAL_UART_UI_KEY_MAP,
    CONFIG_KEY_SECTIONS,
    FILTER_OPTION_KEYS,
    OPTION_CASE_LEVELS,
    OPTION_CIN_INPUT_EXCEL,
    OPTION_DIDINFO_INPUTS,
    OPTION_INPUT_EXCEL,
    OPTION_INPUTS,
    OPTION_LOG_LEVEL_MIN,
    OPTION_OUTPUT_DIR,
    OPTION_SELECTED_SHEETS,
    OPTION_UDS_ECU_QUALIFIER,
    SECTION_CENTRAL,
    SECTION_CONFIG_ENUM,
    SECTION_DID_CONFIG,
    SECTION_DTC,
    SECTION_DTC_CONFIG_ENUM,
    SECTION_DTC_IOMAPPING,
    SECTION_IGNITION_CYCLE,
    SECTION_IOMAPPING,
    SECTION_LR_REAR,
    SECTION_PATHS,
    UDS_DOMAIN_SECTIONS,
    VALID_LOG_LEVELS,
)


def clean_duplicate_sections(config_path: str) -> List[str]:
    """
    清理配置文件中的重复节和重复选项，保留第一个出现的节和选项。
    保护文件开头的注释和空行。返回清理后的行列表。
    """
    if not os.path.exists(config_path):
        return []

    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            lines = config_file.readlines()
    except Exception as error:
        print(f"读取配置文件失败: {error}")
        return []

    seen_sections: set = set()
    seen_options: Dict[str, set] = {}
    current_section: Optional[str] = None
    in_duplicate_section = False
    cleaned_lines: List[str] = []
    first_section_found = False
    invalid_short_token_re = re.compile(r"^[A-Za-z]{2,3}$")

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1].strip()
            first_section_found = True

            if section_name in seen_sections:
                print(f"检测到重复节 [{section_name}]，跳过重复部分")
                in_duplicate_section = True
                current_section = None
            else:
                seen_sections.add(section_name)
                seen_options[section_name] = set()
                current_section = section_name
                in_duplicate_section = False
                cleaned_lines.append(line)
        else:
            if not in_duplicate_section:
                if not first_section_found:
                    cleaned_lines.append(line)
                elif "=" in stripped and not stripped.startswith("#"):
                    parts = stripped.split("=", 1)
                    option_name = parts[0].strip()
                    if not option_name:
                        continue
                    if "/" in option_name or "\\" in option_name:
                        continue
                    if option_name.startswith(","):
                        continue
                    if current_section:
                        option_lower = option_name.lower()
                        if option_lower in seen_options.get(current_section, set()):
                            continue
                        seen_options[current_section].add(option_lower)
                    cleaned_lines.append(line)
                elif stripped.startswith("#") or not stripped:
                    cleaned_lines.append(line)
                elif current_section:
                    # 节内的非注释行做更严格过滤，避免诸如 "CU1.0" 这类裸字符串残留到配置中
                    if stripped.startswith(","):
                        continue
                    _key_sections = CONFIG_KEY_SECTIONS
                    if (
                        "=" not in stripped
                        and current_section not in _key_sections
                        and invalid_short_token_re.match(stripped)
                    ):
                        continue
                    # DTC_CONFIG_ENUM 节只允许标准 key = value 行，其他裸字符串一律丢弃
                    if current_section == SECTION_DTC_CONFIG_ENUM and "=" not in stripped:
                        continue
                    if (stripped.startswith(",") or stripped.endswith(",")) and "=" not in stripped:
                        continue
                    cleaned_lines.append(line)
                else:
                    if stripped.startswith(","):
                        continue
                    if "=" not in stripped and not (
                        stripped.startswith("[") and stripped.endswith("]")
                    ):
                        continue
                    cleaned_lines.append(line)

    return cleaned_lines


def remove_invalid_config_options(config: configparser.ConfigParser) -> None:
    """从 config 中移除无效选项（如 LL、QB 等 2–3 个纯大写字母的残留）。"""
    invalid_pattern = re.compile(r"^[A-Z]{2,3}$")
    for section in config.sections():
        invalid_option_names = [
            option_name
            for option_name in config.options(section)
            if invalid_pattern.match(option_name.strip())
        ]
        for option_name in invalid_option_names:
            config.remove_option(section, option_name)
            print(f"已移除无效配置项 [{section}] {option_name}")


class ConfigManager:
    """
    配置管理器：统一主配置 / 固定配置的读、写、去重、格式化。
    使用方式：
        manager = ConfigManager.from_base_dir(base_dir)
        manager.update_domain_config("LR_REAR", {"input_excel": "a.xlsx"})
        manager.save_formatted()
    """

    _lock = threading.RLock()

    def __init__(self, base_dir: str, config_path: Optional[str] = None) -> None:
        """初始化配置管理器，绑定主配置所在目录与配置文件路径。
        参数:
            base_dir: 项目根目录，用于解析相对路径与 FixedConfig 位置。
            config_path: 主配置文件路径；为 None 时解析 `config/Configuration.ini`，写回同路径。
        """
        self.base_dir = os.path.abspath(base_dir)
        self.paths = ProjectPaths.from_base_dir(self.base_dir)
        if config_path is None:
            self._main_config_read_path = resolve_main_config_path(self.base_dir)
            self.config_path = resolve_main_config_write_path(self.base_dir)
        else:
            explicit = os.path.abspath(config_path)
            self._main_config_read_path = explicit
            self.config_path = explicit
        self.derived_config_files_service = DerivedConfigFilesService(self.base_dir)

    @classmethod
    def from_base_dir(cls, base_dir: str, config_filename: str = "Configuration.ini") -> "ConfigManager":
        """从项目根目录创建 ConfigManager 实例，自动解析主配置文件路径。
        参数:
            base_dir: 项目根目录。
            config_filename: 非标准文件名时按该名解析单一文件；标准名 `Configuration.ini` 时使用默认解析与写回路径。
        返回: ConfigManager 实例。
        """
        base_dir = os.path.abspath(base_dir)
        if config_filename not in (None, "Configuration.ini"):
            return cls(
                base_dir,
                resolve_main_config_path(base_dir, config_filename=config_filename),
            )
        return cls(base_dir, config_path=None)

    def get_fixed_config_path(self) -> str:
        return resolve_fixed_config_path(self.base_dir)

    def read_fixed_config(self) -> Dict[str, str]:
        return read_fixed_config(self.base_dir)

    def write_fixed_config(self, fixed_config: Dict[str, str]) -> None:
        """将固定配置字典写入固定配置文件（PATHS 节：映射表、输出文件名等）。
        参数:
            fixed_config: 键为配置项名、值为字符串的字典，仅写入存在且非空的键。
        无返回值。
        """
        fixed_config_path = resolve_fixed_config_write_path(self.base_dir)
        lines = [
            "# ============================================================\n",
            "# 固定配置（映射表和输出文件名）\n",
            "# ============================================================\n",
            "[PATHS]\n",
            "\n",
        ]
        mapping_keys = [
            "unified_mapping_excel", "mapping_sheets", "cin_mapping_sheet",
            "mapping_excel", "cin_mapping_excel",
        ]
        for option_name in mapping_keys:
            if fixed_config.get(option_name):
                lines.append(f"{option_name} = {fixed_config[option_name]}\n")
        lines.append("\n")
        output_keys = [
            "output_filename", "cin_output_filename", "xml_output_filename",
            "didinfo_output_filename", "didconfig_output_filename",
            "uart_output_filename", "uds_output_filename", "didinfo_variants",
        ]
        for option_name in output_keys:
            if fixed_config.get(option_name):
                lines.append(f"{option_name} = {fixed_config[option_name]}\n")
        while lines and not lines[-1].strip():
            lines.pop()
        with open(fixed_config_path, "w", encoding="utf-8") as fixed_config_file:
            fixed_config_file.writelines(lines)

    def write_uds_files(
        self, config: configparser.ConfigParser, only_domains: Optional[List[str]] = None
    ) -> None:
        """根据各域 output_dir 与 uds_ecu_qualifier 在 output_dir/Configuration 下生成 uds.txt。
        参数:
            config: 已读入的 ConfigParser，含 LR_REAR/CENTRAL/DTC 等节。
            only_domains: 仅对这些域（如 ["LR_REAR"]）写入；None 表示三域都写，避免共用 output_dir 时覆盖。
        无返回值。文件内容为 [UDS] 与 ECU_qualifier=...
        """
        all_domains = [
            (section_name, OPTION_OUTPUT_DIR, OPTION_UDS_ECU_QUALIFIER)
            for section_name in UDS_DOMAIN_SECTIONS
        ]
        domains = (
            [domain_config for domain_config in all_domains if domain_config[0] in only_domains]
            if only_domains
            else all_domains
        )

        for section, _output_option_name, uds_option_name in domains:
            if not config.has_section(section):
                continue
            uds_qualifier = config.get(section, uds_option_name, fallback="").strip()
            uds_path = self.resolve_uds_output_path(config, section, create_dir=True)
            if not uds_path or not uds_qualifier:
                continue

            config_dir = os.path.dirname(uds_path)
            legacy_uds_path = os.path.join(config_dir, DEFAULT_UDS_FILENAME)
            try:
                if (
                    os.path.normcase(os.path.abspath(legacy_uds_path))
                    != os.path.normcase(os.path.abspath(uds_path))
                    and os.path.exists(legacy_uds_path)
                ):
                    os.remove(legacy_uds_path)
                with open(uds_path, "w", encoding="utf-8") as uds_file:
                    uds_file.write("[UDS]\n")
                    uds_file.write(f"ECU_qualifier={uds_qualifier}\n")
            except Exception as error:
                print(f"写入 uds.txt 失败 ({section}): {error}")

    def resolve_output_subdir(
        self,
        output_dir: str,
        subdir_name: str,
        *,
        create_dir: bool = False,
    ) -> Optional[str]:
        return resolve_named_subdir(
            self.base_dir,
            output_dir,
            subdir_name,
            create_dir=create_dir,
        )

    def resolve_uds_output_path(
        self,
        config: configparser.ConfigParser,
        section: str,
        *,
        create_dir: bool = False,
    ) -> str:
        """统一解析各域 uds 输出路径，供写文件与路由预览共用。"""
        if not config.has_section(section):
            return ""

        output_dir = config.get(section, OPTION_OUTPUT_DIR, fallback="").strip()
        uds_qualifier = config.get(section, OPTION_UDS_ECU_QUALIFIER, fallback="").strip()
        if not output_dir or not uds_qualifier:
            return ""

        config_dir = self.resolve_output_subdir(
            output_dir,
            "Configuration",
            create_dir=create_dir,
        )
        if not config_dir:
            return ""

        fixed = self.read_fixed_config()
        uds_filename = (
            fixed.get("uds_output_filename") or DEFAULT_UDS_FILENAME
        ).strip() or DEFAULT_UDS_FILENAME
        return os.path.join(config_dir, uds_filename)

    @staticmethod
    def parse_json_value(raw: Any, default: Any) -> Any:
        """解析字符串形式的 JSON 值；空值或解析失败时返回默认值。"""
        raw_text = str(raw or "").strip()
        if not raw_text:
            return default
        try:
            return json.loads(raw_text)
        except Exception:
            return default

    @staticmethod
    def has_relay_config(relay: Any) -> bool:
        """判断单个继电器是否算已配置：须填写串口 port，或 relayID / id（前端继电器行主键）。

        仅含 relayType / 默认 coilStatuses（UI 渲染时自动补全）不算，否则用户未选串口
        或 ini 中残留骨架仍会触发生成 PowerRelayConfig.txt。
        """
        if not isinstance(relay, dict):
            return False
        port = str(relay.get("port") or "").strip()
        if port:
            return True
        relay_id = relay.get("relayID")
        if relay_id is None:
            relay_id = relay.get("id")
        if relay_id is not None and str(relay_id).strip() != "":
            return True
        return False

    def load_central_ui_json_fields(self, out: Dict[str, Any], section_data: Dict[str, Any]) -> None:
        power = self.parse_json_value(section_data.get("c_pwr", ""), {})
        if isinstance(power, dict) and (power.get("port") or "").strip():
            out["c_pwr"] = power

        relays = self.parse_json_value(section_data.get("c_rly", ""), [])
        if isinstance(relays, list) and any(self.has_relay_config(relay) for relay in relays):
            out["c_rly"] = relays

        for option_name in ("c_ig", "c_pw"):
            equipment_config = self.parse_json_value(section_data.get(option_name, ""), {})
            if (
                equipment_config
                and isinstance(equipment_config, dict)
                and (
                    equipment_config.get("equipmentType")
                    or equipment_config.get("channelNumber")
                )
            ):
                out[option_name] = equipment_config

    def write_central_config_files(self, config: configparser.ConfigParser) -> None:
        """委托派生文件服务生成中央域相关配置文件。"""
        self.derived_config_files_service.write_central_config_files(config)

    def init_fixed_config_from_main_config(self) -> None:
        if os.path.exists(self.get_fixed_config_path()) or not os.path.exists(self._main_config_read_path):
            return
        try:
            main_config = read_config_if_exists(self._main_config_read_path)
            fixed_config_values = {}
            if main_config.has_section(SECTION_PATHS):
                keys = [
                    "unified_mapping_excel", "mapping_sheets", "cin_mapping_sheet",
                    "output_filename", "cin_output_filename", "xml_output_filename",
                    "didinfo_output_filename", "didconfig_output_filename", "didinfo_variants",
                    "mapping_excel", "cin_mapping_excel",
                ]
                for option_name in keys:
                    if main_config.has_option(SECTION_PATHS, option_name):
                        fixed_config_values[option_name] = main_config.get(
                            SECTION_PATHS, option_name
                        )
            if fixed_config_values:
                self.write_fixed_config(fixed_config_values)
        except Exception as error:
            print(f"从主配置初始化固定配置失败: {error}")

    def reload_config_internal(self) -> configparser.ConfigParser:
        """读入配置并做去重后写回，再解析返回 ConfigParser。"""
        with self._lock:
            cleaned = clean_duplicate_sections(self._main_config_read_path)
            if cleaned:
                with open(self._main_config_read_path, "w", encoding="utf-8") as config_file:
                    config_file.writelines(cleaned)
            return read_config_if_exists(self._main_config_read_path)

    def reload(self) -> configparser.ConfigParser:
        """公开的配置重载入口，供跨模块调用。"""
        return self.reload_config_internal()

    def load_config(self) -> configparser.ConfigParser:
        """公开配置读取入口，供外部模块获取最新配置。"""
        return self.reload()

    @staticmethod
    def ui_state_key(prefix: str, option_name: str) -> str:
        return f"{prefix}_{option_name}" if prefix else option_name

    @classmethod
    def load_standard_domain_ui_fields(
        cls,
        out: Dict[str, Any],
        section_data: Dict[str, Any],
        *,
        prefix: str,
        include_didinfo: bool = False,
        include_cin: bool = False,
        include_uds: bool = True,
    ) -> None:
        out[cls.ui_state_key(prefix, "input")] = section_data.get(OPTION_INPUT_EXCEL, "")
        out[cls.ui_state_key(prefix, "out_root")] = section_data.get(OPTION_OUTPUT_DIR, "")
        out[cls.ui_state_key(prefix, "levels")] = section_data.get(OPTION_CASE_LEVELS, "ALL")
        out[cls.ui_state_key(prefix, "platforms")] = section_data.get("case_platforms", "")
        out[cls.ui_state_key(prefix, "models")] = section_data.get("case_models", "")
        out[cls.ui_state_key(prefix, "target_versions")] = section_data.get("case_target_versions", "")
        out[cls.ui_state_key(prefix, "selected_sheets")] = section_data.get(OPTION_SELECTED_SHEETS, "")
        out[cls.ui_state_key(prefix, "log_level")] = section_data.get(OPTION_LOG_LEVEL_MIN, "info")
        if include_uds:
            out[cls.ui_state_key(prefix, "uds_ecu_qualifier")] = section_data.get(
                OPTION_UDS_ECU_QUALIFIER,
                "",
            )
        if include_didinfo:
            didinfo_raw = section_data.get(OPTION_DIDINFO_INPUTS, "")
            out[cls.ui_state_key(prefix, "didinfo_excel")] = didinfo_raw.split(" | ")[0] if didinfo_raw else ""
        if include_cin:
            out[cls.ui_state_key(prefix, "cin_excel")] = section_data.get(OPTION_CIN_INPUT_EXCEL, "")

    @staticmethod
    def append_option_line(
        lines: List[str],
        config: configparser.ConfigParser,
        section: str,
        option: str,
        *,
        fallback: str = "",
    ) -> bool:
        if not config.has_option(section, option):
            return False
        lines.append(f"{option} = {config.get(section, option, fallback=fallback) or ''}\n")
        return True

    @classmethod
    def append_options_if_present(
        cls,
        lines: List[str],
        config: configparser.ConfigParser,
        section: str,
        options: List[str],
    ) -> bool:
        appended_any_option = False
        for option_name in options:
            appended_any_option = (
                cls.append_option_line(lines, config, section, option_name)
                or appended_any_option
            )
        return appended_any_option

    @classmethod
    def append_filter_options(
        cls,
        lines: List[str],
        config: configparser.ConfigParser,
        section: str,
    ) -> bool:
        return cls.append_options_if_present(lines, config, section, list(FILTER_OPTION_KEYS))

    @staticmethod
    def append_valid_log_level(
        lines: List[str],
        config: configparser.ConfigParser,
        section: str,
    ) -> bool:
        if not config.has_option(section, OPTION_LOG_LEVEL_MIN):
            return False
        normalized_log_level = (
            config.get(section, OPTION_LOG_LEVEL_MIN, fallback="info").strip().lower()
        )
        if normalized_log_level not in VALID_LOG_LEVELS:
            return False
        lines.append(f"{OPTION_LOG_LEVEL_MIN} = {normalized_log_level}\n")
        return True

    @staticmethod
    def append_nonempty_option(
        lines: List[str],
        config: configparser.ConfigParser,
        section: str,
        option: str,
    ) -> bool:
        if not config.has_option(section, option):
            return False
        option_value = config.get(section, option, fallback="").strip()
        if not option_value:
            return False
        lines.append(f"{option} = {option_value}\n")
        return True

    def load_ui_data(self) -> Dict[str, Any]:
        """加载主配置并平铺为前端 collectCurrentState 所需字段格式。
        无参数。从当前主配置与固定配置读入，按节映射为 can_input、out_root、c_rly 等键。
        返回: 平铺字典，键为前端 state 字段名，值为配置值（字符串/列表/字典等）。
        """
        config = self.reload_config_internal()
        out: Dict[str, Any] = {}

        # 1. LR_REAR -> 左右后域基础配置
        if config.has_section(SECTION_LR_REAR):
            lr_section = dict(config.items(SECTION_LR_REAR))
            self.load_standard_domain_ui_fields(
                out,
                lr_section,
                prefix="",
                include_didinfo=True,
                include_cin=True,
            )
            out["can_input"] = out.pop("input")

        # 2. IOMAPPING / DID_CONFIG
        if config.has_section(SECTION_IOMAPPING):
            io_mapping_inputs = config.get(SECTION_IOMAPPING, OPTION_INPUTS, fallback="")
            out["io_excel"] = (
                io_mapping_inputs.split(" | ")[0] if io_mapping_inputs else ""
            )
        if config.has_section(SECTION_DID_CONFIG):
            out["didconfig_excel"] = config.get(SECTION_DID_CONFIG, OPTION_INPUT_EXCEL, fallback="")

        # 3. CENTRAL -> c_* 字段
        if config.has_section(SECTION_CENTRAL):
            central_section = dict(config.items(SECTION_CENTRAL))
            self.load_standard_domain_ui_fields(out, central_section, prefix="c")
            # 点火循环：仅当有非空值时才返回，避免未配置时前端显示“已配置”或写入默认值
            ign_waittime = (central_section.get("ign_waittime", "") or "").strip()
            ign_current = (central_section.get("ign_current", "") or "").strip()
            if not ign_waittime and config.has_section(SECTION_IGNITION_CYCLE):
                ign_waittime = (
                    config.get(SECTION_IGNITION_CYCLE, "waitTime", fallback="") or ""
                ).strip()
            if not ign_current and config.has_section(SECTION_IGNITION_CYCLE):
                ign_current = (
                    config.get(SECTION_IGNITION_CYCLE, "current", fallback="") or ""
                ).strip()
            if ign_waittime or ign_current:
                out["c_ign_waitTime"] = ign_waittime
                out["c_ign_current"] = ign_current
            out["c_uart"] = central_section.get("uart_excel", "")
            uart_comm = {}
            for cfg_key, ui_key in CENTRAL_UART_UI_KEY_MAP.items():
                config_value = central_section.get(cfg_key, "")
                if config_value != "":
                    uart_comm[ui_key] = config_value
            out["c_uart_comm"] = uart_comm

            # 程控电源 / 继电器 / IG / PW：仅当配置中有且为“有意义”内容时才返回，避免未配置时回写默认值到主配置文件
            self.load_central_ui_json_fields(out, central_section)
            out["c_login_username"] = central_section.get("login_username", "")
            out["c_login_password"] = central_section.get("login_password", "")

        # 4. DTC -> d_* 字段
        if config.has_section(SECTION_DTC):
            dtc_section = dict(config.items(SECTION_DTC))
            self.load_standard_domain_ui_fields(
                out,
                dtc_section,
                prefix="d",
                include_didinfo=True,
                include_cin=True,
            )
        if config.has_section(SECTION_DTC_IOMAPPING):
            dtc_io_mapping_inputs = (
                config.get(SECTION_DTC_IOMAPPING, OPTION_INPUTS, fallback="") or ""
            ).strip()
            if dtc_io_mapping_inputs and "|" in dtc_io_mapping_inputs:
                path_part, sheets_part = dtc_io_mapping_inputs.split("|", 1)
                out["d_io_excel"] = path_part.strip()
                sheets_str = (sheets_part or "").strip()
                # 若为 * 或空串，表示全选，前端用空串表示“全选/不做过滤”
                out["d_io_selected_sheets"] = "" if sheets_str in ("", "*") else sheets_str
            else:
                out["d_io_excel"] = dtc_io_mapping_inputs
                out["d_io_selected_sheets"] = ""
        if config.has_section(SECTION_DTC_CONFIG_ENUM):
            did_config_inputs = config.get(
                SECTION_DTC_CONFIG_ENUM, OPTION_INPUTS, fallback=""
            )
            out["d_didconfig_excel"] = (
                did_config_inputs.split(" | ")[0] if did_config_inputs else ""
            )

        return out

    def update_domain_config(self, domain: str, data: Dict[str, Any]) -> None:
        """更新指定配置节：节不存在则创建，按 data 写入键值并格式化写回主配置。
        参数:
            domain: 节名，如 "LR_REAR"、"CENTRAL"、"DTC"。
            data: 键值对字典，键为选项名、值为字符串（None 会转为空串）。
        无返回值。
        """
        with self._lock:
            config = self.reload_config_internal()
            if not config.has_section(domain):
                config.add_section(domain)
            for option_name, option_value in data.items():
                config.set(domain, option_name, str(option_value) if option_value is not None else "")
            self.save_formatted_config(config)

    def save_formatted(self) -> None:
        """重新加载配置、移除无效项、按固定格式写回。"""
        with self._lock:
            config = self.reload_config_internal()
            remove_invalid_config_options(config)
            self.init_fixed_config_from_main_config()
            self.save_formatted_config(config)

    @staticmethod
    def is_relay_list_effectively_empty(relay_list_value: Any) -> bool:
        """判断继电器列表是否为“有效空”：空列表，或所有项均未构成有效继电器配置（与 _has_relay_config 对齐，含 id/relayID）。"""
        if relay_list_value is None or relay_list_value == "" or relay_list_value == [] or relay_list_value == {}:
            return True
        # 前端可能传回已解析的 list 或 JSON 字符串
        if isinstance(relay_list_value, str):
            relay_list_value = relay_list_value.strip()
            if relay_list_value in ("", "[]", "[{}]"):
                return True
            try:
                relay_list_value = json.loads(relay_list_value)
            except Exception:
                return False
        if not isinstance(relay_list_value, list):
            return False
        if len(relay_list_value) == 0:
            return True
        for item in relay_list_value:
            if not isinstance(item, dict):
                continue
            if ConfigManager.has_relay_config(item):
                return False
        return True

    @classmethod
    def is_effectively_empty_value(cls, option: str, value: Any) -> bool:
        if value in (None, "", [], {}):
            return True
        return option == "c_rly" and cls.is_relay_list_effectively_empty(value)

    def remove_central_managed_options(
        self,
        config: configparser.ConfigParser,
        section: str,
        section_values: Dict[str, Any],
        managed_keys: List[str],
    ) -> None:
        for managed_key in managed_keys:
            value = section_values.get(managed_key)
            if managed_key not in section_values or self.is_effectively_empty_value(managed_key, value):
                config.set(section, managed_key, "")

    def write_section_values(
        self,
        config: configparser.ConfigParser,
        section: str,
        section_values: Dict[str, Any],
    ) -> None:
        for option_name, option_value in section_values.items():
            normalized_option_name = str(option_name)
            if self.is_effectively_empty_value(normalized_option_name, option_value):
                config.set(section, normalized_option_name, "")
            else:
                config.set(section, normalized_option_name, str(option_value))

    def save_ui_data(self, data: Dict[str, Dict[str, Any]]) -> None:
        """将前端按节提交的 data 写回主配置并格式化写回文件。
        增强点：
        - 对 CENTRAL 段的 UI 托管键（如 c_pwr/c_rly/c_ig/c_pw/ign_*/login_*/uart_comm_*）做“缺失或空值则写空串”的处理，
          防止增量更新导致旧值残留，同时保持配置骨架稳定。
        - 继电器 c_rly 为列表：空列表或所有项均未构成有效继电器时视为“有效空”，写回空字符串，避免脏值残留。
        - 对所有节的键，若值为 None / 空串 / 空列表 / 空字典，统一写回空字符串，不再删除配置项。
        参数:
            data: 节名为键、值为「选项名->值」字典，如 {"LR_REAR": {"input_excel": "..."}, ...}。
        无返回值。
        """
        with self._lock:
            config = self.reload_config_internal()

            # 本次前端实际提交更新的节名列表，用于后续精确控制 UDS/中央域附属文件的生成范围
            updated_sections: List[str] = list(data.keys())

            # 中央域由前端 UI 统一托管的配置键：当前端未提供或提供的是“空值/有效空”时，应主动从配置文件中移除
            central_managed_keys = CENTRAL_MANAGED_KEYS

            for section, section_values in data.items():
                if not config.has_section(section):
                    config.add_section(section)

                # 1) CENTRAL 段：先对托管键做“缺失/空值/有效空即置空”的处理
                if section == SECTION_CENTRAL:
                    self.remove_central_managed_options(
                        config,
                        section,
                        section_values,
                        central_managed_keys,
                    )

                # 2) 通用写入逻辑：有值则 set，空值则置空；继电器列表为“有效空”时也按置空处理，避免脏数据回流
                self.write_section_values(config, section, section_values)

            # 仅针对本次更新涉及到的节生成对应的 UDS 与中央域附属文件，避免无关域被“全量刷新”
            self.save_formatted_config(config, uds_domains=updated_sections)

    def sync_to_file(self, target_path: Optional[str] = None) -> None:
        """将当前内存中的配置（去重后）同步写入指定文件。
        参数:
            target_path: 目标配置文件路径；为 None 时写回 self.config_path。
        无返回值。
        """
        output_config_path = target_path or self.config_path
        with self._lock:
            config = self.reload_config_internal()
            remove_invalid_config_options(config)
            self.save_formatted_config(config, config_path=output_config_path)

    def write_formatted_config_internal(
        self,
        config: configparser.ConfigParser,
        config_path: Optional[str] = None,
        uds_domains: Optional[List[str]] = None,
    ) -> None:
        """按固定顺序与格式将 config 写入 INI 文件，并可选写 UDS.txt / 固定配置备份。
        参数:
            config: 已加载的 ConfigParser 实例，将被写入文件。
            config_path: 目标配置文件路径；为 None 时使用 self.config_path。
            uds_domains: 仅对这些域（如 ["LR_REAR"]）写入 UDS.txt；None 表示三域都写，避免多域共用 output_dir 时覆盖。
        无返回值。
        """
        output_config_path = config_path or self.config_path
        fixed_config_backup = self.read_fixed_config()
        if not fixed_config_backup and os.path.exists(output_config_path):
            try:
                backup_config = read_config_if_exists(output_config_path)
                if backup_config.has_section(SECTION_PATHS):
                    fixed_keys = [
                        "unified_mapping_excel", "mapping_sheets", "cin_mapping_sheet",
                        "output_filename", "cin_output_filename", "xml_output_filename",
                        "didinfo_output_filename", "didconfig_output_filename",
                        "uart_output_filename", "uds_output_filename", "didinfo_variants",
                        "mapping_excel", "cin_mapping_excel",
                    ]
                    for option_name in fixed_keys:
                        if backup_config.has_option(SECTION_PATHS, option_name):
                            fixed_config_backup[option_name] = backup_config.get(
                                SECTION_PATHS, option_name
                            )
                    if fixed_config_backup:
                        self.write_fixed_config(fixed_config_backup)
            except Exception as error:
                print(f"从主配置读取固定配置时出错: {error}")

        fixed_path_option_names = [
            "unified_mapping_excel", "mapping_sheets", "cin_mapping_sheet",
            "output_filename", "cin_output_filename", "xml_output_filename",
            "didinfo_output_filename", "didconfig_output_filename",
            "uart_output_filename", "uds_output_filename", "didinfo_variants",
        ]
        dynamic_path_option_names = ["mapping_excel", "cin_mapping_excel"]
        section_names_to_ensure = [
            SECTION_LR_REAR,
            SECTION_IOMAPPING,
            SECTION_DID_CONFIG,
            SECTION_CONFIG_ENUM,
            SECTION_CENTRAL,
            SECTION_IGNITION_CYCLE,
            SECTION_DTC,
            SECTION_DTC_IOMAPPING,
            SECTION_DTC_CONFIG_ENUM,
        ]
        for section_name in section_names_to_ensure:
            if not config.has_section(section_name):
                config.add_section(section_name)

        lr_fixed_keys = [
            "input_excel",
            "input_excel_dir",
            OPTION_OUTPUT_DIR,
            *list(FILTER_OPTION_KEYS),
            OPTION_SELECTED_SHEETS,
            OPTION_LOG_LEVEL_MIN,
            OPTION_DIDINFO_INPUTS,
            OPTION_CIN_INPUT_EXCEL,
            OPTION_UDS_ECU_QUALIFIER,
        ]
        for option_name in lr_fixed_keys:
            value = self.get_config_value_with_fallback(
                config,
                SECTION_LR_REAR,
                option_name,
            )
            if option_name == OPTION_LOG_LEVEL_MIN:
                normalized_value = value.strip().lower() if value else ""
                value = normalized_value if normalized_value in VALID_LOG_LEVELS else ""
            config.set(SECTION_LR_REAR, option_name, value)

        if config.has_section(SECTION_IOMAPPING):
            for option_name in config.options(SECTION_IOMAPPING):
                if option_name.lower() != "enabled":
                    config.set(
                        SECTION_IOMAPPING,
                        option_name,
                        config.get(SECTION_IOMAPPING, option_name, fallback="") or "",
                    )

        if config.has_section(SECTION_DID_CONFIG):
            for option_name in config.options(SECTION_DID_CONFIG):
                config.set(
                    SECTION_DID_CONFIG,
                    option_name,
                    config.get(SECTION_DID_CONFIG, option_name, fallback="") or "",
                )

        if config.has_section(SECTION_CONFIG_ENUM):
            for option_name in config.options(SECTION_CONFIG_ENUM):
                if option_name.lower() != "enabled":
                    config.set(
                        SECTION_CONFIG_ENUM,
                        option_name,
                        config.get(SECTION_CONFIG_ENUM, option_name, fallback="") or "",
                    )

        central_fixed_keys = [
            "input_excel",
            "input_excel_dir",
            "uart_excel",
            "srv_excel",
            "pwr_excel",
            "rly_excel",
            OPTION_SELECTED_SHEETS,
            "uart_comm_port",
            "uart_comm_baudrate",
            "uart_comm_dataBits",
            "uart_comm_stopBits",
            "uart_comm_kHANDSHAKE_DISABLED",
            "uart_comm_parity",
            "uart_comm_frameTypeIs8676",
            "ign_waittime",
            "ign_current",
            "c_pwr",
            "c_rly",
            "c_ig",
            "c_pw",
            OPTION_OUTPUT_DIR,
            *list(FILTER_OPTION_KEYS),
            OPTION_LOG_LEVEL_MIN,
            OPTION_UDS_ECU_QUALIFIER,
            "login_username",
            "login_password",
        ]
        for option_name in central_fixed_keys:
            value = self.get_config_value_with_fallback(
                config,
                SECTION_CENTRAL,
                option_name,
            )
            if option_name == OPTION_LOG_LEVEL_MIN:
                normalized_value = value.strip().lower() if value else ""
                value = normalized_value if normalized_value in VALID_LOG_LEVELS else ""
            config.set(SECTION_CENTRAL, option_name, value)

        ignition_wait_time = ""
        if config.has_section(SECTION_IGNITION_CYCLE):
            ignition_wait_time = (
                config.get(SECTION_IGNITION_CYCLE, "waitTime", fallback="")
                or config.get(SECTION_IGNITION_CYCLE, "ign_waittime", fallback="")
                or ""
            ).strip()
        if not ignition_wait_time:
            ignition_wait_time = self.get_config_value_with_fallback(
                config,
                SECTION_CENTRAL,
                "ign_waittime",
            ).strip()
        ignition_current = ""
        if config.has_section(SECTION_IGNITION_CYCLE):
            ignition_current = (
                config.get(SECTION_IGNITION_CYCLE, "current", fallback="")
                or config.get(SECTION_IGNITION_CYCLE, "ign_current", fallback="")
                or ""
            ).strip()
        if not ignition_current:
            ignition_current = self.get_config_value_with_fallback(
                config,
                SECTION_CENTRAL,
                "ign_current",
            ).strip()
        config.set(SECTION_IGNITION_CYCLE, "waitTime", ignition_wait_time)
        config.set(SECTION_IGNITION_CYCLE, "current", ignition_current)

        dtc_fixed_keys = [
            "input_excel",
            "input_excel_dir",
            OPTION_SELECTED_SHEETS,
            OPTION_OUTPUT_DIR,
            *list(FILTER_OPTION_KEYS),
            OPTION_LOG_LEVEL_MIN,
            OPTION_DIDINFO_INPUTS,
            OPTION_CIN_INPUT_EXCEL,
            OPTION_UDS_ECU_QUALIFIER,
        ]
        for option_name in dtc_fixed_keys:
            value = self.get_config_value_with_fallback(
                config,
                SECTION_DTC,
                option_name,
            )
            if option_name == OPTION_LOG_LEVEL_MIN:
                normalized_value = value.strip().lower() if value else ""
                value = normalized_value if normalized_value in VALID_LOG_LEVELS else ""
            config.set(SECTION_DTC, option_name, value)

        if config.has_section(SECTION_DTC_IOMAPPING):
            for option_name in config.options(SECTION_DTC_IOMAPPING):
                if option_name.lower() != "enabled":
                    config.set(
                        SECTION_DTC_IOMAPPING,
                        option_name,
                        config.get(SECTION_DTC_IOMAPPING, option_name, fallback="") or "",
                    )

        config.set(
            SECTION_DTC_CONFIG_ENUM,
            OPTION_INPUTS,
            self.get_config_value_with_fallback(
                config,
                SECTION_DTC_CONFIG_ENUM,
                OPTION_INPUTS,
            ),
        )

        with open(output_config_path, "w", encoding="utf-8") as config_file:
            config.write(config_file, space_around_delimiters=True)

        if fixed_config_backup:
            current_fixed = {}
            fixed_option_names = fixed_path_option_names + dynamic_path_option_names
            for option_name in fixed_option_names:
                if option_name in fixed_config_backup:
                    current_fixed[option_name] = fixed_config_backup[option_name]
            if current_fixed:
                self.write_fixed_config(current_fixed)
        # 强制同步到磁盘，确保后续 DIDConfig 等生成器 load() 时能读到最新配置（Windows 无 os.sync，忽略）
        try:
            if hasattr(os, "sync"):
                os.sync()
        except Exception:
            pass

        # 根据最新配置生成 uds.txt（若配置了 uds_ecu_qualifier 和 output_dir）
        try:
            self.write_uds_files(config, only_domains=uds_domains)
        except Exception as error:
            print(f"根据配置生成 uds.txt 失败: {error}")
        # 中央域：生成 PowerRelayConfig.txt、IgnitionCycle.txt 到 output_dir/Configuration/
        try:
            if uds_domains is None or SECTION_CENTRAL in (uds_domains or []):
                self.write_central_config_files(config)
        except Exception as error:
            print(f"根据配置生成中央域配置文件失败: {error}")

    def get_config_value_with_fallback(
        self,
        config: configparser.ConfigParser,
        section_name: str,
        option_name: str,
    ) -> str:
        """从配置读取键值；不存在时返回空字符串。"""
        if config.has_option(section_name, option_name):
            return config.get(section_name, option_name, fallback="") or ""
        return ""

    def save_formatted_config(
        self,
        config: configparser.ConfigParser,
        config_path: Optional[str] = None,
        uds_domains: Optional[List[str]] = None,
    ) -> None:
        """公开格式化写回入口，供外部模块保存配置。"""
        self.write_formatted_config_internal(
            config,
            config_path=config_path,
            uds_domains=uds_domains,
        )
