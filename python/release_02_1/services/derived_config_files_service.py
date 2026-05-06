#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中央域派生配置文件生成服务。

职责：根据 Configuration.ini 中 [CENTRAL] 的值，
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
from services.config_constants import (
    OPTION_C_IG,
    OPTION_C_PW,
    OPTION_C_PWR,
    OPTION_C_RLY,
    OPTION_IGNITION_CYCLE_CURRENT,
    OPTION_IGNITION_CYCLE_WAIT_TIME,
    OPTION_IGN_CURRENT,
    OPTION_IGN_WAITTIME,
    OPTION_LOGIN_PASSWORD,
    OPTION_LOGIN_USERNAME,
    OPTION_OUTPUT_DIR,
    SECTION_CENTRAL,
)
from services.config_constants import (
    DEFAULT_IGNITION_CYCLE_FILENAME,
    DEFAULT_LOGIN_FILENAME,
    DEFAULT_POWER_RELAY_CONFIG_FILENAME,
)


class DerivedConfigFilesService:
    """中央域派生文件写入服务。"""

    def __init__(self, base_dir: str) -> None:
        """初始化派生文件服务。

        参数：
            base_dir：项目根目录，用于解析输出相对路径。

        返回：无。
        """
        self.base_dir = os.path.abspath(base_dir)

    def resolve_output_subdir(
        self,
        output_dir: str,
        subdir_name: str,
        *,
        create_dir: bool = False,
    ) -> Optional[str]:
        """解析并返回输出目录下的指定子目录路径。

        参数：
            output_dir：配置中的输出目录（可相对/绝对）。
            subdir_name：目标子目录名（如 ``Configuration``）。
            create_dir：为 True 时在不存在时创建目录。

        返回：
            解析后的绝对路径；无法解析时返回 ``None``。
        """
        return resolve_named_subdir(
            self.base_dir,
            output_dir,
            subdir_name,
            create_dir=create_dir,
        )

    def get_central_config_dir(self, config: configparser.ConfigParser) -> Optional[str]:
        """获取中央域 ``Configuration`` 目录路径。

        参数：
            config：当前主配置对象。

        返回：
            中央域配置目录绝对路径；缺少 CENTRAL 节或输出目录时返回 ``None``。
        """
        if not config.has_section(SECTION_CENTRAL):
            return None
        output_dir = (config.get(SECTION_CENTRAL, OPTION_OUTPUT_DIR, fallback="") or "").strip()
        if not output_dir:
            return None
        return self.resolve_output_subdir(output_dir, "Configuration", create_dir=True)

    @staticmethod
    def extract_port_number(port_text: str) -> str:
        """从端口文本中提取端口号。

        参数：
            port_text：端口文本，如 ``COM3``、``3``、``ttyS3``。

        返回：
            纯数字端口号字符串；无法提取时返回原文本（去空白后）。
        """
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
        """读取并解析 JSON 选项。

        参数：
            config：主配置对象。
            section：节名。
            option_name：选项名。
            default_value：缺失/空值/解析失败时返回的默认值。

        返回：
            解析后的对象；失败时返回 ``default_value``。
        """
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
        """判断单个继电器配置是否有效。

        参数：
            relay_config：继电器配置对象（通常为 dict）。

        返回：
            含有效 ``port``、``relayID``、``relayType`` 或 ``coilStatuses`` 时为 True，否则为 False。
        """
        if not isinstance(relay_config, dict):
            return False
        port = str(relay_config.get("port") or "").strip()
        if port:
            return True
        relay_id = relay_config.get("relayID")
        if relay_id is not None and str(relay_id).strip() != "":
            return True
        relay_type = str(relay_config.get("relayType") or "").strip()
        if relay_type:
            return True
        coil_statuses = relay_config.get("coilStatuses")
        if isinstance(coil_statuses, list) and len(coil_statuses) > 0:
            return True
        return False

    @staticmethod
    def has_power_relay_config(
        power_config: Any,
        relay_configs: Any,
        ig_config: Any,
        pw_config: Any,
    ) -> bool:
        """判断是否需要生成 Power/Relay 相关派生文件。

        参数：
            power_config：电源配置。
            relay_configs：继电器配置列表。
            ig_config：IG 配置。
            pw_config：PW 配置。

        返回：
            任一配置具备有效关键字段时返回 True，否则 False。
        """
        if isinstance(power_config, dict) and str(power_config.get("port") or "").strip():
            return True
        if isinstance(relay_configs, list):
            for relay in relay_configs:
                if DerivedConfigFilesService.has_relay_config(relay):
                    return True
        if isinstance(ig_config, dict) and str(ig_config.get("equipmentType") or "").strip():
            return True
        if isinstance(pw_config, dict) and str(pw_config.get("equipmentType") or "").strip():
            return True
        return False

    @staticmethod
    def write_config_lines(file_obj: Any, lines: List[str]) -> None:
        """按行写入文本内容。

        参数：
            file_obj：已打开的可写文件对象。
            lines：要写入的行列表（不含行尾换行符）。

        返回：无。
        """
        for line in lines:
            file_obj.write(f"{line}\n")

    def write_power_block(self, file_obj: Any, power_config: Any) -> None:
        """写入 Power 配置段。

        参数：
            file_obj：目标文件对象。
            power_config：电源配置字典。

        返回：无。
        """
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
        """写入继电器配置段（多组 Relay）。

        参数：
            file_obj：目标文件对象。
            relay_configs：继电器配置列表。

        返回：无。
        """
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
        """写入 IG/PW 设备配置段。

        参数：
            file_obj：目标文件对象。
            title：段名（如 ``IG``、``PW``）。
            config_data：设备配置字典。
            default_values：缺省字段值映射。
            include_init_comment：是否写入 initStatus 解释注释。

        返回：无。
        """
        payload_data = config_data if (config_data and config_data.get("equipmentType")) else {}
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
                f"Equipment_Type={payload_data.get('equipmentType', default_values['equipmentType'])}",
                f"ChannelNumber={payload_data.get('channelNumber', default_values['channelNumber'])}",
                f"initStatus={payload_data.get('initStatus', default_values['initStatus'])}",
                f"eqPosition={payload_data.get('eqPosition', default_values['eqPosition'])}",
                "",
            ]
        )
        self.write_config_lines(file_obj, lines)

    def write_central_config_files(self, config: configparser.ConfigParser) -> None:
        """根据中央域配置生成/清理派生配置文件。

        参数：
            config：主配置对象，读取 ``[CENTRAL]`` 与 ``[IGNITION_CYCLE]``。

        返回：无。内部按条件生成或删除
            ``PowerRelayConfig.txt``、``IgnitionCycle.txt``、``login.txt``。
        """
        config_dir = self.get_central_config_dir(config)
        if not config_dir:
            return
        try:
            os.makedirs(config_dir, exist_ok=True)
        except Exception:
            return

        power_config = self.parse_json_config_option(config, SECTION_CENTRAL, OPTION_C_PWR, {})
        relay_configs = self.parse_json_config_option(config, SECTION_CENTRAL, OPTION_C_RLY, [])
        ig_config = self.parse_json_config_option(config, SECTION_CENTRAL, OPTION_C_IG, {})
        pw_config = self.parse_json_config_option(config, SECTION_CENTRAL, OPTION_C_PW, {})

        ignition_wait_time = (config.get(SECTION_CENTRAL, OPTION_IGN_WAITTIME, fallback="") or "").strip()
        ignition_current = (config.get(SECTION_CENTRAL, OPTION_IGN_CURRENT, fallback="") or "").strip()

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
                        ignition_file.write(f"{OPTION_IGNITION_CYCLE_WAIT_TIME}={ignition_wait_time}\n")
                    if ignition_current:
                        ignition_file.write(f"{OPTION_IGNITION_CYCLE_CURRENT}={ignition_current}\n")
            except Exception as error:
                print(f"生成 {DEFAULT_IGNITION_CYCLE_FILENAME} 失败: {error}")

        login_username = (config.get(SECTION_CENTRAL, OPTION_LOGIN_USERNAME, fallback="") or "").strip()
        login_password = (config.get(SECTION_CENTRAL, OPTION_LOGIN_PASSWORD, fallback="") or "").strip()
        login_path = os.path.join(config_dir, DEFAULT_LOGIN_FILENAME)
        try:
            with open(login_path, "w", encoding="utf-8") as login_file:
                login_file.write("[login]\n")
                if login_username or login_password:
                    login_file.write(f"username={login_username}\n")
                    login_file.write(f"password={login_password}\n")
        except Exception as error:
            print(f"生成 {DEFAULT_LOGIN_FILENAME} 失败: {error}")
