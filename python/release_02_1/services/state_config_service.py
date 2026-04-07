#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前端 state 与配置文件之间的业务服务。"""

from __future__ import annotations

import configparser
import json
import os
from typing import Any, Dict, Optional

from services.config_constants import (
    CENTRAL_FILTER_KEY_MAP,
    CENTRAL_STATE_KEYS,
    DTC_FILTER_KEY_MAP,
    DTC_STATE_KEYS,
    LR_EMPTY_STATE_OPTION_MAP,
    LR_STATE_KEYS,
    OPTION_CIN_INPUT_EXCEL,
    OPTION_DIDINFO_INPUTS,
    OPTION_INPUT_EXCEL,
    OPTION_INPUTS,
    OPTION_IGNITION_CYCLE_CURRENT,
    OPTION_IGNITION_CYCLE_WAIT_TIME,
    OPTION_IGN_CURRENT,
    OPTION_IGN_WAITTIME,
    OPTION_LOGIN_PASSWORD,
    OPTION_LOGIN_USERNAME,
    OPTION_LOG_LEVEL_MIN,
    OPTION_OUTPUT_DIR,
    OPTION_SELECTED_SHEETS,
    OPTION_UDS_ECU_QUALIFIER,
    OPTION_UART_EXCEL,
    SECTION_CENTRAL,
    SECTION_DTC,
    SECTION_DTC_CONFIG_ENUM,
    SECTION_DTC_IOMAPPING,
    SECTION_IGNITION_CYCLE,
    UART_COMM_CFG_KEYS,
    UART_COMM_KEY_MAP,
)
from services.config_manager import ConfigManager
from services.config_service import ConfigService


class StateConfigService:
    """封装前端 state 到 Configuration 的合并、落盘与生成前准备。"""

    def __init__(
        self,
        base_dir: str,
        *,
        config_manager: ConfigManager,
        config_service: ConfigService,
    ) -> None:
        self.base_dir = base_dir
        self.config_manager = config_manager
        self.config_service = config_service

    @classmethod
    def from_base_dir(cls, base_dir: str) -> "StateConfigService":
        config_manager = ConfigManager.from_base_dir(base_dir)
        return cls(
            base_dir=base_dir,
            config_manager=config_manager,
            config_service=ConfigService(
                ConfigPaths(base_dir=config_manager.base_dir, config_path=config_manager.config_path),
                config_manager=config_manager,
            ),
        )

    @staticmethod
    def flush_config_to_disk() -> None:
        try:
            if hasattr(os, "sync"):
                os.sync()
        except Exception:
            pass

    @staticmethod
    def state_value_to_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return ",".join(str(item) for item in value) if value else "ALL"
        return str(value).strip()

    @classmethod
    def build_lr_preset_from_state(cls, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "can_input": cls.state_value_to_text(state.get("can_input")),
            "out_root": cls.state_value_to_text(state.get("out_root")),
            "levels": cls.state_value_to_text(state.get("levels")) or "ALL",
            "platforms": cls.state_value_to_text(state.get("platforms")),
            "models": cls.state_value_to_text(state.get("models")),
            "target_versions": cls.state_value_to_text(state.get("target_versions")),
            "selected_sheets": cls.state_value_to_text(state.get("selected_sheets")),
            "log_level": cls.state_value_to_text(state.get("log_level")) or "info",
            "didinfo_excel": cls.state_value_to_text(state.get("didinfo_excel")),
            "cin_excel": cls.state_value_to_text(state.get("cin_excel")),
            "io_excel": cls.state_value_to_text(state.get("io_excel")),
            "didconfig_excel": cls.state_value_to_text(state.get("didconfig_excel")),
        }

    @staticmethod
    def has_any_lr_state(state: Dict[str, Any]) -> bool:
        return any(key in state for key in LR_STATE_KEYS)

    @staticmethod
    def remove_option_if_present(cfg: configparser.ConfigParser, section: str, option: str) -> None:
        if cfg.has_section(section) and cfg.has_option(section, option):
            cfg.remove_option(section, option)

    @classmethod
    def set_text_option(
        cls,
        cfg: configparser.ConfigParser,
        section: str,
        option: str,
        raw_value: Any,
        *,
        remove_on_empty: bool = False,
        lowercase: bool = False,
    ) -> None:
        if raw_value:
            value = str(raw_value).strip()
            cfg.set(section, option, value.lower() if lowercase else value)
        elif raw_value == "" and remove_on_empty:
            cls.remove_option_if_present(cfg, section, option)

    @staticmethod
    def apply_filter_option_state(
        cfg: configparser.ConfigParser,
        section: str,
        state: Dict[str, Any],
        filter_key_map,
    ) -> None:
        for state_key, option_name in filter_key_map:
            value = state.get(state_key)
            if value is None:
                continue
            normalized = ",".join(value) if isinstance(value, list) else str(value)
            cfg.set(section, option_name, normalized.strip() if isinstance(normalized, str) else normalized)

    @classmethod
    def apply_standard_domain_state(
        cls,
        cfg: configparser.ConfigParser,
        state: Dict[str, Any],
        *,
        section: str,
        input_key: str,
        out_root_key: str,
        selected_sheets_key: str,
        log_level_key: str,
        uds_key: str,
        filter_key_map,
        clear_selected_sheets_with_input: bool = False,
    ) -> None:
        if not cfg.has_section(section):
            cfg.add_section(section)

        cls.set_text_option(
            cfg,
            section,
            OPTION_INPUT_EXCEL,
            state.get(input_key),
            remove_on_empty=True,
        )
        if state.get(input_key) == "" and clear_selected_sheets_with_input:
            cls.remove_option_if_present(cfg, section, OPTION_SELECTED_SHEETS)

        cls.set_text_option(cfg, section, OPTION_OUTPUT_DIR, state.get(out_root_key))
        cls.apply_filter_option_state(cfg, section, state, filter_key_map)
        cls.set_text_option(
            cfg,
            section,
            OPTION_SELECTED_SHEETS,
            state.get(selected_sheets_key),
            remove_on_empty=True,
        )
        cls.set_text_option(
            cfg,
            section,
            OPTION_LOG_LEVEL_MIN,
            state.get(log_level_key),
            lowercase=True,
        )
        cls.set_text_option(cfg, section, OPTION_UDS_ECU_QUALIFIER, state.get(uds_key))

    @staticmethod
    def is_configured_c_pwr(data: Any) -> bool:
        return isinstance(data, dict) and bool((data.get("port") or "").strip())

    @staticmethod
    def is_configured_c_rly(relays: Any) -> bool:
        if not isinstance(relays, list) or len(relays) == 0:
            return False
        for relay in relays:
            if (
                relay.get("relayID")
                or relay.get("relayType")
                or (relay.get("coilStatuses") and len(relay.get("coilStatuses", [])) > 0)
                or relay.get("port")
            ):
                return True
        return False

    @staticmethod
    def is_configured_ig_pw(data: Any) -> bool:
        return isinstance(data, dict) and bool(data.get("equipmentType") or data.get("channelNumber"))

    @classmethod
    def set_json_option_or_remove(
        cls,
        cfg: configparser.ConfigParser,
        section: str,
        option: str,
        raw_value: Any,
        *,
        is_configured,
    ) -> None:
        if raw_value is None:
            return
        try:
            if is_configured(raw_value):
                cfg.set(section, option, json.dumps(raw_value, ensure_ascii=False))
            else:
                cls.remove_option_if_present(cfg, section, option)
        except Exception:
            pass

    def apply_state_to_config(
        self,
        state: Dict[str, Any],
        cfg: configparser.ConfigParser,
        *,
        skip_lr_rear: bool = False,
    ) -> None:
        if not skip_lr_rear and self.has_any_lr_state(state):
            preset = self.build_lr_preset_from_state(state)
            self.config_service.update_lr_rear_and_related(cfg, preset)
            if state.get("uds_ecu_qualifier"):
                if not cfg.has_section(SECTION_LR_REAR):
                    cfg.add_section(SECTION_LR_REAR)
                cfg.set(SECTION_LR_REAR, OPTION_UDS_ECU_QUALIFIER, str(state["uds_ecu_qualifier"]).strip())
            if cfg.has_section(SECTION_LR_REAR):
                for state_key, targets in LR_EMPTY_STATE_OPTION_MAP.items():
                    if state.get(state_key) == "":
                        for section_name, option_name in targets:
                            if cfg.has_section(section_name) and cfg.has_option(section_name, option_name):
                                cfg.remove_option(section_name, option_name)

        if any(key in state for key in CENTRAL_STATE_KEYS):
            self.apply_standard_domain_state(
                cfg,
                state,
                section=SECTION_CENTRAL,
                input_key="c_input",
                out_root_key="c_out_root",
                selected_sheets_key="c_selected_sheets",
                log_level_key="c_log_level",
                uds_key="c_uds_ecu_qualifier",
                filter_key_map=CENTRAL_FILTER_KEY_MAP,
                clear_selected_sheets_with_input=True,
            )
            self.set_text_option(
                cfg,
                SECTION_CENTRAL,
                OPTION_UART_EXCEL,
                state.get("c_uart"),
                remove_on_empty=True,
            )
            has_uart_in_cfg = cfg.has_section(SECTION_CENTRAL) and any(
                cfg.has_option(SECTION_CENTRAL, key) for key in UART_COMM_CFG_KEYS
            )
            uart_comm_raw = state.get("c_uart_comm")
            uart_comm = uart_comm_raw if isinstance(uart_comm_raw, dict) else None
            port_set = bool((uart_comm.get("port") or "").strip()) if uart_comm else False
            if has_uart_in_cfg or port_set:
                if uart_comm and port_set:
                    for src_key, cfg_key in UART_COMM_KEY_MAP.items():
                        if src_key in uart_comm:
                            cfg.set(SECTION_CENTRAL, cfg_key, str(uart_comm.get(src_key) or "").strip())
                elif has_uart_in_cfg:
                    for cfg_key in UART_COMM_CFG_KEYS:
                        if cfg.has_option(SECTION_CENTRAL, cfg_key):
                            cfg.remove_option(SECTION_CENTRAL, cfg_key)

            ign_waittime = str(state.get("c_ign_waitTime") or "").strip()
            ign_current = str(state.get("c_ign_current") or "").strip()
            if state.get("c_ign_waitTime") is not None or state.get("c_ign_current") is not None:
                if ign_waittime or ign_current:
                    if not cfg.has_section(SECTION_IGNITION_CYCLE):
                        cfg.add_section(SECTION_IGNITION_CYCLE)
                    if state.get("c_ign_waitTime") is not None:
                        cfg.set(SECTION_CENTRAL, OPTION_IGN_WAITTIME, ign_waittime)
                        cfg.set(SECTION_IGNITION_CYCLE, OPTION_IGNITION_CYCLE_WAIT_TIME, ign_waittime)
                    if state.get("c_ign_current") is not None:
                        cfg.set(SECTION_CENTRAL, OPTION_IGN_CURRENT, ign_current)
                        cfg.set(SECTION_IGNITION_CYCLE, OPTION_IGNITION_CYCLE_CURRENT, ign_current)
                else:
                    if cfg.has_section(SECTION_CENTRAL):
                        if cfg.has_option(SECTION_CENTRAL, OPTION_IGN_WAITTIME):
                            cfg.remove_option(SECTION_CENTRAL, OPTION_IGN_WAITTIME)
                        if cfg.has_option(SECTION_CENTRAL, OPTION_IGN_CURRENT):
                            cfg.remove_option(SECTION_CENTRAL, OPTION_IGN_CURRENT)
                    if cfg.has_section(SECTION_IGNITION_CYCLE):
                        if cfg.has_option(SECTION_IGNITION_CYCLE, OPTION_IGNITION_CYCLE_WAIT_TIME):
                            cfg.remove_option(SECTION_IGNITION_CYCLE, OPTION_IGNITION_CYCLE_WAIT_TIME)
                        if cfg.has_option(SECTION_IGNITION_CYCLE, OPTION_IGNITION_CYCLE_CURRENT):
                            cfg.remove_option(SECTION_IGNITION_CYCLE, OPTION_IGNITION_CYCLE_CURRENT)

            if state.get("c_login_username") is not None:
                cfg.set(SECTION_CENTRAL, OPTION_LOGIN_USERNAME, str(state.get("c_login_username") or "").strip())
            if state.get("c_login_password") is not None:
                cfg.set(SECTION_CENTRAL, OPTION_LOGIN_PASSWORD, str(state.get("c_login_password") or "").strip())

            self.set_json_option_or_remove(
                cfg,
                SECTION_CENTRAL,
                "c_pwr",
                state.get("c_pwr"),
                is_configured=self.is_configured_c_pwr,
            )
            self.set_json_option_or_remove(
                cfg,
                SECTION_CENTRAL,
                "c_rly",
                state.get("c_rly"),
                is_configured=self.is_configured_c_rly,
            )
            self.set_json_option_or_remove(
                cfg,
                SECTION_CENTRAL,
                "c_ig",
                state.get("c_ig"),
                is_configured=self.is_configured_ig_pw,
            )
            self.set_json_option_or_remove(
                cfg,
                SECTION_CENTRAL,
                "c_pw",
                state.get("c_pw"),
                is_configured=self.is_configured_ig_pw,
            )

        if any(key in state for key in DTC_STATE_KEYS):
            self.apply_standard_domain_state(
                cfg,
                state,
                section=SECTION_DTC,
                input_key="d_input",
                out_root_key="d_out_root",
                selected_sheets_key="d_selected_sheets",
                log_level_key="d_log_level",
                uds_key="d_uds_ecu_qualifier",
                filter_key_map=DTC_FILTER_KEY_MAP,
            )
            if state.get("d_didinfo_excel"):
                cfg.set(SECTION_DTC, OPTION_DIDINFO_INPUTS, f"{str(state['d_didinfo_excel']).strip()} | *")
            elif state.get("d_didinfo_excel") == "":
                if cfg.has_option(SECTION_DTC, OPTION_DIDINFO_INPUTS):
                    cfg.remove_option(SECTION_DTC, OPTION_DIDINFO_INPUTS)

            if state.get("d_cin_excel"):
                cfg.set(SECTION_DTC, OPTION_CIN_INPUT_EXCEL, str(state["d_cin_excel"]).strip())
            elif state.get("d_cin_excel") == "":
                if cfg.has_option(SECTION_DTC, OPTION_CIN_INPUT_EXCEL):
                    cfg.remove_option(SECTION_DTC, OPTION_CIN_INPUT_EXCEL)

            if "d_io_excel" in state or "d_io_selected_sheets" in state:
                if not cfg.has_section(SECTION_DTC_IOMAPPING):
                    cfg.add_section(SECTION_DTC_IOMAPPING)
                path = str(state.get("d_io_excel") or "").strip()
                sheets = str(state.get("d_io_selected_sheets") or "").strip()
                if path:
                    cfg.set(SECTION_DTC_IOMAPPING, OPTION_INPUTS, f"{path} | {sheets if sheets else '*'}")
                else:
                    if cfg.has_option(SECTION_DTC_IOMAPPING, OPTION_INPUTS):
                        cfg.remove_option(SECTION_DTC_IOMAPPING, OPTION_INPUTS)

            if state.get("d_didconfig_excel"):
                if not cfg.has_section(SECTION_DTC_CONFIG_ENUM):
                    cfg.add_section(SECTION_DTC_CONFIG_ENUM)
                cfg.set(SECTION_DTC_CONFIG_ENUM, OPTION_INPUTS, f"{str(state['d_didconfig_excel']).strip()} | *")
            elif state.get("d_didconfig_excel") == "":
                if cfg.has_section(SECTION_DTC_CONFIG_ENUM) and cfg.has_option(
                    SECTION_DTC_CONFIG_ENUM,
                    OPTION_INPUTS,
                ):
                    cfg.remove_option(SECTION_DTC_CONFIG_ENUM, OPTION_INPUTS)

    def persist_state_config(
        self,
        state: Dict[str, Any],
        *,
        uds_domains=None,
        skip_lr_rear: bool = False,
        flush_disk: bool = False,
        extra_write_path: Optional[str] = None,
    ) -> tuple[ConfigManager, configparser.ConfigParser]:
        config = self.config_manager.load_config()
        self.apply_state_to_config(state, config, skip_lr_rear=skip_lr_rear)
        self.config_manager.save_formatted_config(config, uds_domains=uds_domains)
        if extra_write_path:
            self.config_manager.save_formatted_config(config, config_path=extra_write_path)
        if flush_disk:
            self.flush_config_to_disk()
        return self.config_manager, config

    def prepare_generation_config(
        self,
        *,
        state: Dict[str, Any],
        uds_domain: str,
        skip_lr_rear: bool = False,
    ) -> configparser.ConfigParser:
        if state:
            _, config = self.persist_state_config(
                state,
                uds_domains=[uds_domain],
                skip_lr_rear=skip_lr_rear,
                flush_disk=True,
            )
            return config
        return self.config_manager.load_config()

    @staticmethod
    def get_lr_generation_flags(state: Dict[str, Any]) -> dict[str, bool]:
        return {
            "run_can": True,
            "run_xml": True,
            "run_did": True,
            "run_cin": bool(state.get("cin_excel")),
            "run_uart": bool(state.get("c_uart")),
        }

    @staticmethod
    def get_dtc_generation_flags(state: Dict[str, Any]) -> dict[str, bool]:
        return {
            "run_can": True,
            "run_xml": True,
            "run_cin": bool(state.get("d_cin_excel")),
        }
