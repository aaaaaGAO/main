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
from services.config_constants import (
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


def _clean_duplicate_sections(config_path: str) -> List[str]:
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


def _remove_invalid_config_options(config: configparser.ConfigParser) -> None:
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

    def _get_fixed_config_path(self) -> str:
        return resolve_fixed_config_path(self.base_dir)

    def _read_fixed_config(self) -> Dict[str, str]:
        return read_fixed_config(self.base_dir)

    def _write_fixed_config(self, fixed_config: Dict[str, str]) -> None:
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

    def _write_uds_files(
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
            legacy_uds_path = os.path.join(config_dir, "uds.txt")
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

    def _resolve_output_subdir(
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

        config_dir = self._resolve_output_subdir(
            output_dir,
            "Configuration",
            create_dir=create_dir,
        )
        if not config_dir:
            return ""

        fixed = self._read_fixed_config()
        uds_filename = (fixed.get("uds_output_filename") or "uds.txt").strip() or "uds.txt"
        return os.path.join(config_dir, uds_filename)

    def _get_central_config_dir(self, config: configparser.ConfigParser) -> Optional[str]:
        """获取中央域 output_dir 下的 Configuration 目录。"""
        if not config.has_section(SECTION_CENTRAL):
            return None
        output_dir = (config.get(SECTION_CENTRAL, OPTION_OUTPUT_DIR, fallback="") or "").strip()
        if not output_dir:
            return None
        return self._resolve_output_subdir(output_dir, "Configuration", create_dir=True)

    @staticmethod
    def _extract_port_number(port_str: str) -> str:
        """从端口号中提取数字（如 COM3 -> 3）。"""
        if not port_str:
            return ""
        port_str = str(port_str).strip()
        match = re.match(r"^COM(\d+)$", port_str, re.IGNORECASE)
        if match:
            return match.group(1)
        if port_str.isdigit():
            return port_str
        digits = re.findall(r"\d+", port_str)
        return digits[0] if digits else port_str

    @staticmethod
    def _parse_json_config_option(
        config: configparser.ConfigParser,
        section: str,
        option_name: str,
        default: Any,
    ) -> Any:
        """读取并解析指定配置项中的 JSON；缺失、空值或解析失败时返回默认值。"""
        if not config.has_option(section, option_name):
            return default
        raw = config.get(section, option_name, fallback="").strip()
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    @staticmethod
    def _parse_json_value(raw: Any, default: Any) -> Any:
        """解析字符串形式的 JSON 值；空值或解析失败时返回默认值。"""
        raw_text = str(raw or "").strip()
        if not raw_text:
            return default
        try:
            return json.loads(raw_text)
        except Exception:
            return default

    @staticmethod
    def _has_relay_config(relay: Any) -> bool:
        """判断单个继电器是否算已配置：须填写串口 port 或 relayID。

        仅含 relayType / 默认 coilStatuses（UI 渲染时自动补全）不算，否则用户未选串口
        或 ini 中残留骨架仍会触发生成 PowerRelayConfig.txt。
        """
        if not isinstance(relay, dict):
            return False
        port = str(relay.get("port") or "").strip()
        if port:
            return True
        relay_id = relay.get("relayID")
        if relay_id is not None and str(relay_id).strip() != "":
            return True
        return False

    @classmethod
    def _has_power_relay_config(
        cls,
        power_config: Any,
        relay_configs: Any,
        ig_config: Any,
        pw_config: Any,
    ) -> bool:
        """判断是否配置了任一程控电源/继电器/IG/PW 项。"""
        if isinstance(power_config, dict) and str(power_config.get("port") or "").strip():
            return True
        if isinstance(relay_configs, list):
            for relay in relay_configs:
                if cls._has_relay_config(relay):
                    return True
        if isinstance(ig_config, dict) and str(ig_config.get("equipmentType") or "").strip():
            return True
        if isinstance(pw_config, dict) and str(pw_config.get("equipmentType") or "").strip():
            return True
        return False

    @staticmethod
    def _write_config_lines(file_obj: Any, lines: List[str]) -> None:
        for line in lines:
            file_obj.write(f"{line}\n")

    def _write_power_block(self, file_obj: Any, power_config: Any) -> None:
        power = power_config if (power_config and power_config.get("port")) else {}
        port_val = self._extract_port_number(power.get("port", "")) if power.get("port") else "0"
        lines: List[str] = ["[Power]//电源", f"port={port_val}//端口号"]
        baud = str(power.get("baudrate") or "").strip()
        if baud:
            lines.append(f"baudrate={baud}//波特率")
        # UI 已隐藏以下项，不再写入 PowerRelayConfig.txt（保留原条件写入代码便于恢复）
        # data_bits = str(power.get("dataBits") or "").strip()
        # if data_bits:
        #     lines.append(f"dataBits={data_bits}//数据位")
        # stop_bits = str(power.get("stopBits") or "").strip()
        # if stop_bits:
        #     lines.append(f"stopBits={stop_bits}//停止位")
        # handshake = str(power.get("kHANDSHAKE_DISABLED") or "").strip()
        # if handshake:
        #     lines.append(f"kHANDSHAKE_DISABLED={handshake}//握手")
        # parity = str(power.get("parity") or "").strip()
        # if parity:
        #     lines.append(f"parity={parity}//校验")
        channel = str(power.get("channel") or "").strip()
        if channel:
            lines.append(f"channel={channel}//电源通道")
        lines.append("")
        self._write_config_lines(file_obj, lines)

    def _write_relay_blocks(self, file_obj: Any, relay_configs: Any) -> None:
        if not relay_configs:
            return
        for idx, relay in enumerate(relay_configs, 1):
            if not self._has_relay_config(relay):
                continue
            lines = [f"[Relay{idx}]//继电器"]
            if relay.get("port"):
                lines.append(f"port={self._extract_port_number(relay.get('port', ''))}//端口号")
            baud = str(relay.get("baudrate") or "").strip()
            if baud:
                lines.append(f"baudrate={baud}//波特率")
            # UI 已隐藏以下项，不再写入 PowerRelayConfig.txt（保留原条件写入代码便于恢复）
            # data_bits = str(relay.get("dataBits") or "").strip()
            # if data_bits:
            #     lines.append(f"dataBits={data_bits}//数据位")
            # stop_bits = str(relay.get("stopBits") or "").strip()
            # if stop_bits:
            #     lines.append(f"stopBits={stop_bits}//停止位")
            # handshake = str(relay.get("kHANDSHAKE_DISABLED") or "").strip()
            # if handshake:
            #     lines.append(f"kHANDSHAKE_DISABLED={handshake}//握手")
            # parity = str(relay.get("parity") or "").strip()
            # if parity:
            #     lines.append(f"parity={parity}//校验")
            # relay_id = str(relay.get("relayID") or "").strip()
            # if relay_id:
            #     lines.append(f"relayID={relay_id}//继电器设备地址")
            relay_type = str(relay.get("relayType") or "").strip()
            if relay_type:
                lines.append(f"RelayType={relay_type}")
            for coil_idx, status in enumerate(relay.get("coilStatuses", []), 1):
                lines.append(f"RelayCoil{coil_idx}Status={status}")
            lines.append("")
            self._write_config_lines(file_obj, lines)

    def _write_equipment_block(
        self,
        file_obj: Any,
        *,
        title: str,
        config_data: Any,
        default_values: Dict[str, str],
        include_init_comment: bool = False,
    ) -> None:
        data = config_data if (config_data and config_data.get("equipmentType")) else {}
        lines = [
            f"[{title}]",
            "//Equipment_Type设备类型：Power/Relay",
            "//ChannelNumber如果类型是Power,此含义是电源通道号，如果类型是Relay,此含义是线圈号",
        ]
        if include_init_comment:
            lines.append("//initStatus初始状态，如果设备类型是Power:1代表上电，0代表下电，如果类型是Relay:17代表常开，18代表常关")
        lines.extend(
            [
                "//eqPosition设备位置",
                f"Equipment_Type={data.get('equipmentType', default_values['equipmentType'])}",
                f"ChannelNumber={data.get('channelNumber', default_values['channelNumber'])}",
                f"initStatus={data.get('initStatus', default_values['initStatus'])}",
                f"eqPosition={data.get('eqPosition', default_values['eqPosition'])}",
                "",
            ]
        )
        self._write_config_lines(file_obj, lines)

    def _load_central_ui_json_fields(self, out: Dict[str, Any], section_data: Dict[str, Any]) -> None:
        power = self._parse_json_value(section_data.get("c_pwr", ""), {})
        if isinstance(power, dict) and (power.get("port") or "").strip():
            out["c_pwr"] = power

        relays = self._parse_json_value(section_data.get("c_rly", ""), [])
        if isinstance(relays, list) and any(self._has_relay_config(relay) for relay in relays):
            out["c_rly"] = relays

        for option_name in ("c_ig", "c_pw"):
            equipment_config = self._parse_json_value(section_data.get(option_name, ""), {})
            if (
                equipment_config
                and isinstance(equipment_config, dict)
                and (
                    equipment_config.get("equipmentType")
                    or equipment_config.get("channelNumber")
                )
            ):
                out[option_name] = equipment_config

    def _write_central_config_files(self, config: configparser.ConfigParser) -> None:
        """
        根据 [CENTRAL] 的 c_pwr/c_rly/c_ig/c_pw/ign_waittime/ign_current 生成：
        - PowerRelayConfig.txt：程控电源 [Power]、继电器 [RelayN]、[IG]、[PW]
        - IgnitionCycle.txt：点火循环 [IgnitionCycle] waitTime/current
        写入中央域 output_dir 下的 Configuration 目录（与 UDS 同规则）。
        """
        config_dir = self._get_central_config_dir(config)
        if not config_dir:
            return
        try:
            os.makedirs(config_dir, exist_ok=True)
        except Exception:
            return

        power_config = self._parse_json_config_option(config, SECTION_CENTRAL, "c_pwr", {})
        relay_configs = self._parse_json_config_option(config, SECTION_CENTRAL, "c_rly", [])
        ig_config = self._parse_json_config_option(config, SECTION_CENTRAL, "c_ig", {})
        pw_config = self._parse_json_config_option(config, SECTION_CENTRAL, "c_pw", {})
        # 点火循环：与副本一致，优先从 [IgnitionCycle] 读，再回退到 [CENTRAL]
        ign_waittime = ""
        ign_current = ""
        if config.has_section(SECTION_IGNITION_CYCLE):
            ign_waittime = (config.get(SECTION_IGNITION_CYCLE, "waitTime", fallback="") or "").strip()
            ign_current = (config.get(SECTION_IGNITION_CYCLE, "current", fallback="") or "").strip()
        if (not ign_waittime and not ign_current) and config.has_section(SECTION_CENTRAL):
            ign_waittime = (config.get(SECTION_CENTRAL, "ign_waittime", fallback="") or "").strip()
            ign_current = (config.get(SECTION_CENTRAL, "ign_current", fallback="") or "").strip()

        # 仅当用户实际配置了程控电源/继电器/IG/PW 之一时才生成 PowerRelayConfig.txt；未配置则不生成并删除已有文件
        power_path = os.path.join(config_dir, "PowerRelayConfig.txt")
        if not self._has_power_relay_config(power_config, relay_configs, ig_config, pw_config):
            if os.path.exists(power_path):
                try:
                    os.remove(power_path)
                except Exception as error:
                    print(f"移除未配置的 PowerRelayConfig.txt 失败: {error}")
        else:
            try:
                with open(power_path, "w", encoding="utf-8") as power_file:
                    # 仅输出用户实际填过的块，避免「只配了继电器」却带上 port=0 的 [Power] 或默认 [IG]/[PW]
                    if isinstance(power_config, dict) and str(
                        power_config.get("port") or ""
                    ).strip():
                        self._write_power_block(power_file, power_config)
                    self._write_relay_blocks(power_file, relay_configs)
                    if isinstance(ig_config, dict) and str(
                        ig_config.get("equipmentType") or ""
                    ).strip():
                        self._write_equipment_block(
                            power_file,
                            title="IG",
                            config_data=ig_config,
                            default_values={
                                "equipmentType": "Power",
                                "channelNumber": "1",
                                "initStatus": "1",
                                "eqPosition": "1",
                            },
                            include_init_comment=True,
                        )
                    if isinstance(pw_config, dict) and str(
                        pw_config.get("equipmentType") or ""
                    ).strip():
                        self._write_equipment_block(
                            power_file,
                            title="PW",
                            config_data=pw_config,
                            default_values={
                                "equipmentType": "Relay",
                                "channelNumber": "1",
                                "initStatus": "17",
                                "eqPosition": "1",
                            },
                        )
            except Exception as error:
                print(f"生成 PowerRelayConfig.txt 失败: {error}")

        # 仅当用户实际配置了点火循环（waitTime/current 有值）时才生成 IgnitionCycle.txt；未配置则不生成并删除已有文件
        ign_path = os.path.join(config_dir, "IgnitionCycle.txt")
        if not (ign_waittime or ign_current):
            if os.path.exists(ign_path):
                try:
                    os.remove(ign_path)
                except Exception as error:
                    print(f"移除未配置的 IgnitionCycle.txt 失败: {error}")
        else:
            try:
                with open(ign_path, "w", encoding="utf-8") as ignition_file:
                    ignition_file.write("[IgnitionCycle]\n")
                    if ign_waittime:
                        ignition_file.write(f"waitTime={ign_waittime}\n")
                    if ign_current:
                        ignition_file.write(f"current={ign_current}\n")
            except Exception as error:
                print(f"生成 IgnitionCycle.txt 失败: {error}")

        # 运行账号：生成 login.txt，有账号密码则写入，无则仅写 [login]
        login_username = (config.get(SECTION_CENTRAL, "login_username", fallback="") or "").strip()
        login_password = (config.get(SECTION_CENTRAL, "login_password", fallback="") or "").strip()
        login_path = os.path.join(config_dir, "login.txt")
        try:
            with open(login_path, "w", encoding="utf-8") as login_file:
                login_file.write("[login]\n")
                if login_username or login_password:
                    login_file.write(f"username={login_username}\n")
                    login_file.write(f"password={login_password}\n")
        except Exception as error:
            print(f"生成 login.txt 失败: {error}")

    def _init_fixed_config_from_main_config(self) -> None:
        if os.path.exists(self._get_fixed_config_path()) or not os.path.exists(self._main_config_read_path):
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
                self._write_fixed_config(fixed_config_values)
        except Exception as error:
            print(f"从主配置初始化固定配置失败: {error}")

    def _reload(self) -> configparser.ConfigParser:
        """读入配置并做去重后写回，再解析返回 ConfigParser。"""
        with self._lock:
            cleaned = _clean_duplicate_sections(self._main_config_read_path)
            if cleaned:
                with open(self._main_config_read_path, "w", encoding="utf-8") as config_file:
                    config_file.writelines(cleaned)
            return read_config_if_exists(self._main_config_read_path)

    def load_config(self) -> configparser.ConfigParser:
        """公开配置读取入口，供外部模块获取最新配置。"""
        return self._reload()

    @staticmethod
    def _ui_state_key(prefix: str, option_name: str) -> str:
        return f"{prefix}_{option_name}" if prefix else option_name

    @classmethod
    def _load_standard_domain_ui_fields(
        cls,
        out: Dict[str, Any],
        section_data: Dict[str, Any],
        *,
        prefix: str,
        include_didinfo: bool = False,
        include_cin: bool = False,
        include_uds: bool = True,
    ) -> None:
        out[cls._ui_state_key(prefix, "input")] = section_data.get(OPTION_INPUT_EXCEL, "")
        out[cls._ui_state_key(prefix, "out_root")] = section_data.get(OPTION_OUTPUT_DIR, "")
        out[cls._ui_state_key(prefix, "levels")] = section_data.get(OPTION_CASE_LEVELS, "ALL")
        out[cls._ui_state_key(prefix, "platforms")] = section_data.get("case_platforms", "")
        out[cls._ui_state_key(prefix, "models")] = section_data.get("case_models", "")
        out[cls._ui_state_key(prefix, "target_versions")] = section_data.get("case_target_versions", "")
        out[cls._ui_state_key(prefix, "selected_sheets")] = section_data.get(OPTION_SELECTED_SHEETS, "")
        out[cls._ui_state_key(prefix, "log_level")] = section_data.get(OPTION_LOG_LEVEL_MIN, "info")
        if include_uds:
            out[cls._ui_state_key(prefix, "uds_ecu_qualifier")] = section_data.get(
                OPTION_UDS_ECU_QUALIFIER,
                "",
            )
        if include_didinfo:
            didinfo_raw = section_data.get(OPTION_DIDINFO_INPUTS, "")
            out[cls._ui_state_key(prefix, "didinfo_excel")] = didinfo_raw.split(" | ")[0] if didinfo_raw else ""
        if include_cin:
            out[cls._ui_state_key(prefix, "cin_excel")] = section_data.get(OPTION_CIN_INPUT_EXCEL, "")

    @staticmethod
    def _append_option_line(
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
    def _append_options_if_present(
        cls,
        lines: List[str],
        config: configparser.ConfigParser,
        section: str,
        options: List[str],
    ) -> bool:
        appended_any_option = False
        for option_name in options:
            appended_any_option = (
                cls._append_option_line(lines, config, section, option_name)
                or appended_any_option
            )
        return appended_any_option

    @classmethod
    def _append_filter_options(
        cls,
        lines: List[str],
        config: configparser.ConfigParser,
        section: str,
    ) -> bool:
        return cls._append_options_if_present(lines, config, section, list(FILTER_OPTION_KEYS))

    @staticmethod
    def _append_valid_log_level(
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
    def _append_nonempty_option(
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
        config = self._reload()
        out: Dict[str, Any] = {}

        # 1. LR_REAR -> 左右后域基础配置
        if config.has_section(SECTION_LR_REAR):
            lr_section = dict(config.items(SECTION_LR_REAR))
            self._load_standard_domain_ui_fields(
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
            self._load_standard_domain_ui_fields(out, central_section, prefix="c")
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
            self._load_central_ui_json_fields(out, central_section)
            out["c_login_username"] = central_section.get("login_username", "")
            out["c_login_password"] = central_section.get("login_password", "")

        # 4. DTC -> d_* 字段
        if config.has_section(SECTION_DTC):
            dtc_section = dict(config.items(SECTION_DTC))
            self._load_standard_domain_ui_fields(
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
            config = self._reload()
            if not config.has_section(domain):
                config.add_section(domain)
            for option_name, option_value in data.items():
                config.set(domain, option_name, str(option_value) if option_value is not None else "")
            self.save_formatted_config(config)

    def save_formatted(self) -> None:
        """重新加载配置、移除无效项、按固定格式写回。"""
        with self._lock:
            config = self._reload()
            _remove_invalid_config_options(config)
            self._init_fixed_config_from_main_config()
            self.save_formatted_config(config)

    @staticmethod
    def _is_relay_list_effectively_empty(relay_list_value: Any) -> bool:
        """判断继电器列表是否为“有效空”：空列表，或所有项均未构成有效继电器配置（与 _has_relay_config 对齐，避免仅靠 relayID 判定）。"""
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
            if ConfigManager._has_relay_config(item):
                return False
        return True

    @classmethod
    def _is_effectively_empty_value(cls, option: str, value: Any) -> bool:
        if value in (None, "", [], {}):
            return True
        return option == "c_rly" and cls._is_relay_list_effectively_empty(value)

    def _remove_central_managed_options(
        self,
        config: configparser.ConfigParser,
        section: str,
        section_values: Dict[str, Any],
        managed_keys: List[str],
    ) -> None:
        for managed_key in managed_keys:
            value = section_values.get(managed_key)
            if managed_key not in section_values or self._is_effectively_empty_value(managed_key, value):
                if config.has_option(section, managed_key):
                    config.remove_option(section, managed_key)

    def _write_section_values(
        self,
        config: configparser.ConfigParser,
        section: str,
        section_values: Dict[str, Any],
    ) -> None:
        for option_name, option_value in section_values.items():
            normalized_option_name = str(option_name)
            if self._is_effectively_empty_value(normalized_option_name, option_value):
                if config.has_option(section, normalized_option_name):
                    config.remove_option(section, normalized_option_name)
            else:
                config.set(section, normalized_option_name, str(option_value))

    def save_ui_data(self, data: Dict[str, Dict[str, Any]]) -> None:
        """将前端按节提交的 data 写回主配置并格式化写回文件。
        增强点：
        - 对 CENTRAL 段的 UI 托管键（如 c_pwr/c_rly/c_ig/c_pw/ign_*/login_*/uart_comm_*）做“缺失即删”的处理，
          防止增量更新导致旧值残留。
        - 继电器 c_rly 为列表：空列表或所有项均未填 port/relayID 时视为“有效空”，从配置中删除，避免骨架残留。
        - 对所有节的键，若值为 None / 空串 / 空列表 / 空字典，则优先执行 remove_option 而不是写入空字符串。
        参数:
            data: 节名为键、值为「选项名->值」字典，如 {"LR_REAR": {"input_excel": "..."}, ...}。
        无返回值。
        """
        with self._lock:
            config = self._reload()

            # 本次前端实际提交更新的节名列表，用于后续精确控制 UDS/中央域附属文件的生成范围
            updated_sections: List[str] = list(data.keys())

            # 中央域由前端 UI 统一托管的配置键：当前端未提供或提供的是“空值/有效空”时，应主动从配置文件中移除
            central_managed_keys = CENTRAL_MANAGED_KEYS

            for section, section_values in data.items():
                if not config.has_section(section):
                    config.add_section(section)

                # 1) CENTRAL 段：先对托管键做“缺失/空值/有效空即删除”的处理
                if section == SECTION_CENTRAL:
                    self._remove_central_managed_options(
                        config,
                        section,
                        section_values,
                        central_managed_keys,
                    )

                # 2) 通用写入逻辑：有值则 set，空值则删；继电器列表为“有效空”时也按删除处理，避免脏数据回流
                self._write_section_values(config, section, section_values)

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
            config = self._reload()
            _remove_invalid_config_options(config)
            self.save_formatted_config(config, config_path=output_config_path)

    def _write_formatted_config(
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
        fixed_config_backup = self._read_fixed_config()
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
                        self._write_fixed_config(fixed_config_backup)
            except Exception as error:
                print(f"从主配置读取固定配置时出错: {error}")

        fixed_path_option_names = [
            "unified_mapping_excel", "mapping_sheets", "cin_mapping_sheet",
            "output_filename", "cin_output_filename", "xml_output_filename",
            "didinfo_output_filename", "didconfig_output_filename",
            "uart_output_filename", "uds_output_filename", "didinfo_variants",
        ]
        dynamic_path_option_names = ["mapping_excel", "cin_mapping_excel"]

        lines: List[str] = []

        lines.append("# ============================================================\n")
        lines.append("# 左右后域配置\n")
        lines.append("# ============================================================\n")
        lines.append(f"[{SECTION_LR_REAR}]\n")
        written_lr_options = set()
        if config.has_section(SECTION_LR_REAR):
            for option_name in ["input_excel", "input_excel_dir"]:
                if config.has_option(SECTION_LR_REAR, option_name):
                    lines.append(
                        f"{option_name} = {config.get(SECTION_LR_REAR, option_name) or ''}\n"
                    )
                    written_lr_options.add(option_name.lower())
            lines.append("\n")
            if self._append_option_line(lines, config, SECTION_LR_REAR, OPTION_OUTPUT_DIR):
                written_lr_options.add(OPTION_OUTPUT_DIR)
            lines.append("\n")
            for option_name in FILTER_OPTION_KEYS:
                if config.has_option(SECTION_LR_REAR, option_name):
                    lines.append(
                        f"{option_name} = {config.get(SECTION_LR_REAR, option_name) or ''}\n"
                    )
                    written_lr_options.add(option_name.lower())
            lines.append("\n")
            if config.has_option(SECTION_LR_REAR, OPTION_SELECTED_SHEETS):
                lines.append("# 勾选的工作表\n")
                lines.append(f"{OPTION_SELECTED_SHEETS} = {config.get(SECTION_LR_REAR, OPTION_SELECTED_SHEETS, fallback='') or ''}\n")
                written_lr_options.add(OPTION_SELECTED_SHEETS)
                lines.append("\n")
            if self._append_valid_log_level(lines, config, SECTION_LR_REAR):
                written_lr_options.add(OPTION_LOG_LEVEL_MIN)
                lines.append("\n")
            if self._append_option_line(lines, config, SECTION_LR_REAR, OPTION_DIDINFO_INPUTS):
                written_lr_options.add(OPTION_DIDINFO_INPUTS)
            if self._append_option_line(lines, config, SECTION_LR_REAR, OPTION_CIN_INPUT_EXCEL):
                written_lr_options.add(OPTION_CIN_INPUT_EXCEL)

        if config.has_section(SECTION_IOMAPPING):
            lines.append(f"[{SECTION_IOMAPPING}]\n")
            for option_name in config.options(SECTION_IOMAPPING):
                if option_name.lower() != "enabled":
                    lines.append(
                        f"{option_name} = {config.get(SECTION_IOMAPPING, option_name) or ''}\n"
                    )
            lines.append("\n")
        if config.has_section(SECTION_DID_CONFIG):
            lines.append(f"[{SECTION_DID_CONFIG}]\n")
            for option_name in config.options(SECTION_DID_CONFIG):
                lines.append(
                    f"{option_name} = {config.get(SECTION_DID_CONFIG, option_name) or ''}\n"
                )
            lines.append("\n")
        if config.has_section(SECTION_CONFIG_ENUM):
            lines.append(f"[{SECTION_CONFIG_ENUM}]\n")
            for option_name in config.options(SECTION_CONFIG_ENUM):
                if option_name.lower() != "enabled":
                    lines.append(
                        f"{option_name} = {config.get(SECTION_CONFIG_ENUM, option_name) or ''}\n"
                    )
            lines.append("\n")

        lines.append("# ============================================================\n")
        lines.append("# 中央域配置\n")
        lines.append("# ============================================================\n")
        lines.append(f"[{SECTION_CENTRAL}]\n")
        if config.has_section(SECTION_CENTRAL):
            # 基础与表格
            self._append_options_if_present(lines, config, SECTION_CENTRAL, [
                "input_excel",
                "input_excel_dir",
                "uart_excel",
                "srv_excel",
                "pwr_excel",
                "rly_excel",
                "selected_sheets",
            ])
            # 串口通信配置
            uart_option_names = [
                "uart_comm_port",
                "uart_comm_baudrate",
                "uart_comm_dataBits",
                "uart_comm_stopBits",
                "uart_comm_kHANDSHAKE_DISABLED",
                "uart_comm_parity",
                "uart_comm_frameTypeIs8676",
            ]
            if any(config.has_option(SECTION_CENTRAL, option_name) for option_name in uart_option_names):
                lines.append("\n# 串口通信配置\n")
                self._append_options_if_present(lines, config, SECTION_CENTRAL, uart_option_names)
            # 点火循环（中央域，兼容从 CENTRAL 读取）
            if config.has_option(SECTION_CENTRAL, "ign_waittime") or config.has_option(SECTION_CENTRAL, "ign_current"):
                lines.append("\n# 点火循环配置（中央域，兼容从本段读取）\n")
                self._append_options_if_present(lines, config, SECTION_CENTRAL, ["ign_waittime", "ign_current"])
            # 程控电源/继电器/IG/PW：与点火循环一致，仅当配置中有该选项时才写入，避免写空覆盖
            if config.has_option(SECTION_CENTRAL, "c_pwr"):
                lines.append("\n# 程控电源配置（c_pwr）\n")
                self._append_option_line(lines, config, SECTION_CENTRAL, "c_pwr")
            if config.has_option(SECTION_CENTRAL, "c_rly"):
                lines.append("\n# 继电器配置（c_rly）\n")
                self._append_option_line(lines, config, SECTION_CENTRAL, "c_rly")
            if config.has_option(SECTION_CENTRAL, "c_ig"):
                lines.append("\n# IG 配置（点火装置）\n")
                self._append_option_line(lines, config, SECTION_CENTRAL, "c_ig")
            if config.has_option(SECTION_CENTRAL, "c_pw"):
                lines.append("\n# PW 配置（程控电源/继电器装置）\n")
                self._append_option_line(lines, config, SECTION_CENTRAL, "c_pw")
            lines.append("\n")
            self._append_option_line(lines, config, SECTION_CENTRAL, OPTION_OUTPUT_DIR)
            lines.append("\n")
            self._append_filter_options(lines, config, SECTION_CENTRAL)
            self._append_valid_log_level(lines, config, SECTION_CENTRAL)
            self._append_nonempty_option(lines, config, SECTION_CENTRAL, OPTION_UDS_ECU_QUALIFIER)
            # 运行账号（中央域，写入 Configuration/login.txt）
            if config.has_option(SECTION_CENTRAL, "login_username") or config.has_option(SECTION_CENTRAL, "login_password"):
                lines.append("\n# 运行账号（生成至 output_dir/Configuration/login.txt）\n")
                self._append_options_if_present(lines, config, SECTION_CENTRAL, ["login_username", "login_password"])

        # 点火循环配置（中央域相关，写在 [CENTRAL] 之后）
        if config.has_section(SECTION_IGNITION_CYCLE) or config.has_section(SECTION_CENTRAL):
            # 兼容老配置中 [IgnitionCycle] 里使用 ign_waittime/ign_current 的写法
            ignition_wait_time = ""
            if config.has_section(SECTION_IGNITION_CYCLE):
                ignition_wait_time = (
                    config.get(SECTION_IGNITION_CYCLE, "waitTime", fallback="")
                    or config.get(SECTION_IGNITION_CYCLE, "ign_waittime", fallback="")
                    or ""
                ).strip()
            if not ignition_wait_time and config.has_section(SECTION_CENTRAL):
                ignition_wait_time = (
                    config.get(SECTION_CENTRAL, "ign_waittime", fallback="") or ""
                ).strip()

            ignition_current = ""
            if config.has_section(SECTION_IGNITION_CYCLE):
                ignition_current = (
                    config.get(SECTION_IGNITION_CYCLE, "current", fallback="")
                    or config.get(SECTION_IGNITION_CYCLE, "ign_current", fallback="")
                    or ""
                ).strip()
            if not ignition_current and config.has_section(SECTION_CENTRAL):
                ignition_current = (
                    config.get(SECTION_CENTRAL, "ign_current", fallback="") or ""
                ).strip()

            # 只要原文件里存在 [IgnitionCycle]，即使值为空也不要把整个节删掉
            if ignition_wait_time or ignition_current or config.has_section(SECTION_IGNITION_CYCLE):
                lines.append(f"\n[{SECTION_IGNITION_CYCLE}]\n")
                lines.append(f"waitTime = {ignition_wait_time}\n")
                lines.append(f"current = {ignition_current}\n")

        lines.append("\n# ============================================================\n")
        lines.append("# DTC配置\n")
        lines.append("# ============================================================\n")
        lines.append(f"[{SECTION_DTC}]\n")
        if config.has_section(SECTION_DTC):
            self._append_options_if_present(lines, config, SECTION_DTC, ["input_excel", "input_excel_dir"])
            self._append_option_line(lines, config, SECTION_DTC, OPTION_SELECTED_SHEETS)
            lines.append("\n")
            self._append_option_line(lines, config, SECTION_DTC, OPTION_OUTPUT_DIR)
            lines.append("\n")
            self._append_filter_options(lines, config, SECTION_DTC)
            self._append_valid_log_level(lines, config, SECTION_DTC)
            self._append_option_line(lines, config, SECTION_DTC, OPTION_DIDINFO_INPUTS)
            self._append_option_line(lines, config, SECTION_DTC, OPTION_CIN_INPUT_EXCEL)
            self._append_nonempty_option(lines, config, SECTION_DTC, OPTION_UDS_ECU_QUALIFIER)

        if config.has_section(SECTION_DTC_IOMAPPING):
            lines.append(f"\n[{SECTION_DTC_IOMAPPING}]\n")
            for option_name in config.options(SECTION_DTC_IOMAPPING):
                if option_name.lower() != "enabled":
                    lines.append(
                        f"{option_name} = {config.get(SECTION_DTC_IOMAPPING, option_name) or ''}\n"
                    )
        # [DTC_CONFIG_ENUM] 仅保留 inputs（DID 配置表路径），等级/平台/车型/日志/UDS 等由 [DTC] 统一提供，此处不写入
        if config.has_section(SECTION_DTC_CONFIG_ENUM):
            lines.append(f"\n[{SECTION_DTC_CONFIG_ENUM}]\n")
            if config.has_option(SECTION_DTC_CONFIG_ENUM, OPTION_INPUTS):
                lines.append(f"{OPTION_INPUTS} = {config.get(SECTION_DTC_CONFIG_ENUM, OPTION_INPUTS) or ''}\n")

        if fixed_config_backup:
            current_fixed = {}
            fixed_option_names = fixed_path_option_names + dynamic_path_option_names
            for option_name in fixed_option_names:
                if option_name in fixed_config_backup:
                    current_fixed[option_name] = fixed_config_backup[option_name]
            if current_fixed:
                self._write_fixed_config(current_fixed)

        if not lines:
            lines = [
                "# ============================================================\n",
                "# 左右后域配置\n",
                "# ============================================================\n",
                f"[{SECTION_LR_REAR}]\n",
                "\n",
            ]

        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned_lines.append(line if line.endswith("\n") else line + "\n")
                continue
            if stripped.startswith("#"):
                cleaned_lines.append(line if line.endswith("\n") else line + "\n")
                continue
            if stripped.startswith(","):
                continue
            if "=" in stripped:
                parts = stripped.split("=", 1)
                option_name = parts[0].strip()
                if not option_name or option_name.startswith(","):
                    continue
                cleaned_lines.append(line if line.endswith("\n") else line + "\n")
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                cleaned_lines.append(line if line.endswith("\n") else line + "\n")
                continue
            # 其他无效行跳过
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()

        with open(output_config_path, "w", encoding="utf-8") as config_file:
            config_file.writelines(cleaned_lines)
        # 强制同步到磁盘，确保后续 DIDConfig 等生成器 load() 时能读到最新配置（Windows 无 os.sync，忽略）
        try:
            if hasattr(os, "sync"):
                os.sync()
        except Exception:
            pass

        # 根据最新配置生成 uds.txt（若配置了 uds_ecu_qualifier 和 output_dir）
        try:
            self._write_uds_files(config, only_domains=uds_domains)
        except Exception as error:
            print(f"根据配置生成 uds.txt 失败: {error}")
        # 中央域：生成 PowerRelayConfig.txt、IgnitionCycle.txt 到 output_dir/Configuration/
        try:
            if uds_domains is None or SECTION_CENTRAL in (uds_domains or []):
                self._write_central_config_files(config)
        except Exception as error:
            print(f"根据配置生成中央域配置文件失败: {error}")

    def save_formatted_config(
        self,
        config: configparser.ConfigParser,
        config_path: Optional[str] = None,
        uds_domains: Optional[List[str]] = None,
    ) -> None:
        """公开格式化写回入口，供外部模块保存配置。"""
        self._write_formatted_config(
            config,
            config_path=config_path,
            uds_domains=uds_domains,
        )
