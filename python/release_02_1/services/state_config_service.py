#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前端 UI state 与 `Configuration.ini` 之间的业务服务（`StateConfigService`）。

职责概要：
- 将各 Tab 采集的 state（与 `services.config_constants` 中键名一致）**合并**到内存中
  `configparser.ConfigParser` 的对应**节/选项**；与 **LR_REAR / CENTRAL / DTC** 分域、UART/SOA/点火等
  专项字段对齐，避免在路由里写散落的 `cfg.set`。
- 在「自动保存 / 一键生成前」等路径中 **持久化**（经 `ConfigManager` 格式化写盘），
  并可依据 state 计算 **各域一键生成** 应打开的 CAN/XML/DID/CIN/SOA/UART 开关（`get_*_generation_flags`）。

不直接处理 HTTP；由 `web/routes`、`GenerationRouteService` 等调用。常量与节名尽量来自
`config_constants`，与《架构》中 `StateConfigService` 描述一致。
"""

from __future__ import annotations

import configparser
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from services.config_constants import (
    CENTRAL_FILTER_KEY_MAP,
    CENTRAL_STATE_KEYS,
    DTC_FILTER_KEY_MAP,
    DTC_STATE_KEYS,
    LR_EMPTY_STATE_OPTION_MAP,
    LR_STATE_KEYS,
    STATE_KEY_DTC_CIN_EXCEL,
    STATE_KEY_DTC_CAN_INPUT,
    STATE_KEY_DTC_DIDCONFIG_EXCEL,
    STATE_KEY_DTC_DIDINFO_EXCEL,
    STATE_KEY_DTC_IO_EXCEL,
    STATE_KEY_DTC_IO_SELECTED_SHEETS,
    STATE_KEY_DTC_SRV_EXCEL,
    STATE_KEY_DTC_UDS_ECU_QUALIFIER,
    STATE_KEY_DTC_LEVELS,
    STATE_KEY_DTC_LOG_LEVEL,
    STATE_KEY_DTC_MODELS,
    STATE_KEY_DTC_OUT_ROOT,
    STATE_KEY_DTC_PLATFORMS,
    STATE_KEY_DTC_SELECTED_SHEETS,
    STATE_KEY_DTC_TARGET_VERSIONS,
    STATE_KEY_LR_CAN_INPUT,
    STATE_KEY_LR_CIN_EXCEL,
    STATE_KEY_LR_DIDCONFIG_EXCEL,
    STATE_KEY_LR_DIDINFO_EXCEL,
    STATE_KEY_LR_IO_EXCEL,
    STATE_KEY_LR_SRV_EXCEL,
    STATE_KEY_LR_LEVELS,
    STATE_KEY_LR_LOG_LEVEL,
    STATE_KEY_LR_MODELS,
    STATE_KEY_LR_OUT_ROOT,
    STATE_KEY_LR_PLATFORMS,
    STATE_KEY_LR_SELECTED_SHEETS,
    STATE_KEY_LR_TARGET_VERSIONS,
    STATE_KEY_CENTRAL_CAN_INPUT,
    STATE_KEY_CENTRAL_IGN_CURRENT,
    STATE_KEY_CENTRAL_IGN_WAIT_TIME,
    STATE_KEY_CENTRAL_LOG_LEVEL,
    STATE_KEY_CENTRAL_LOGIN_PASSWORD,
    STATE_KEY_CENTRAL_LOGIN_USERNAME,
    STATE_KEY_CENTRAL_OUT_ROOT,
    STATE_KEY_CENTRAL_SELECTED_SHEETS,
    STATE_KEY_CENTRAL_SRV_EXCEL,
    STATE_KEY_CENTRAL_UART,
    STATE_KEY_CENTRAL_UART_COMM,
    STATE_KEY_CENTRAL_UDS_ECU_QUALIFIER,
    OPTION_C_IG,
    OPTION_C_PW,
    OPTION_C_PWR,
    OPTION_C_RLY,
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
    OPTION_SRV_EXCEL,
    OPTION_UDS_ECU_QUALIFIER,
    OPTION_UART_EXCEL,
    SECTION_CENTRAL,
    SECTION_DTC,
    SECTION_DTC_CONFIG_ENUM,
    SECTION_DTC_IOMAPPING,
    SECTION_IGNITION_CYCLE,
    SECTION_LR_REAR,
    UART_COMM_CFG_KEYS,
    UART_COMM_KEY_MAP,
    cin_input_excel_value_from_ui_path,
    input_excel_value_from_ui_path,
    didinfo_inputs_value_from_ui_single_path,
    io_inputs_value_from_ui_single_path,
)
from services.config_manager import ConfigManager
from services.config_service import ConfigPaths, ConfigService


@dataclass(frozen=True)
class LrDtcBundleStateKeys:
    """左右后域与 DTC 共用的「一键生成」 state 键名元组（仅键字符串不同，语义一致）。"""

    didconfig_excel: str
    didinfo_excel: str
    cin_excel: str
    srv_excel: str


LR_REAR_BUNDLE_STATE_KEYS = LrDtcBundleStateKeys(
    STATE_KEY_LR_DIDCONFIG_EXCEL,
    STATE_KEY_LR_DIDINFO_EXCEL,
    STATE_KEY_LR_CIN_EXCEL,
    STATE_KEY_LR_SRV_EXCEL,
)

DTC_DOMAIN_BUNDLE_STATE_KEYS = LrDtcBundleStateKeys(
    STATE_KEY_DTC_DIDCONFIG_EXCEL,
    STATE_KEY_DTC_DIDINFO_EXCEL,
    STATE_KEY_DTC_CIN_EXCEL,
    STATE_KEY_DTC_SRV_EXCEL,
)


@dataclass(frozen=True)
class StandardDomainUiBinding:
    """
    中央域与 DTC 在「用例/输出/筛选项」上共享的写配置模式（一套 binding 传两处）。

    字段说明：section 为 INI 节名；各 `*_key` 为 state 中对应键名；filter_pairs 为
    (state 键, option 名) 列表，供 `apply_filter_option_state` 使用；
    `clear_selected_sheets_with_input` 为 True 时，在输入被清空时同步清空已选 sheet 选项。
    """

    section: str
    input_key: str
    out_root_key: str
    selected_sheets_key: str
    log_level_key: str
    uds_key: str
    filter_pairs: list[tuple[str, str]]
    clear_selected_sheets_with_input: bool = False


CENTRAL_DOMAIN_UI_BINDING = StandardDomainUiBinding(
    section=SECTION_CENTRAL,
    input_key=STATE_KEY_CENTRAL_CAN_INPUT,
    out_root_key=STATE_KEY_CENTRAL_OUT_ROOT,
    selected_sheets_key=STATE_KEY_CENTRAL_SELECTED_SHEETS,
    log_level_key=STATE_KEY_CENTRAL_LOG_LEVEL,
    uds_key=STATE_KEY_CENTRAL_UDS_ECU_QUALIFIER,
    filter_pairs=list(CENTRAL_FILTER_KEY_MAP),
    clear_selected_sheets_with_input=True,
)

DTC_DOMAIN_UI_BINDING = StandardDomainUiBinding(
    section=SECTION_DTC,
    input_key=STATE_KEY_DTC_CAN_INPUT,
    out_root_key=STATE_KEY_DTC_OUT_ROOT,
    selected_sheets_key=STATE_KEY_DTC_SELECTED_SHEETS,
    log_level_key=STATE_KEY_DTC_LOG_LEVEL,
    uds_key=STATE_KEY_DTC_UDS_ECU_QUALIFIER,
    filter_pairs=list(DTC_FILTER_KEY_MAP),
    clear_selected_sheets_with_input=False,
)


class StateConfigService:
    """
    将前端 state 合并进主配置、写盘，并提供生成编排用的布尔开关解析。

    与 `ConfigService.update_lr_rear_and_related` 等协作，保持「**读—改—存**」
    在固定节结构下完成（参见客户配置保存相关需求）。
    """

    def __init__(
        self,
        base_dir: str,
        *,
        config_manager: ConfigManager,
        config_service: ConfigService,
    ) -> None:
        """
        参数：
            base_dir — 工程根目录。
            config_manager — 主/固定配置读写与格式化落盘。
            config_service — 对 LR 预设等的高层封装，与本类共同写 `ConfigParser`。
        返回：无。
        """
        self.base_dir = base_dir
        self.config_manager = config_manager
        self.config_service = config_service

    @classmethod
    def from_base_dir(cls, base_dir: str) -> "StateConfigService":
        """
        以工程根构造默认的 `ConfigManager` + `ConfigService` 并返回本服务实例。

        参数：base_dir — 工程根目录。

        返回：配置好的 `StateConfigService`。
        """
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
    def ensure_sections(cfg: configparser.ConfigParser, sections: tuple[str, ...]) -> None:
        """
        若缺则添加 INI 节，避免对不存在节 `set` 抛错。

        参数：cfg — 内存中的配置；sections — 节名元组。返回：无。
        """
        for section_name in sections:
            if not cfg.has_section(section_name):
                cfg.add_section(section_name)

    @staticmethod
    def flush_config_to_disk() -> None:
        """
        在支持的平台上调用 `os.sync()`，尽量让刚写入的配置落盘到介质（**尽力而为**，忽略异常）。

        参数：无。返回：无。
        """
        try:
            if hasattr(os, "sync"):
                os.sync()
        except Exception:
            pass

    @staticmethod
    def state_value_to_text(item_value: Any) -> str:
        """
        将前端单字段（字符串或 list）规范成写入 INI 的文本；list 用英文逗号拼接，空表为 ``"ALL"``。

        参数：item_value — 原始 state 值，可为 `None`、str、list 等。

        返回：适合 `cfg.set` 的 str；`None` 时返回 `""`。
        """
        if item_value is None:
            return ""
        if isinstance(item_value, list):
            return ",".join(str(item) for item in item_value) if item_value else "ALL"
        return str(item_value).strip()

    @classmethod
    def build_lr_preset_from_state(cls, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        从当前 LR 区 state 构造传给 `ConfigService.update_lr_rear_and_related` 的扁平 dict 预设。

        参数：state — 含 `STATE_KEY_LR_*` 等键的 dict。

        返回：各键为字符串的预设，缺省为 ``ALL`` / ``info`` 等约定默认值已填。
        """
        return {
            STATE_KEY_LR_CAN_INPUT: cls.state_value_to_text(state.get(STATE_KEY_LR_CAN_INPUT)),
            STATE_KEY_LR_OUT_ROOT: cls.state_value_to_text(state.get(STATE_KEY_LR_OUT_ROOT)),
            STATE_KEY_LR_LEVELS: cls.state_value_to_text(state.get(STATE_KEY_LR_LEVELS)) or "ALL",
            STATE_KEY_LR_PLATFORMS: cls.state_value_to_text(state.get(STATE_KEY_LR_PLATFORMS)),
            STATE_KEY_LR_MODELS: cls.state_value_to_text(state.get(STATE_KEY_LR_MODELS)),
            STATE_KEY_LR_TARGET_VERSIONS: cls.state_value_to_text(state.get(STATE_KEY_LR_TARGET_VERSIONS)),
            STATE_KEY_LR_SELECTED_SHEETS: cls.state_value_to_text(state.get(STATE_KEY_LR_SELECTED_SHEETS)),
            STATE_KEY_LR_LOG_LEVEL: cls.state_value_to_text(state.get(STATE_KEY_LR_LOG_LEVEL)) or "info",
            STATE_KEY_LR_DIDINFO_EXCEL: cls.state_value_to_text(state.get(STATE_KEY_LR_DIDINFO_EXCEL)),
            STATE_KEY_LR_CIN_EXCEL: cls.state_value_to_text(state.get(STATE_KEY_LR_CIN_EXCEL)),
            STATE_KEY_LR_SRV_EXCEL: cls.state_value_to_text(state.get(STATE_KEY_LR_SRV_EXCEL)),
            STATE_KEY_LR_IO_EXCEL: cls.state_value_to_text(state.get(STATE_KEY_LR_IO_EXCEL)),
            STATE_KEY_LR_DIDCONFIG_EXCEL: cls.state_value_to_text(state.get(STATE_KEY_LR_DIDCONFIG_EXCEL)),
        }

    @staticmethod
    def has_any_lr_state(state: Dict[str, Any]) -> bool:
        """
        判断本次 payload 是否包含任一「左右后域」相关键，以决定是否走 LR 写回分支。

        参数：state — 当前 merge 后的 state。返回：出现任一键则为 True。
        """
        return any(item_key in state for item_key in LR_STATE_KEYS)

    @staticmethod
    def clear_option_if_present(cfg: configparser.ConfigParser, section: str, option: str) -> None:
        """
        若节存在，将 `option` 置空串（不删除节）。

        参数：cfg, section, option — 目标配置与节/选项名。返回：无。
        """
        if cfg.has_section(section):
            cfg.set(section, option, "")

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
        """
        将 `raw_value` 规范化后写入 `section/option`；空值时可清空或按策略忽略。

        参数：
            raw_value — 来自 state 的原始值，truthy 时写回；`""` 且 `remove_on_empty`
                为 True 时调用 `clear_option_if_present`。
            lowercase — 为 True 时写入小写（如 log level）。

        返回：无。
        """
        if raw_value:
            item_value = str(raw_value).strip()
            cfg.set(section, option, item_value.lower() if lowercase else item_value)
        elif raw_value == "" and remove_on_empty:
            cls.clear_option_if_present(cfg, section, option)

    @staticmethod
    def apply_filter_option_state(
        cfg: configparser.ConfigParser,
        section: str,
        state: Dict[str, Any],
        filter_key_map,
    ) -> None:
        """
        将「等级/平台/车型…」等筛选项从 state 写入指定节的对应 option；列表则逗号拼接。

        参数：cfg — 配置；section — 目标节；state — 当前 state；filter_key_map — 可迭代
        `(state 键, option 名)`。返回：无。
        """
        for state_key, option_name in filter_key_map:
            item_value = state.get(state_key)
            if item_value is None:
                continue
            normalized = ",".join(item_value) if isinstance(item_value, list) else str(item_value)
            cfg.set(section, option_name, normalized.strip() if isinstance(normalized, str) else normalized)

    @classmethod
    def apply_standard_domain_state(
        cls,
        cfg: configparser.ConfigParser,
        state: Dict[str, Any],
        binding: StandardDomainUiBinding,
    ) -> None:
        """
        对 CENTRAL 或 DTC 应用「用例表 + 输出 + 筛选项 + 日志级别 + UDS」等标准写回块。

        参数：cfg — 配置；state — 当前 state；binding — `CENTRAL_DOMAIN_UI_BINDING` 或
        `DTC_DOMAIN_UI_BINDING`。返回：无。
        """
        section = binding.section
        cls.ensure_sections(cfg, (section,))

        cls.set_text_option(
            cfg,
            section,
            OPTION_INPUT_EXCEL,
            state.get(binding.input_key),
            remove_on_empty=True,
        )
        if state.get(binding.input_key) == "" and binding.clear_selected_sheets_with_input:
            cls.clear_option_if_present(cfg, section, OPTION_SELECTED_SHEETS)

        cls.set_text_option(cfg, section, OPTION_OUTPUT_DIR, state.get(binding.out_root_key))
        cls.apply_filter_option_state(cfg, section, state, binding.filter_pairs)
        cls.set_text_option(
            cfg,
            section,
            OPTION_SELECTED_SHEETS,
            state.get(binding.selected_sheets_key),
            remove_on_empty=True,
        )
        cls.set_text_option(
            cfg,
            section,
            OPTION_LOG_LEVEL_MIN,
            state.get(binding.log_level_key),
            lowercase=True,
        )
        cls.set_text_option(cfg, section, OPTION_UDS_ECU_QUALIFIER, state.get(binding.uds_key))

    @staticmethod
    def is_configured_c_pwr(payload_data: Any) -> bool:
        """
        判断中央域「充电/电源板」类 JSON 是否已配置到应写入 `OPTION_C_PWR` 的程度（含有效 port）。

        参数：payload_data — 前端下发明文字典或 None。返回：可序列化落盘为 True，否则 False。
        """
        return isinstance(payload_data, dict) and bool((payload_data.get("port") or "").strip())

    @staticmethod
    def is_configured_c_rly(relays: Any) -> bool:
        """
        判断继电器列表 JSON 是否已形成“有效继电器配置”。

        参数：relays — 列表或他类型。返回：可写入 `OPTION_C_RLY` 为 True。
        """
        if not isinstance(relays, list) or len(relays) == 0:
            return False
        # 与 ConfigManager.load_central_ui_json_fields / has_relay_config 保持同一口径：
        # 仅当存在有效 port 或 relayID/id 时，才视为“已配置”。
        # 避免仅有 relayType/默认 coilStatuses 骨架时被误判为已配置并回写残留。
        return any(ConfigManager.has_relay_config(relay) for relay in relays)

    @staticmethod
    def is_configured_ig_pw(payload_data: Any) -> bool:
        """
        判断点火/功率类 JSON 是否含设备类型或通道号等，用于 `OPTION_C_IG` / `OPTION_C_PW`。

        参数：payload_data — 字典或 None。返回：应序列化落盘为 True 否则 False。
        """
        return isinstance(payload_data, dict) and bool(payload_data.get("equipmentType") or payload_data.get("channelNumber"))

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
        """
        若 `is_configured(raw_value)` 为真则 `json.dumps` 写入 option，否则清空该选项。

        参数：is_configured — 可调用对象，签名为 ``(raw_value) -> bool``。raw_value 为
        `None` 时直接返回不写。返回：无（异常时静默忽略，保证保存不抛）。
        """
        if raw_value is None:
            return
        try:
            if is_configured(raw_value):
                cfg.set(section, option, json.dumps(raw_value, ensure_ascii=False))
            else:
                cls.clear_option_if_present(cfg, section, option)
        except Exception:
            pass

    @classmethod
    def remove_mapped_options_on_empty_state(
        cls,
        cfg: configparser.ConfigParser,
        state: Dict[str, Any],
        empty_option_map: dict[str, list[tuple[str, str]]],
    ) -> None:
        """
        当某 state 键被置为 ``""`` 时，按表清空其映射的多处 INI 选项（置空串）。

        参数：empty_option_map — `state 键` → `[(节, 选项), ...]`。返回：无。
        """
        for state_key, targets in empty_option_map.items():
            if state.get(state_key) != "":
                continue
            for section_name, option_name in targets:
                cls.clear_option_if_present(cfg, section_name, option_name)

    @classmethod
    def sync_uart_comm_options(
        cls,
        cfg: configparser.ConfigParser,
        uart_comm: Optional[Dict[str, Any]],
    ) -> None:
        """
        将前端的 `c_uart_comm` 同步到 `[CENTRAL]` 下各 UART 相关键；全空时按策略清空。

        参数：cfg — 配置；uart_comm — 字典或 None。返回：无。
        """
        has_uart_in_cfg = cfg.has_section(SECTION_CENTRAL) and any(
            cfg.has_option(SECTION_CENTRAL, item_key) for item_key in UART_COMM_CFG_KEYS
        )
        port_set = bool((uart_comm.get("port") or "").strip()) if uart_comm else False
        if not (has_uart_in_cfg or port_set):
            return

        if uart_comm and port_set:
            for source_key, cfg_key in UART_COMM_KEY_MAP.items():
                if source_key in uart_comm:
                    cfg.set(SECTION_CENTRAL, cfg_key, str(uart_comm.get(source_key) or "").strip())
            return

        for cfg_key in UART_COMM_CFG_KEYS:
            cls.clear_option_if_present(cfg, SECTION_CENTRAL, cfg_key)

    @classmethod
    def sync_ignition_cycle_options(
        cls,
        cfg: configparser.ConfigParser,
        state: Dict[str, Any],
    ) -> None:
        """
        将点火等待时间/电流等写入 `[CENTRAL]` 与 `[IGNITION_CYCLE]` 对应项（成对、可清空）。

        参数：cfg — 配置；state — 含 `STATE_KEY_CENTRAL_IGN_*` 的 state。返回：无。
        """
        has_wait_time = state.get(STATE_KEY_CENTRAL_IGN_WAIT_TIME) is not None
        has_current = state.get(STATE_KEY_CENTRAL_IGN_CURRENT) is not None
        if not (has_wait_time or has_current):
            return

        ign_waittime = str(state.get(STATE_KEY_CENTRAL_IGN_WAIT_TIME) or "").strip()
        ign_current = str(state.get(STATE_KEY_CENTRAL_IGN_CURRENT) or "").strip()
        has_any_value = bool(ign_waittime or ign_current)
        if has_any_value:
            cls.ensure_sections(cfg, (SECTION_IGNITION_CYCLE,))

        if has_wait_time:
            cls.set_text_option(
                cfg,
                SECTION_CENTRAL,
                OPTION_IGN_WAITTIME,
                ign_waittime,
                remove_on_empty=True,
            )
            cls.set_text_option(
                cfg,
                SECTION_IGNITION_CYCLE,
                OPTION_IGNITION_CYCLE_WAIT_TIME,
                ign_waittime,
                remove_on_empty=True,
            )

        if has_current:
            cls.set_text_option(
                cfg,
                SECTION_CENTRAL,
                OPTION_IGN_CURRENT,
                ign_current,
                remove_on_empty=True,
            )
            cls.set_text_option(
                cfg,
                SECTION_IGNITION_CYCLE,
                OPTION_IGNITION_CYCLE_CURRENT,
                ign_current,
                remove_on_empty=True,
            )

    @classmethod
    def sync_dtc_domain_inputs(
        cls,
        cfg: configparser.ConfigParser,
        state: Dict[str, Any],
    ) -> None:
        """
        在标准域写回之后，补全 DTC 特有条目：DIDInfo/CIN/IO 映射/ConfigEnum 等节的路径与表。

        参数：cfg — 配置；state — 含 `STATE_KEY_DTC_*`。返回：无。
        """
        dtc_didinfo_excel = state.get(STATE_KEY_DTC_DIDINFO_EXCEL)
        cls.set_text_option(
            cfg,
            SECTION_DTC,
            OPTION_DIDINFO_INPUTS,
            didinfo_inputs_value_from_ui_single_path(dtc_didinfo_excel) if dtc_didinfo_excel else "",
            remove_on_empty=True,
        )

        dtc_cin_excel = state.get(STATE_KEY_DTC_CIN_EXCEL)
        cls.set_text_option(
            cfg,
            SECTION_DTC,
            OPTION_CIN_INPUT_EXCEL,
            cin_input_excel_value_from_ui_path(dtc_cin_excel) if dtc_cin_excel else "",
            remove_on_empty=True,
        )

        if STATE_KEY_DTC_IO_EXCEL in state or STATE_KEY_DTC_IO_SELECTED_SHEETS in state:
            cls.ensure_sections(cfg, (SECTION_DTC_IOMAPPING,))
            io_excel_path = input_excel_value_from_ui_path(state.get(STATE_KEY_DTC_IO_EXCEL))
            io_selected_sheets = str(state.get(STATE_KEY_DTC_IO_SELECTED_SHEETS) or "").strip()
            io_inputs_value = (
                f"{io_excel_path} | {io_selected_sheets if io_selected_sheets else '*'}"
                if io_excel_path
                else ""
            )
            cls.set_text_option(
                cfg,
                SECTION_DTC_IOMAPPING,
                OPTION_INPUTS,
                io_inputs_value,
                remove_on_empty=True,
            )

        if STATE_KEY_DTC_DIDCONFIG_EXCEL in state:
            cls.ensure_sections(cfg, (SECTION_DTC_CONFIG_ENUM,))
            dtc_didconfig_excel = state.get(STATE_KEY_DTC_DIDCONFIG_EXCEL)
            cls.set_text_option(
                cfg,
                SECTION_DTC_CONFIG_ENUM,
                OPTION_INPUTS,
                io_inputs_value_from_ui_single_path(dtc_didconfig_excel) if dtc_didconfig_excel else "",
                remove_on_empty=True,
            )

    def apply_state_to_config(
        self,
        state: Dict[str, Any],
        cfg: configparser.ConfigParser,
        *,
        skip_lr_rear: bool = False,
    ) -> None:
        """
        将完整 state 合并到内存 `cfg`：LR、CENTRAL、DTC 分块处理，不单独写盘。

        参数：
            state — 前端合并后的键值对。
            cfg — 已 load 的 `ConfigParser`（就地修改）。
            skip_lr_rear — 为 True 时跳过左右后区写回（如中央仅保存、避免误改 LR 节）。

        返回：无。
        """
        self.ensure_sections(
            cfg,
            (
                SECTION_LR_REAR,
                SECTION_CENTRAL,
                SECTION_DTC,
                SECTION_DTC_IOMAPPING,
                SECTION_DTC_CONFIG_ENUM,
                SECTION_IGNITION_CYCLE,
            ),
        )
        if not skip_lr_rear and self.has_any_lr_state(state):
            preset = self.build_lr_preset_from_state(state)
            self.config_service.update_lr_rear_and_related(cfg, preset)
            if state.get(OPTION_UDS_ECU_QUALIFIER):
                cfg.set(
                    SECTION_LR_REAR,
                    OPTION_UDS_ECU_QUALIFIER,
                    str(state[OPTION_UDS_ECU_QUALIFIER]).strip(),
                )
            if cfg.has_section(SECTION_LR_REAR):
                self.set_text_option(
                    cfg,
                    SECTION_LR_REAR,
                    OPTION_SRV_EXCEL,
                    state.get(STATE_KEY_LR_SRV_EXCEL),
                    remove_on_empty=True,
                )
                self.remove_mapped_options_on_empty_state(cfg, state, LR_EMPTY_STATE_OPTION_MAP)

        if any(item_key in state for item_key in CENTRAL_STATE_KEYS):
            self.apply_standard_domain_state(cfg, state, CENTRAL_DOMAIN_UI_BINDING)
            self.set_text_option(
                cfg,
                SECTION_CENTRAL,
                OPTION_UART_EXCEL,
                state.get(STATE_KEY_CENTRAL_UART),
                remove_on_empty=True,
            )
            self.set_text_option(
                cfg,
                SECTION_CENTRAL,
                OPTION_SRV_EXCEL,
                state.get(STATE_KEY_CENTRAL_SRV_EXCEL),
                remove_on_empty=True,
            )
            uart_comm_raw = state.get(STATE_KEY_CENTRAL_UART_COMM)
            uart_comm = uart_comm_raw if isinstance(uart_comm_raw, dict) else None
            self.sync_uart_comm_options(cfg, uart_comm)
            self.sync_ignition_cycle_options(cfg, state)

            if state.get(STATE_KEY_CENTRAL_LOGIN_USERNAME) is not None:
                cfg.set(
                    SECTION_CENTRAL,
                    OPTION_LOGIN_USERNAME,
                    str(state.get(STATE_KEY_CENTRAL_LOGIN_USERNAME) or "").strip(),
                )
            if state.get(STATE_KEY_CENTRAL_LOGIN_PASSWORD) is not None:
                cfg.set(
                    SECTION_CENTRAL,
                    OPTION_LOGIN_PASSWORD,
                    str(state.get(STATE_KEY_CENTRAL_LOGIN_PASSWORD) or "").strip(),
                )

            self.set_json_option_or_remove(
                cfg,
                SECTION_CENTRAL,
                OPTION_C_PWR,
                state.get(OPTION_C_PWR),
                is_configured=self.is_configured_c_pwr,
            )
            self.set_json_option_or_remove(
                cfg,
                SECTION_CENTRAL,
                OPTION_C_RLY,
                state.get(OPTION_C_RLY),
                is_configured=self.is_configured_c_rly,
            )
            self.set_json_option_or_remove(
                cfg,
                SECTION_CENTRAL,
                OPTION_C_IG,
                state.get(OPTION_C_IG),
                is_configured=self.is_configured_ig_pw,
            )
            self.set_json_option_or_remove(
                cfg,
                SECTION_CENTRAL,
                OPTION_C_PW,
                state.get(OPTION_C_PW),
                is_configured=self.is_configured_ig_pw,
            )

        if any(item_key in state for item_key in DTC_STATE_KEYS):
            self.apply_standard_domain_state(cfg, state, DTC_DOMAIN_UI_BINDING)
            self.sync_dtc_domain_inputs(cfg, state)
            self.set_text_option(
                cfg,
                SECTION_DTC,
                OPTION_SRV_EXCEL,
                state.get(STATE_KEY_DTC_SRV_EXCEL),
                remove_on_empty=True,
            )

    def persist_state_config(
        self,
        state: Dict[str, Any],
        *,
        uds_domains=None,
        skip_lr_rear: bool = False,
        flush_disk: bool = False,
        extra_write_path: Optional[str] = None,
    ) -> tuple[ConfigManager, configparser.ConfigParser]:
        """
        加载主配置，应用 state 后经 `ConfigManager` 写回磁盘（可选额外路径与 fsync）。

        参数：
            uds_domains — 传给 `save_formatted_config` 的 UDS 节列表，可为 None。
            flush_disk — 为 True 时调用 `flush_config_to_disk`。
            extra_write_path — 非空时额外写一份到该路径（如导出/备份）。

        返回：``(self.config_manager, 合并后的 configparser)``。
        """
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
        """
        在启动某域生成前，若有 state 则先合并并落盘再返回 `ConfigParser`；无 state 则只读当前文件。

        参数：
            state — 可空；非空时触发 `persist_state_config` 且 `flush_disk=True`。
            uds_domain — 单域标识，供保存时 UDS 相关节处理。
            skip_lr_rear — 同 `apply_state_to_config`。

        返回：供生成器使用的合并后配置（内存中对象）。
        """
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
    def bundle_run_flags_for_lr_dtc_state(
        state: Dict[str, Any],
        state_key_bundle: LrDtcBundleStateKeys,
    ) -> dict[str, bool]:
        """
        LR_REAR 与 DTC 共用的「一键生成」子任务开关：CAN/XML 常开，DID/CIN/SOA 依路径非空决定。

        参数：state — 当前 state；state_key_bundle — `LR_REAR_BUNDLE_STATE_KEYS` 或
        `DTC_DOMAIN_BUNDLE_STATE_KEYS`。

        返回：``run_can`` / ``run_xml`` / ``run_did`` / ``run_cin`` / ``run_soa`` 布尔 dict。
        """
        has_didconfig = bool((state.get(state_key_bundle.didconfig_excel) or "").strip())
        has_didinfo = bool((state.get(state_key_bundle.didinfo_excel) or "").strip())
        return {
            "run_can": True,
            "run_xml": True,
            "run_did": has_didconfig or has_didinfo,
            "run_cin": bool(state.get(state_key_bundle.cin_excel)),
            "run_soa": bool((state.get(state_key_bundle.srv_excel) or "").strip()),
        }

    @staticmethod
    def get_lr_generation_flags(state: Dict[str, Any]) -> dict[str, bool]:
        """
        左右后域一键生成用的编排开关（`bundle_run_flags_for_lr_dtc_state` + LR 键名）。

        参数：state — 含 LR DID/CIN/SOA 等路径。返回：见 `bundle_run_flags_for_lr_dtc_state`。
        """
        return StateConfigService.bundle_run_flags_for_lr_dtc_state(state, LR_REAR_BUNDLE_STATE_KEYS)

    @staticmethod
    def get_dtc_generation_flags(state: Dict[str, Any]) -> dict[str, bool]:
        """
        DTC 域一键生成用的编排开关（`bundle_run_flags_for_lr_dtc_state` + DTC 键名）。

        参数：state — 含 DTC 侧 Excel 路径。返回：见 `bundle_run_flags_for_lr_dtc_state`。
        """
        return StateConfigService.bundle_run_flags_for_lr_dtc_state(state, DTC_DOMAIN_BUNDLE_STATE_KEYS)

    @staticmethod
    def get_central_generation_flags(state: Dict[str, Any]) -> dict[str, bool]:
        """
        与 `collectCurrentState()` 对齐：中央域一键生成时子任务开关（含 UART 条件）。

        参数：state — 含 `c_uart`（UART 矩阵路径）、`c_uart_comm`（含 `port` 则视为要跑 UART
        步）、`c_srv` 对应服务矩阵等。

        返回：``run_can`` / ``run_xml`` 为 True；``run_uart`` 在矩阵或串口已配置时为 True；
        ``run_soa`` 在服务矩阵路径非空时为 True。
        """
        c_uart = (state.get(STATE_KEY_CENTRAL_UART) or "").strip()
        c_srv = (state.get(STATE_KEY_CENTRAL_SRV_EXCEL) or "").strip()
        uart_comm_raw = state.get(STATE_KEY_CENTRAL_UART_COMM)
        uart_comm = uart_comm_raw if isinstance(uart_comm_raw, dict) else None
        port_set = bool((uart_comm.get("port") or "").strip()) if uart_comm else False
        run_uart = bool(c_uart) or port_set
        return {
            "run_can": True,
            "run_xml": True,
            "run_uart": run_uart,
            "run_soa": bool(c_srv),
        }
