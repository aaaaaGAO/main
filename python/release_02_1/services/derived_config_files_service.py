#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中央域派生配置文件生成服务。

职责：根据 Configuration.ini 中 [CENTRAL]/[IgnitionCycle] 的值，
生成或清理 output_dir/Configuration 下的派生文件：
- PowerRelayConfig.txt
- IgnitionCycle.txt
- login.txt
"""

from __future__ import annotations

import configparser
import json
import os
import re
from typing import Any, Dict, List, Optional

from infra.filesystem import resolve_named_subdir
from services.config_constants import OPTION_OUTPUT_DIR, SECTION_CENTRAL, SECTION_IGNITION_CYCLE
from services.config_constants import (
    DEFAULT_IGNITION_CYCLE_FILENAME,
    DEFAULT_LOGIN_FILENAME,
    DEFAULT_POWER_RELAY_CONFIG_FILENAME,
)


class DerivedConfigFilesService:
    """中央域派生文件写入服务。"""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = os.path.abspath(base_dir)

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

    def get_central_config_dir(self, config: configparser.ConfigParser) -> Optional[str]:
        if not config.has_section(SECTION_CENTRAL):
            return None
        output_dir = (config.get(SECTION_CENTRAL, OPTION_OUTPUT_DIR, fallback="") or "").strip()
        if not output_dir:
            return None
        return self.resolve_output_subdir(output_dir, "Configuration", create_dir=True)

    @staticmethod
    def extract_port_number(port_text: str) -> str:
        if not port_text:
            return ""
        normalized_port = str(port_text).strip()
        match = re.match(r"^COM(\d+)$", normalized_port, re.IGNORECASE)
        if match:
            return match.group(1)
        if normalized_port.isdigit():
            return normalized_port
        digits = re.findall(r"\d+", normalized_port)
        return digits[0] if digits else normalized_port

    @staticmethod
    def parse_json_config_option(
        config: configparser.ConfigParser,
        section: str,
        option_name: str,
        default_value: Any,
    ) -> Any:
        if not config.has_option(section, option_name):
            return default_value
        raw = config.get(section, option_name, fallback="").strip()
        if not raw:
            return default_value
        try:
            return json.loads(raw)
        except Exception:
            return default_value

    @staticmethod
    def has_relay_config(relay_config: Any) -> bool:
        if not isinstance(relay_config, dict):
            return False
        port = str(relay_config.get("port") or "").strip()
        if port:
            return True
        relay_id = relay_config.get("relayID")
        if relay_id is None:
            relay_id = relay_config.get("id")
        if relay_id is not None and str(relay_id).strip() != "":
            return True
        return False

    @classmethod
    def has_power_relay_config(
        cls,
        power_config: Any,
        relay_configs: Any,
        ig_config: Any,
        pw_config: Any,
    ) -> bool:
        if isinstance(power_config, dict) and str(power_config.get("port") or "").strip():
            return True
        if isinstance(relay_configs, list):
            for relay in relay_configs:
                if cls.has_relay_config(relay):
                    return True
        if isinstance(ig_config, dict) and str(ig_config.get("equipmentType") or "").strip():
            return True
        if isinstance(pw_config, dict) and str(pw_config.get("equipmentType") or "").strip():
            return True
        return False

    @staticmethod
    def write_config_lines(file_obj: Any, lines: List[str]) -> None:
        for line in lines:
            file_obj.write(f"{line}\n")

    def write_power_block(self, file_obj: Any, power_config: Any) -> None:
        power = power_config if (power_config and power_config.get("port")) else {}
        port_value = self.extract_port_number(power.get("port", "")) if power.get("port") else "0"
        lines: List[str] = ["[Power]//电源", f"port={port_value}//端口号"]
        baud = str(power.get("baudrate") or "").strip()
        if baud:
            lines.append(f"baudrate={baud}//波特率")
        channel = str(power.get("channel") or "").strip()
        if channel:
            lines.append(f"channel={channel}//电源通道")
        lines.append("")
        self.write_config_lines(file_obj, lines)

    def write_relay_blocks(self, file_obj: Any, relay_configs: Any) -> None:
        if not relay_configs:
            return
        for relay_index, relay in enumerate(relay_configs, 1):
            if not self.has_relay_config(relay):
                continue
            lines = [f"[Relay{relay_index}]//继电器"]
            if relay.get("port"):
                lines.append(f"port={self.extract_port_number(relay.get('port', ''))}//端口号")
            baud = str(relay.get("baudrate") or "").strip()
            if baud:
                lines.append(f"baudrate={baud}//波特率")
            relay_type = str(relay.get("relayType") or "").strip()
            if relay_type:
                lines.append(f"RelayType={relay_type}")
            for coil_index, status in enumerate(relay.get("coilStatuses", []), 1):
                lines.append(f"RelayCoil{coil_index}Status={status}")
            lines.append("")
            self.write_config_lines(file_obj, lines)

    def write_equipment_block(
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
        self.write_config_lines(file_obj, lines)

    def write_central_config_files(self, config: configparser.ConfigParser) -> None:
        config_dir = self.get_central_config_dir(config)
        if not config_dir:
            return
        try:
            os.makedirs(config_dir, exist_ok=True)
        except Exception:
            return

        power_config = self.parse_json_config_option(config, SECTION_CENTRAL, "c_pwr", {})
        relay_configs = self.parse_json_config_option(config, SECTION_CENTRAL, "c_rly", [])
        ig_config = self.parse_json_config_option(config, SECTION_CENTRAL, "c_ig", {})
        pw_config = self.parse_json_config_option(config, SECTION_CENTRAL, "c_pw", {})

        ignition_wait_time = ""
        ignition_current = ""
        if config.has_section(SECTION_IGNITION_CYCLE):
            ignition_wait_time = (config.get(SECTION_IGNITION_CYCLE, "waitTime", fallback="") or "").strip()
            ignition_current = (config.get(SECTION_IGNITION_CYCLE, "current", fallback="") or "").strip()
        if (not ignition_wait_time and not ignition_current) and config.has_section(SECTION_CENTRAL):
            ignition_wait_time = (config.get(SECTION_CENTRAL, "ign_waittime", fallback="") or "").strip()
            ignition_current = (config.get(SECTION_CENTRAL, "ign_current", fallback="") or "").strip()

        power_config_path = os.path.join(config_dir, DEFAULT_POWER_RELAY_CONFIG_FILENAME)
        if not self.has_power_relay_config(power_config, relay_configs, ig_config, pw_config):
            if os.path.exists(power_config_path):
                try:
                    os.remove(power_config_path)
                except Exception as error:
                    print(f"移除未配置的 {DEFAULT_POWER_RELAY_CONFIG_FILENAME} 失败: {error}")
        else:
            try:
                with open(power_config_path, "w", encoding="utf-8") as power_file:
                    if isinstance(power_config, dict) and str(power_config.get("port") or "").strip():
                        self.write_power_block(power_file, power_config)
                    self.write_relay_blocks(power_file, relay_configs)
                    if isinstance(ig_config, dict) and str(ig_config.get("equipmentType") or "").strip():
                        self.write_equipment_block(
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
                    if isinstance(pw_config, dict) and str(pw_config.get("equipmentType") or "").strip():
                        self.write_equipment_block(
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
                print(f"生成 {DEFAULT_POWER_RELAY_CONFIG_FILENAME} 失败: {error}")

        ignition_path = os.path.join(config_dir, DEFAULT_IGNITION_CYCLE_FILENAME)
        if not (ignition_wait_time or ignition_current):
            if os.path.exists(ignition_path):
                try:
                    os.remove(ignition_path)
                except Exception as error:
                    print(f"移除未配置的 {DEFAULT_IGNITION_CYCLE_FILENAME} 失败: {error}")
        else:
            try:
                with open(ignition_path, "w", encoding="utf-8") as ignition_file:
                    ignition_file.write("[IgnitionCycle]\n")
                    if ignition_wait_time:
                        ignition_file.write(f"waitTime={ignition_wait_time}\n")
                    if ignition_current:
                        ignition_file.write(f"current={ignition_current}\n")
            except Exception as error:
                print(f"生成 {DEFAULT_IGNITION_CYCLE_FILENAME} 失败: {error}")

        login_username = (config.get(SECTION_CENTRAL, "login_username", fallback="") or "").strip()
        login_password = (config.get(SECTION_CENTRAL, "login_password", fallback="") or "").strip()
        login_path = os.path.join(config_dir, DEFAULT_LOGIN_FILENAME)
        try:
            with open(login_path, "w", encoding="utf-8") as login_file:
                login_file.write("[login]\n")
                if login_username or login_password:
                    login_file.write(f"username={login_username}\n")
                    login_file.write(f"password={login_password}\n")
        except Exception as error:
            print(f"生成 {DEFAULT_LOGIN_FILENAME} 失败: {error}")
