#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理器（ConfigManager）— 基础设施层

目标：收纳所有对 Configuration.txt 的读、写、去重、格式化逻辑。
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

from infra.config import read_fixed_config
from utils.path_utils import resolve_target_subdir


def _clean_duplicate_sections(config_path: str) -> List[str]:
    """
    清理配置文件中的重复节和重复选项，保留第一个出现的节和选项。
    保护文件开头的注释和空行。返回清理后的行列表。
    """
    if not os.path.exists(config_path):
        return []

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"读取配置文件失败: {e}")
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
                    if stripped.startswith(","):
                        continue
                    _key_sections = ("LR_REAR", "DTC", "CENTRAL", "PATHS")
                    if (
                        "=" not in stripped
                        and current_section not in _key_sections
                        and invalid_short_token_re.match(stripped)
                    ):
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
        to_remove = [
            k for k in config.options(section)
            if invalid_pattern.match(k.strip())
        ]
        for key in to_remove:
            config.remove_option(section, key)
            print(f"已移除无效配置项 [{section}] {key}")


class ConfigManager:
    """
    配置管理器：统一 Configuration.txt / FixedConfig.txt 的读、写、去重、格式化。
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
            config_path: 主配置文件路径；为 None 时使用 base_dir/Configuration.txt（不存在则试 Configuration_can.txt）。
        """
        self.base_dir = os.path.abspath(base_dir)
        if config_path is None:
            p = os.path.join(self.base_dir, "Configuration.txt")
            if not os.path.exists(p):
                p = os.path.join(self.base_dir, "Configuration_can.txt")
            self.config_path = p
        else:
            self.config_path = os.path.abspath(config_path)

    @classmethod
    def from_base_dir(cls, base_dir: str, config_filename: str = "Configuration.txt") -> "ConfigManager":
        """从项目根目录创建 ConfigManager 实例，自动解析主配置文件路径。
        参数:
            base_dir: 项目根目录。
            config_filename: 主配置文件名，默认 Configuration.txt；若不存在则尝试 Configuration_can.txt。
        返回: ConfigManager 实例。
        """
        base_dir = os.path.abspath(base_dir)
        cfg_path = os.path.join(base_dir, config_filename)
        if not os.path.exists(cfg_path):
            alt = os.path.join(base_dir, "Configuration_can.txt")
            cfg_path = alt if os.path.exists(alt) else cfg_path
        return cls(base_dir, cfg_path)

    def _get_fixed_config_path(self) -> str:
        return os.path.join(self.base_dir, "FixedConfig.txt")

    def _read_fixed_config(self) -> Dict[str, str]:
        return read_fixed_config(self.base_dir)

    def _write_fixed_config(self, fixed_config: Dict[str, str]) -> None:
        """将固定配置字典写入 FixedConfig.txt（PATHS 节：映射表、输出文件名等）。
        参数:
            fixed_config: 键为配置项名、值为字符串的字典，仅写入存在且非空的键。
        无返回值。
        """
        path = self._get_fixed_config_path()
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
        for key in mapping_keys:
            if fixed_config.get(key):
                lines.append(f"{key} = {fixed_config[key]}\n")
        lines.append("\n")
        output_keys = [
            "output_filename", "cin_output_filename", "xml_output_filename",
            "didinfo_output_filename", "didconfig_output_filename",
            "uart_output_filename", "uds_output_filename", "didinfo_variants",
        ]
        for key in output_keys:
            if fixed_config.get(key):
                lines.append(f"{key} = {fixed_config[key]}\n")
        while lines and not lines[-1].strip():
            lines.pop()
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def _write_uds_files(
        self, config: configparser.ConfigParser, only_domains: Optional[List[str]] = None
    ) -> None:
        """根据各域 output_dir 与 uds_ecu_qualifier 在 output_dir/Configuration 下生成 uds.txt。
        参数:
            config: 已读入的 ConfigParser，含 LR_REAR/CENTRAL/DTC 等节。
            only_domains: 仅对这些域（如 ["LR_REAR"]）写入；None 表示三域都写，避免共用 output_dir 时覆盖。
        无返回值。文件内容为 [UDS] 与 ECU_qualifier=...
        """
        fixed = self._read_fixed_config()
        uds_filename = (fixed.get("uds_output_filename") or "uds.txt").strip() or "uds.txt"
        all_domains = [
            ("LR_REAR", "output_dir", "uds_ecu_qualifier"),
            ("CENTRAL", "output_dir", "uds_ecu_qualifier"),
            ("DTC", "output_dir", "uds_ecu_qualifier"),
        ]
        domains = (
            [d for d in all_domains if d[0] in only_domains]
            if only_domains
            else all_domains
        )

        for section, out_key, uds_key in domains:
            if not config.has_section(section):
                continue
            out_dir = config.get(section, out_key, fallback="").strip()
            uds_val = config.get(section, uds_key, fallback="").strip()
            if not out_dir or not uds_val:
                continue

            # 解析用户选择的输出根目录（相对路径以 base_dir 为准）
            if not os.path.isabs(out_dir):
                root = os.path.abspath(os.path.join(self.base_dir, out_dir))
            else:
                root = os.path.abspath(out_dir)

            # 在输出根目录下寻找/创建名为 Configuration 的子目录（大小写不敏感）
            config_dir = None
            if os.path.basename(root).lower() == "configuration":
                config_dir = root
            else:
                if os.path.isdir(root):
                    for name in os.listdir(root):
                        if name.lower() == "configuration":
                            cand = os.path.join(root, name)
                            if os.path.isdir(cand):
                                config_dir = cand
                                break
                if config_dir is None:
                    config_dir = os.path.join(root, "Configuration")
            try:
                os.makedirs(config_dir, exist_ok=True)
            except Exception:
                continue

            legacy_uds_path = os.path.join(config_dir, "uds.txt")
            uds_path = os.path.join(config_dir, uds_filename)
            try:
                if (
                    os.path.normcase(os.path.abspath(legacy_uds_path))
                    != os.path.normcase(os.path.abspath(uds_path))
                    and os.path.exists(legacy_uds_path)
                ):
                    os.remove(legacy_uds_path)
                with open(uds_path, "w", encoding="utf-8") as f:
                    f.write("[UDS]\n")
                    f.write(f"ECU_qualifier={uds_val}\n")
            except Exception as e:
                print(f"写入 uds.txt 失败 ({section}): {e}")

    def _get_central_config_dir(self, config: configparser.ConfigParser) -> Optional[str]:
        """获取中央域 output_dir 下的 Configuration 目录（与 UART/DIDConfig 等一致，使用 resolve_target_subdir）。"""
        if not config.has_section("CENTRAL"):
            return None
        out_dir = (config.get("CENTRAL", "output_dir", fallback="") or "").strip()
        if not out_dir:
            return None
        try:
            return resolve_target_subdir(self.base_dir, out_dir, "Configuration")
        except Exception:
            # 若 Configuration 子目录不存在，则创建并返回（与 UART 要求目录存在时的行为兼容）
            if not os.path.isabs(out_dir):
                root = os.path.abspath(os.path.join(self.base_dir, out_dir))
            else:
                root = os.path.abspath(out_dir)
            config_dir = os.path.join(root, "Configuration")
            try:
                os.makedirs(config_dir, exist_ok=True)
                return config_dir
            except Exception:
                return None

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

        def _parse_json(key: str, default: Any):
            if not config.has_option("CENTRAL", key):
                return default
            raw = config.get("CENTRAL", key, fallback="").strip()
            if not raw:
                return default
            try:
                return json.loads(raw)
            except Exception:
                return default

        power_config = _parse_json("c_pwr", {})
        relay_configs = _parse_json("c_rly", [])
        ig_config = _parse_json("c_ig", {})
        pw_config = _parse_json("c_pw", {})
        # 点火循环：与副本一致，优先从 [IgnitionCycle] 读，再回退到 [CENTRAL]
        ign_waittime = ""
        ign_current = ""
        if config.has_section("IgnitionCycle"):
            ign_waittime = (config.get("IgnitionCycle", "waitTime", fallback="") or "").strip()
            ign_current = (config.get("IgnitionCycle", "current", fallback="") or "").strip()
        if (not ign_waittime and not ign_current) and config.has_section("CENTRAL"):
            ign_waittime = (config.get("CENTRAL", "ign_waittime", fallback="") or "").strip()
            ign_current = (config.get("CENTRAL", "ign_current", fallback="") or "").strip()

        # 仅当用户实际配置了程控电源/继电器/IG/PW 之一时才生成 PowerRelayConfig.txt；未配置则不生成并删除已有文件
        def _has_power_relay_config() -> bool:
            if power_config and power_config.get("port"):
                return True
            if relay_configs:
                for r in relay_configs:
                    if r.get("relayID") or r.get("relayType") or (r.get("coilStatuses") and len(r.get("coilStatuses", [])) > 0) or r.get("port"):
                        return True
            if ig_config and ig_config.get("equipmentType"):
                return True
            if pw_config and pw_config.get("equipmentType"):
                return True
            return False

        power_path = os.path.join(config_dir, "PowerRelayConfig.txt")
        if not _has_power_relay_config():
            if os.path.exists(power_path):
                try:
                    os.remove(power_path)
                except Exception as e:
                    print(f"移除未配置的 PowerRelayConfig.txt 失败: {e}")
        else:
            try:
                with open(power_path, "w", encoding="utf-8") as f:
                    # [Power]//电源（程控电源）
                    p = power_config if (power_config and power_config.get("port")) else {}
                    port_val = self._extract_port_number(p.get("port", "")) if p.get("port") else "0"
                    f.write("[Power]//电源\n")
                    f.write(f"port={port_val}//端口号\n")
                    f.write(f"baudrate={p.get('baudrate', '115200')}//波特率\n")
                    f.write(f"dataBits={p.get('dataBits', '8')}//数据位\n")
                    f.write(f"stopBits={p.get('stopBits', '1')}//停止位\n")
                    f.write(f"kHANDSHAKE_DISABLED={p.get('kHANDSHAKE_DISABLED', '0')}//握手\n")
                    f.write(f"parity={p.get('parity', '0')}//校验\n")
                    f.write(f"channel={p.get('channel', '1')}//默认读取电流通道\n")
                    f.write("\n")
                    # [RelayN]//继电器：仅当有“有效配置”时才写入，不再写默认占位 [Relay1]
                    if relay_configs and len(relay_configs) > 0:
                        for idx, relay in enumerate(relay_configs, 1):
                            has_valid = (
                                relay.get("relayID")
                                or relay.get("relayType")
                                or (relay.get("coilStatuses") and len(relay.get("coilStatuses", [])) > 0)
                                or relay.get("port")
                            )
                            if not has_valid:
                                continue
                            f.write(f"[Relay{idx}]//继电器\n")
                            if relay.get("port"):
                                f.write(f"port={self._extract_port_number(relay.get('port', ''))}//端口号\n")
                            f.write(f"baudrate={relay.get('baudrate', '9600')}//波特率\n")
                            f.write(f"dataBits={relay.get('dataBits', '8')}//数据位\n")
                            f.write(f"stopBits={relay.get('stopBits', '1')}//停止位\n")
                            f.write(f"kHANDSHAKE_DISABLED={relay.get('kHANDSHAKE_DISABLED', '0')}//握手\n")
                            f.write(f"parity={relay.get('parity', '0')}//校验\n")
                            f.write(f"relayID={relay.get('relayID', '1')}//继电器设备地址\n")
                            f.write(f"RelayType={relay.get('relayType', 'RS232_8')}\n")
                            for coil_idx, status in enumerate(relay.get("coilStatuses", []), 1):
                                f.write(f"RelayCoil{coil_idx}Status={status}\n")
                            f.write("\n")
                    # [IG] 点火装置
                    ig = ig_config if (ig_config and ig_config.get("equipmentType")) else {}
                    f.write("[IG]\n")
                    f.write("//Equipment_Type设备类型：Power/Relay\n")
                    f.write("//ChannelNumber如果类型是Power,此含义是电源通道号，如果类型是Relay,此含义是线圈号\n")
                    f.write("//initStatus初始状态，如果设备类型是Power:1代表上电，0代表下电，如果类型是Relay:17代表常开，18代表常关\n")
                    f.write("//eqPosition设备位置\n")
                    f.write(f"Equipment_Type={ig.get('equipmentType', 'Power')}\n")
                    f.write(f"ChannelNumber={ig.get('channelNumber', '1')}\n")
                    f.write(f"initStatus={ig.get('initStatus', '1')}\n")
                    f.write(f"eqPosition={ig.get('eqPosition', '1')}\n")
                    f.write("\n")
                    # [PW] 程控电源/继电器装置
                    pw = pw_config if (pw_config and pw_config.get("equipmentType")) else {}
                    f.write("[PW]\n")
                    f.write("//Equipment_Type设备类型：Power/Relay\n")
                    f.write("//ChannelNumber如果类型是Power,此含义是电源通道号，如果类型是Relay,此含义是线圈号\n")
                    f.write(f"Equipment_Type={pw.get('equipmentType', 'Relay')}\n")
                    f.write(f"ChannelNumber={pw.get('channelNumber', '1')}\n")
                    f.write(f"initStatus={pw.get('initStatus', '17')}\n")
                    f.write(f"eqPosition={pw.get('eqPosition', '1')}\n")
                    f.write("\n")
            except Exception as e:
                print(f"生成 PowerRelayConfig.txt 失败: {e}")

        # 仅当用户实际配置了点火循环（waitTime/current 有值）时才生成 IgnitionCycle.txt；未配置则不生成并删除已有文件
        ign_path = os.path.join(config_dir, "IgnitionCycle.txt")
        if not (ign_waittime or ign_current):
            if os.path.exists(ign_path):
                try:
                    os.remove(ign_path)
                except Exception as e:
                    print(f"移除未配置的 IgnitionCycle.txt 失败: {e}")
        else:
            try:
                with open(ign_path, "w", encoding="utf-8") as f:
                    f.write("[IgnitionCycle]\n")
                    if ign_waittime:
                        f.write(f"waitTime={ign_waittime}\n")
                    if ign_current:
                        f.write(f"current={ign_current}\n")
            except Exception as e:
                print(f"生成 IgnitionCycle.txt 失败: {e}")

        # 运行账号：生成 login.txt，有账号密码则写入，无则仅写 [login]
        login_username = (config.get("CENTRAL", "login_username", fallback="") or "").strip()
        login_password = (config.get("CENTRAL", "login_password", fallback="") or "").strip()
        login_path = os.path.join(config_dir, "login.txt")
        try:
            with open(login_path, "w", encoding="utf-8") as f:
                f.write("[login]\n")
                if login_username or login_password:
                    f.write(f"username={login_username}\n")
                    f.write(f"password={login_password}\n")
        except Exception as e:
            print(f"生成 login.txt 失败: {e}")

    def _init_fixed_config_from_main_config(self) -> None:
        if os.path.exists(self._get_fixed_config_path()) or not os.path.exists(self.config_path):
            return
        try:
            cfg = configparser.ConfigParser()
            cfg.optionxform = str
            cfg.read(self.config_path, encoding="utf-8")
            fixed = {}
            if cfg.has_section("PATHS"):
                keys = [
                    "unified_mapping_excel", "mapping_sheets", "cin_mapping_sheet",
                    "output_filename", "cin_output_filename", "xml_output_filename",
                    "didinfo_output_filename", "didconfig_output_filename", "didinfo_variants",
                    "mapping_excel", "cin_mapping_excel",
                ]
                for key in keys:
                    if cfg.has_option("PATHS", key):
                        fixed[key] = cfg.get("PATHS", key)
            if fixed:
                self._write_fixed_config(fixed)
        except Exception as e:
            print(f"从主配置初始化固定配置失败: {e}")

    def _reload(self) -> configparser.ConfigParser:
        """读入配置并做去重后写回，再解析返回 ConfigParser。"""
        with self._lock:
            cleaned = _clean_duplicate_sections(self.config_path)
            if cleaned:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    f.writelines(cleaned)
            config = configparser.ConfigParser()
            config.optionxform = str
            if os.path.exists(self.config_path):
                try:
                    config.read(self.config_path, encoding="utf-8")
                except Exception:
                    with open(self.config_path, "r", encoding="utf-8", errors="replace") as f:
                        config.read_file(f)
            return config

    def load_ui_data(self) -> Dict[str, Any]:
        """加载主配置并平铺为前端 collectCurrentState 所需字段格式。
        无参数。从 Configuration.txt 与 FixedConfig 读入，按节映射为 can_input、out_root、c_rly 等键。
        返回: 平铺字典，键为前端 state 字段名，值为配置值（字符串/列表/字典等）。
        """
        config = self._reload()
        out: Dict[str, Any] = {}

        # 1. LR_REAR -> 左右后域基础配置
        if config.has_section("LR_REAR"):
            lr = dict(config.items("LR_REAR"))
            out["can_input"] = lr.get("input_excel", "")
            out["out_root"] = lr.get("output_dir", "")
            out["levels"] = lr.get("case_levels", "ALL")
            out["platforms"] = lr.get("case_platforms", "")
            out["models"] = lr.get("case_models", "")
            out["target_versions"] = lr.get("case_target_versions", "")
            out["selected_sheets"] = lr.get("selected_sheets", "")
            out["log_level"] = lr.get("log_level_min", "info")
            didinfo_raw = lr.get("didinfo_inputs", "")
            out["didinfo_excel"] = didinfo_raw.split(" | ")[0] if didinfo_raw else ""
            out["cin_excel"] = lr.get("cin_input_excel", "")
            out["uds_ecu_qualifier"] = lr.get("uds_ecu_qualifier", "")

        # 2. IOMAPPING / DID_CONFIG
        if config.has_section("IOMAPPING"):
            io_raw = config.get("IOMAPPING", "inputs", fallback="")
            out["io_excel"] = io_raw.split(" | ")[0] if io_raw else ""
        if config.has_section("DID_CONFIG"):
            out["didconfig_excel"] = config.get("DID_CONFIG", "input_excel", fallback="")

        # 3. CENTRAL -> c_* 字段
        if config.has_section("CENTRAL"):
            c = dict(config.items("CENTRAL"))
            out["c_input"] = c.get("input_excel", "")
            out["c_out_root"] = c.get("output_dir", "")
            out["c_levels"] = c.get("case_levels", "ALL")
            out["c_platforms"] = c.get("case_platforms", "")
            out["c_models"] = c.get("case_models", "")
            out["c_target_versions"] = c.get("case_target_versions", "")
            out["c_selected_sheets"] = c.get("selected_sheets", "")
            out["c_log_level"] = c.get("log_level_min", "info")
            out["c_uds_ecu_qualifier"] = c.get("uds_ecu_qualifier", "")
            # 点火循环：仅当有非空值时才返回，避免未配置时前端显示“已配置”或写入默认值
            _ign_wt = (c.get("ign_waittime", "") or "").strip()
            _ign_cur = (c.get("ign_current", "") or "").strip()
            if not _ign_wt and config.has_section("IgnitionCycle"):
                _ign_wt = (config.get("IgnitionCycle", "waitTime", fallback="") or "").strip()
            if not _ign_cur and config.has_section("IgnitionCycle"):
                _ign_cur = (config.get("IgnitionCycle", "current", fallback="") or "").strip()
            if _ign_wt or _ign_cur:
                out["c_ign_waitTime"] = _ign_wt
                out["c_ign_current"] = _ign_cur
            out["c_uart"] = c.get("uart_excel", "")
            uart_comm = {}
            for cfg_key, ui_key in [
                ("uart_comm_port", "port"),
                ("uart_comm_baudrate", "baudrate"),
                ("uart_comm_dataBits", "dataBits"),
                ("uart_comm_stopBits", "stopBits"),
                ("uart_comm_kHANDSHAKE_DISABLED", "kHANDSHAKE_DISABLED"),
                ("uart_comm_parity", "parity"),
                ("uart_comm_frameTypeIs8676", "frameTypeIs8676"),
            ]:
                val = c.get(cfg_key, "")
                if val != "":
                    uart_comm[ui_key] = val
            out["c_uart_comm"] = uart_comm

            # 程控电源 / 继电器 / IG / PW：仅当配置中有且为“有意义”内容时才返回，避免未配置时回写默认值到 Configuration.txt
            def _parse_json_field(key: str, default):
                raw = c.get(key, "").strip()
                if not raw:
                    return default
                try:
                    return json.loads(raw)
                except Exception:
                    return default

            _c_pwr = _parse_json_field("c_pwr", {})
            if isinstance(_c_pwr, dict) and (_c_pwr.get("port") or "").strip():
                out["c_pwr"] = _c_pwr
            _c_rly = _parse_json_field("c_rly", [])
            if isinstance(_c_rly, list) and len(_c_rly) > 0:
                has_rly = any(
                    r.get("relayID") or r.get("relayType") or (r.get("coilStatuses") and len(r.get("coilStatuses", [])) > 0) or r.get("port")
                    for r in _c_rly
                )
                if has_rly:
                    out["c_rly"] = _c_rly
            # IG/PW：仅当配置中确有内容时才返回
            _c_ig = _parse_json_field("c_ig", {})
            _c_pw = _parse_json_field("c_pw", {})
            if _c_ig and isinstance(_c_ig, dict) and (_c_ig.get("equipmentType") or _c_ig.get("channelNumber")):
                out["c_ig"] = _c_ig
            if _c_pw and isinstance(_c_pw, dict) and (_c_pw.get("equipmentType") or _c_pw.get("channelNumber")):
                out["c_pw"] = _c_pw
            out["c_login_username"] = c.get("login_username", "")
            out["c_login_password"] = c.get("login_password", "")

        # 4. DTC -> d_* 字段
        if config.has_section("DTC"):
            d = dict(config.items("DTC"))
            out["d_input"] = d.get("input_excel", "")
            out["d_out_root"] = d.get("output_dir", "")
            out["d_levels"] = d.get("case_levels", "ALL")
            out["d_platforms"] = d.get("case_platforms", "")
            out["d_models"] = d.get("case_models", "")
            out["d_target_versions"] = d.get("case_target_versions", "")
            out["d_selected_sheets"] = d.get("selected_sheets", "")
            out["d_log_level"] = d.get("log_level_min", "info")
            out["d_uds_ecu_qualifier"] = d.get("uds_ecu_qualifier", "")
            didinfo_raw = d.get("didinfo_inputs", "")
            out["d_didinfo_excel"] = didinfo_raw.split(" | ")[0] if didinfo_raw else ""
            out["d_cin_excel"] = d.get("cin_input_excel", "")
        if config.has_section("DTC_IOMAPPING"):
            io_raw = config.get("DTC_IOMAPPING", "inputs", fallback="")
            out["d_io_excel"] = io_raw.split(" | ")[0] if io_raw else ""
        if config.has_section("DTC_CONFIG_ENUM"):
            didcfg_raw = config.get("DTC_CONFIG_ENUM", "inputs", fallback="")
            out["d_didconfig_excel"] = didcfg_raw.split(" | ")[0] if didcfg_raw else ""

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
            for key, val in data.items():
                config.set(domain, key, str(val) if val is not None else "")
            self._write_formatted_config(config)

    def save_formatted(self) -> None:
        """重新加载配置、移除无效项、按固定格式写回。"""
        with self._lock:
            config = self._reload()
            _remove_invalid_config_options(config)
            self._init_fixed_config_from_main_config()
            self._write_formatted_config(config)

    def save_ui_data(self, data: Dict[str, Dict[str, Any]]) -> None:
        """将前端按节提交的 data 写回主配置并格式化写回文件。
        增强点：
        - 对 CENTRAL 段的 UI 托管键（如 c_pwr/c_rly/c_ig/c_pw/ign_*/login_*/uart_comm_*）做“缺失即删”的处理，
          防止增量更新导致旧值残留。
        - 对所有节的键，若值为 None / 空串 / 空列表 / 空字典，则优先执行 remove_option 而不是写入空字符串。
        参数:
            data: 节名为键、值为「选项名->值」字典，如 {"LR_REAR": {"input_excel": "..."}, ...}。
        无返回值。
        """
        with self._lock:
            config = self._reload()

            # 本次前端实际提交更新的节名列表，用于后续精确控制 UDS/中央域附属文件的生成范围
            updated_sections: List[str] = list(data.keys())

            # 中央域由前端 UI 统一托管的配置键：当前端未提供或提供的是“空值”时，应主动从配置文件中移除
            central_managed_keys = {
                "c_pwr",
                "c_rly",
                "c_ig",
                "c_pw",
                "ign_waittime",
                "ign_current",
                "login_username",
                "login_password",
                "uart_comm_port",
                "uart_comm_baudrate",
                "uart_comm_dataBits",
                "uart_comm_stopBits",
                "uart_comm_kHANDSHAKE_DISABLED",
                "uart_comm_parity",
                "uart_comm_frameTypeIs8676",
            }

            for section, kv in data.items():
                if not config.has_section(section):
                    config.add_section(section)

                # 1) CENTRAL 段：先对托管键做“缺失/空值即删除”的处理
                if section == "CENTRAL":
                    for m_key in central_managed_keys:
                        # 前端完全没传这个键，或者传的是 None / "" / [] / {}，都视为“用户清空/关闭”
                        if m_key not in kv or kv.get(m_key) in (None, "", [], {}):
                            if config.has_option(section, m_key):
                                config.remove_option(section, m_key)

                # 2) 通用写入逻辑：有值则 set，空值则删
                for key, val in kv.items():
                    opt = str(key)
                    if val in (None, "", [], {}):
                        if config.has_option(section, opt):
                            config.remove_option(section, opt)
                    else:
                        config.set(section, opt, str(val))

            # 仅针对本次更新涉及到的节生成对应的 UDS 与中央域附属文件，避免无关域被“全量刷新”
            self._write_formatted_config(config, uds_domains=updated_sections)

    def sync_to_file(self, target_path: Optional[str] = None) -> None:
        """将当前内存中的配置（去重后）同步写入指定文件。
        参数:
            target_path: 目标配置文件路径；为 None 时写回 self.config_path。
        无返回值。
        """
        path = target_path or self.config_path
        with self._lock:
            config = self._reload()
            _remove_invalid_config_options(config)
            self._write_formatted_config(config, path)

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
        path = config_path or self.config_path
        fixed_config_backup = self._read_fixed_config()
        if not fixed_config_backup and os.path.exists(path):
            try:
                backup = configparser.ConfigParser()
                backup.optionxform = str
                backup.read(path, encoding="utf-8")
                if backup.has_section("PATHS"):
                    fixed_keys = [
                        "unified_mapping_excel", "mapping_sheets", "cin_mapping_sheet",
                        "output_filename", "cin_output_filename", "xml_output_filename",
                        "didinfo_output_filename", "didconfig_output_filename",
                        "uart_output_filename", "uds_output_filename", "didinfo_variants",
                        "mapping_excel", "cin_mapping_excel",
                    ]
                    for key in fixed_keys:
                        if backup.has_option("PATHS", key):
                            fixed_config_backup[key] = backup.get("PATHS", key)
                    if fixed_config_backup:
                        self._write_fixed_config(fixed_config_backup)
            except Exception as e:
                print(f"从主配置读取固定配置时出错: {e}")

        fixed_paths_keys = [
            "unified_mapping_excel", "mapping_sheets", "cin_mapping_sheet",
            "output_filename", "cin_output_filename", "xml_output_filename",
            "didinfo_output_filename", "didconfig_output_filename",
            "uart_output_filename", "uds_output_filename", "didinfo_variants",
        ]
        dynamic_paths_keys = ["mapping_excel", "cin_mapping_excel"]

        lines: List[str] = []

        lines.append("# ============================================================\n")
        lines.append("# 左右后域配置\n")
        lines.append("# ============================================================\n")
        lines.append("[LR_REAR]\n")
        lr_written = set()
        if config.has_section("LR_REAR"):
            for key in ["input_excel", "input_excel_dir"]:
                if config.has_option("LR_REAR", key):
                    lines.append(f"{key} = {config.get('LR_REAR', key) or ''}\n")
                    lr_written.add(key.lower())
            lines.append("\n")
            if config.has_option("LR_REAR", "output_dir"):
                lines.append(f"output_dir = {config.get('LR_REAR', 'output_dir') or ''}\n")
                lr_written.add("output_dir")
            lines.append("\n")
            for key in ["case_levels", "case_platforms", "case_models", "case_target_versions"]:
                if config.has_option("LR_REAR", key):
                    lines.append(f"{key} = {config.get('LR_REAR', key) or ''}\n")
                    lr_written.add(key.lower())
            lines.append("\n")
            if config.has_option("LR_REAR", "selected_sheets"):
                lines.append("# 勾选的工作表\n")
                lines.append(f"selected_sheets = {config.get('LR_REAR', 'selected_sheets', fallback='') or ''}\n")
                lr_written.add("selected_sheets")
                lines.append("\n")
            if config.has_option("LR_REAR", "log_level_min"):
                val = config.get("LR_REAR", "log_level_min", fallback="info").strip().lower()
                if val in ("info", "warning", "error"):
                    lines.append("log_level_min = " + val + "\n")
                    lr_written.add("log_level_min")
                    lines.append("\n")
            if config.has_option("LR_REAR", "didinfo_inputs"):
                lines.append(f"didinfo_inputs = {config.get('LR_REAR', 'didinfo_inputs') or ''}\n")
                lr_written.add("didinfo_inputs")
            if config.has_option("LR_REAR", "cin_input_excel"):
                lines.append(f"cin_input_excel = {config.get('LR_REAR', 'cin_input_excel') or ''}\n")
                lr_written.add("cin_input_excel")

        if config.has_section("IOMAPPING"):
            lines.append("[IOMAPPING]\n")
            for key in config.options("IOMAPPING"):
                if key.lower() != "enabled":
                    lines.append(f"{key} = {config.get('IOMAPPING', key) or ''}\n")
            lines.append("\n")
        if config.has_section("DID_CONFIG"):
            lines.append("[DID_CONFIG]\n")
            for key in config.options("DID_CONFIG"):
                lines.append(f"{key} = {config.get('DID_CONFIG', key) or ''}\n")
            lines.append("\n")
        if config.has_section("CONFIG_ENUM"):
            lines.append("[CONFIG_ENUM]\n")
            for key in config.options("CONFIG_ENUM"):
                if key.lower() != "enabled":
                    lines.append(f"{key} = {config.get('CONFIG_ENUM', key) or ''}\n")
            lines.append("\n")

        lines.append("# ============================================================\n")
        lines.append("# 中央域配置\n")
        lines.append("# ============================================================\n")
        lines.append("[CENTRAL]\n")
        if config.has_section("CENTRAL"):
            # 基础与表格
            for key in [
                "input_excel",
                "input_excel_dir",
                "uart_excel",
                "srv_excel",
                "pwr_excel",
                "rly_excel",
                "selected_sheets",
            ]:
                if config.has_option("CENTRAL", key):
                    lines.append(f"{key} = {config.get('CENTRAL', key) or ''}\n")
            # 串口通信配置
            _uart_keys = [
                "uart_comm_port",
                "uart_comm_baudrate",
                "uart_comm_dataBits",
                "uart_comm_stopBits",
                "uart_comm_kHANDSHAKE_DISABLED",
                "uart_comm_parity",
                "uart_comm_frameTypeIs8676",
            ]
            if any(config.has_option("CENTRAL", k) for k in _uart_keys):
                lines.append("\n# 串口通信配置\n")
                for key in _uart_keys:
                    if config.has_option("CENTRAL", key):
                        lines.append(f"{key} = {config.get('CENTRAL', key) or ''}\n")
            # 点火循环（中央域，兼容从 CENTRAL 读取）
            if config.has_option("CENTRAL", "ign_waittime") or config.has_option("CENTRAL", "ign_current"):
                lines.append("\n# 点火循环配置（中央域，兼容从本段读取）\n")
                if config.has_option("CENTRAL", "ign_waittime"):
                    lines.append(f"ign_waittime = {config.get('CENTRAL', 'ign_waittime') or ''}\n")
                if config.has_option("CENTRAL", "ign_current"):
                    lines.append(f"ign_current = {config.get('CENTRAL', 'ign_current') or ''}\n")
            # 程控电源/继电器/IG/PW：与点火循环一致，仅当配置中有该选项时才写入，避免写空覆盖
            if config.has_option("CENTRAL", "c_pwr"):
                lines.append("\n# 程控电源配置（c_pwr）\n")
                lines.append(f"c_pwr = {config.get('CENTRAL', 'c_pwr') or ''}\n")
            if config.has_option("CENTRAL", "c_rly"):
                lines.append("\n# 继电器配置（c_rly）\n")
                lines.append(f"c_rly = {config.get('CENTRAL', 'c_rly') or ''}\n")
            if config.has_option("CENTRAL", "c_ig"):
                lines.append("\n# IG 配置（点火装置）\n")
                lines.append(f"c_ig = {config.get('CENTRAL', 'c_ig') or ''}\n")
            if config.has_option("CENTRAL", "c_pw"):
                lines.append("\n# PW 配置（程控电源/继电器装置）\n")
                lines.append(f"c_pw = {config.get('CENTRAL', 'c_pw') or ''}\n")
            lines.append("\n")
            if config.has_option("CENTRAL", "output_dir"):
                lines.append(f"output_dir = {config.get('CENTRAL', 'output_dir') or ''}\n")
            lines.append("\n")
            for key in ["case_levels", "case_platforms", "case_models", "case_target_versions"]:
                if config.has_option("CENTRAL", key):
                    lines.append(f"{key} = {config.get('CENTRAL', key) or ''}\n")
            if config.has_option("CENTRAL", "log_level_min"):
                val = config.get("CENTRAL", "log_level_min", fallback="info").strip().lower()
                if val in ("info", "warning", "error"):
                    lines.append(f"log_level_min = {val}\n")
            if config.has_option("CENTRAL", "uds_ecu_qualifier"):
                val = config.get("CENTRAL", "uds_ecu_qualifier", fallback="").strip()
                if val:
                    lines.append(f"uds_ecu_qualifier = {val}\n")
            # 运行账号（中央域，写入 Configuration/login.txt）
            if config.has_option("CENTRAL", "login_username") or config.has_option("CENTRAL", "login_password"):
                lines.append("\n# 运行账号（生成至 output_dir/Configuration/login.txt）\n")
                if config.has_option("CENTRAL", "login_username"):
                    lines.append(f"login_username = {config.get('CENTRAL', 'login_username') or ''}\n")
                if config.has_option("CENTRAL", "login_password"):
                    lines.append(f"login_password = {config.get('CENTRAL', 'login_password') or ''}\n")

        # 点火循环配置（中央域相关，写在 [CENTRAL] 之后）
        if config.has_section("IgnitionCycle") or config.has_section("CENTRAL"):
            # 兼容老配置中 [IgnitionCycle] 里使用 ign_waittime/ign_current 的写法
            wait_val = ""
            if config.has_section("IgnitionCycle"):
                wait_val = (
                    config.get("IgnitionCycle", "waitTime", fallback="")
                    or config.get("IgnitionCycle", "ign_waittime", fallback="")
                    or ""
                ).strip()
            if not wait_val and config.has_section("CENTRAL"):
                wait_val = (config.get("CENTRAL", "ign_waittime", fallback="") or "").strip()

            cur_val = ""
            if config.has_section("IgnitionCycle"):
                cur_val = (
                    config.get("IgnitionCycle", "current", fallback="")
                    or config.get("IgnitionCycle", "ign_current", fallback="")
                    or ""
                ).strip()
            if not cur_val and config.has_section("CENTRAL"):
                cur_val = (config.get("CENTRAL", "ign_current", fallback="") or "").strip()

            # 只要原文件里存在 [IgnitionCycle]，即使值为空也不要把整个节删掉
            if wait_val or cur_val or config.has_section("IgnitionCycle"):
                lines.append("\n[IgnitionCycle]\n")
                lines.append(f"waitTime = {wait_val}\n")
                lines.append(f"current = {cur_val}\n")

        lines.append("\n# ============================================================\n")
        lines.append("# DTC配置\n")
        lines.append("# ============================================================\n")
        lines.append("[DTC]\n")
        if config.has_section("DTC"):
            for key in ["input_excel", "input_excel_dir"]:
                if config.has_option("DTC", key):
                    lines.append(f"{key} = {config.get('DTC', key) or ''}\n")
            if config.has_option("DTC", "selected_sheets"):
                lines.append(f"selected_sheets = {config.get('DTC', 'selected_sheets') or ''}\n")
            lines.append("\n")
            if config.has_option("DTC", "output_dir"):
                lines.append(f"output_dir = {config.get('DTC', 'output_dir') or ''}\n")
            lines.append("\n")
            for key in ["case_levels", "case_platforms", "case_models", "case_target_versions"]:
                if config.has_option("DTC", key):
                    lines.append(f"{key} = {config.get('DTC', key) or ''}\n")
            if config.has_option("DTC", "log_level_min"):
                val = config.get("DTC", "log_level_min", fallback="info").strip().lower()
                if val in ("info", "warning", "error"):
                    lines.append(f"log_level_min = {val}\n")
            if config.has_option("DTC", "didinfo_inputs"):
                lines.append(f"didinfo_inputs = {config.get('DTC', 'didinfo_inputs') or ''}\n")
            if config.has_option("DTC", "cin_input_excel"):
                lines.append(f"cin_input_excel = {config.get('DTC', 'cin_input_excel') or ''}\n")
            if config.has_option("DTC", "uds_ecu_qualifier"):
                val = config.get("DTC", "uds_ecu_qualifier", fallback="").strip()
                if val:
                    lines.append(f"uds_ecu_qualifier = {val}\n")

        if config.has_section("DTC_IOMAPPING"):
            lines.append("\n[DTC_IOMAPPING]\n")
            for key in config.options("DTC_IOMAPPING"):
                if key.lower() != "enabled":
                    lines.append(f"{key} = {config.get('DTC_IOMAPPING', key) or ''}\n")
        if config.has_section("DTC_CONFIG_ENUM"):
            lines.append("\n[DTC_CONFIG_ENUM]\n")
            for key in config.options("DTC_CONFIG_ENUM"):
                if key.lower() != "enabled":
                    lines.append(f"{key} = {config.get('DTC_CONFIG_ENUM', key) or ''}\n")

        if fixed_config_backup:
            current_fixed = {}
            fixed_keys = fixed_paths_keys + dynamic_paths_keys
            for key in fixed_keys:
                if key in fixed_config_backup:
                    current_fixed[key] = fixed_config_backup[key]
            if current_fixed:
                self._write_fixed_config(current_fixed)

        if not lines:
            lines = [
                "# ============================================================\n",
                "# 左右后域配置\n",
                "# ============================================================\n",
                "[LR_REAR]\n",
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
                opt = parts[0].strip()
                if not opt or opt.startswith(","):
                    continue
                cleaned_lines.append(line if line.endswith("\n") else line + "\n")
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                cleaned_lines.append(line if line.endswith("\n") else line + "\n")
                continue
            # 其他无效行跳过
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(cleaned_lines)
        # 强制同步到磁盘，确保后续 DIDConfig 等生成器 load() 时能读到最新配置（Windows 无 os.sync，忽略）
        try:
            if hasattr(os, "sync"):
                os.sync()
        except Exception:
            pass

        # 根据最新配置生成 uds.txt（若配置了 uds_ecu_qualifier 和 output_dir）
        try:
            self._write_uds_files(config, only_domains=uds_domains)
        except Exception as e:
            print(f"根据配置生成 uds.txt 失败: {e}")
        # 中央域：生成 PowerRelayConfig.txt、IgnitionCycle.txt 到 output_dir/Configuration/
        try:
            if uds_domains is None or "CENTRAL" in (uds_domains or []):
                self._write_central_config_files(config)
        except Exception as e:
            print(f"根据配置生成中央域配置文件失败: {e}")
