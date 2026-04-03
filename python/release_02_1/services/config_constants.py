#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置节名、键名与前端 state 键的统一出口。

先集中最常改、最容易散落的常量，供路由层与配置服务共用，
避免后续做命名、路径、配置读写改造时重复搬迁字面量。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 配置节名
# ---------------------------------------------------------------------------

SECTION_LR_REAR = "LR_REAR"
SECTION_CENTRAL = "CENTRAL"
SECTION_DTC = "DTC"
SECTION_IOMAPPING = "IOMAPPING"
SECTION_DID_CONFIG = "DID_CONFIG"
SECTION_CONFIG_ENUM = "CONFIG_ENUM"
SECTION_DTC_IOMAPPING = "DTC_IOMAPPING"
SECTION_DTC_CONFIG_ENUM = "DTC_CONFIG_ENUM"
SECTION_IGNITION_CYCLE = "IgnitionCycle"
SECTION_PATHS = "PATHS"
SECTION_PATH = "PATH"
SECTION_FILTER = "FILTER"

# ---------------------------------------------------------------------------
# 常用配置项名
# ---------------------------------------------------------------------------

OPTION_INPUTS = "inputs"
OPTION_INPUT_EXCEL = "input_excel"
OPTION_OUTPUT_DIR = "output_dir"
OPTION_OUTPUT_FILENAME = "output_filename"
OPTION_SELECTED_SHEETS = "selected_sheets"
OPTION_LOG_LEVEL_MIN = "log_level_min"
OPTION_UDS_ECU_QUALIFIER = "uds_ecu_qualifier"
OPTION_CASE_LEVELS = "case_levels"
OPTION_CASE_PLATFORMS = "case_platforms"
OPTION_CASE_MODELS = "case_models"
OPTION_CASE_TARGET_VERSIONS = "case_target_versions"
OPTION_DIDINFO_INPUTS = "didinfo_inputs"
OPTION_CIN_INPUT_EXCEL = "cin_input_excel"

DEFAULT_DID_CONFIG_FILENAME = "DIDConfig.txt"
DEFAULT_DOMAIN_LR_REAR = SECTION_LR_REAR
VALID_LOG_LEVELS: tuple[str, ...] = ("info", "warning", "error")

# ---------------------------------------------------------------------------
# 各域 state 键常量（前端 collectCurrentState 中出现的 key）
# ---------------------------------------------------------------------------

LR_STATE_KEYS: tuple[str, ...] = (
    "can_input",
    "out_root",
    "levels",
    "platforms",
    "models",
    "target_versions",
    "selected_sheets",
    "log_level",
    "didinfo_excel",
    "cin_excel",
    "io_excel",
    "didconfig_excel",
    "uds_ecu_qualifier",
)

CENTRAL_STATE_KEYS: tuple[str, ...] = (
    "c_input",
    "c_out_root",
    "c_levels",
    "c_platforms",
    "c_models",
    "c_target_versions",
    "c_uart",
    "c_uart_comm",
    "c_selected_sheets",
    "c_uds_ecu_qualifier",
    "c_pwr",
    "c_rly",
    "c_ig",
    "c_pw",
    "c_ign_waitTime",
    "c_ign_current",
    "c_login_username",
    "c_login_password",
)

DTC_STATE_KEYS: tuple[str, ...] = (
    "d_input",
    "d_out_root",
    "d_levels",
    "d_platforms",
    "d_models",
    "d_target_versions",
    "d_selected_sheets",
    "d_uds_ecu_qualifier",
    "d_io_excel",
    "d_didconfig_excel",
    "d_didinfo_excel",
    "d_cin_excel",
)

# ---------------------------------------------------------------------------
# 前端状态键与配置项映射
# ---------------------------------------------------------------------------

UART_COMM_CFG_KEYS: tuple[str, ...] = (
    "uart_comm_port",
    "uart_comm_baudrate",
    "uart_comm_dataBits",
    "uart_comm_stopBits",
    "uart_comm_kHANDSHAKE_DISABLED",
    "uart_comm_parity",
    "uart_comm_frameTypeIs8676",
)

UART_COMM_KEY_MAP: dict[str, str] = {
    "port": "uart_comm_port",
    "baudrate": "uart_comm_baudrate",
    "dataBits": "uart_comm_dataBits",
    "stopBits": "uart_comm_stopBits",
    "kHANDSHAKE_DISABLED": "uart_comm_kHANDSHAKE_DISABLED",
    "parity": "uart_comm_parity",
    "frameTypeIs8676": "uart_comm_frameTypeIs8676",
}

CENTRAL_FILTER_KEY_MAP: list[tuple[str, str]] = [
    ("c_levels", OPTION_CASE_LEVELS),
    ("c_platforms", OPTION_CASE_PLATFORMS),
    ("c_models", OPTION_CASE_MODELS),
    ("c_target_versions", OPTION_CASE_TARGET_VERSIONS),
]

DTC_FILTER_KEY_MAP: list[tuple[str, str]] = [
    ("d_levels", OPTION_CASE_LEVELS),
    ("d_platforms", OPTION_CASE_PLATFORMS),
    ("d_models", OPTION_CASE_MODELS),
    ("d_target_versions", OPTION_CASE_TARGET_VERSIONS),
]

UDS_DOMAIN_SECTIONS: tuple[str, ...] = (
    SECTION_LR_REAR,
    SECTION_CENTRAL,
    SECTION_DTC,
)

FILTER_OPTION_KEYS: tuple[str, ...] = (
    OPTION_CASE_LEVELS,
    OPTION_CASE_PLATFORMS,
    OPTION_CASE_MODELS,
    OPTION_CASE_TARGET_VERSIONS,
)

FILTER_OPTION_CANDIDATES: dict[str, tuple[str, str]] = {
    OPTION_CASE_LEVELS: ("Case_Levels", OPTION_CASE_LEVELS),
    OPTION_CASE_PLATFORMS: ("Case_Platforms", OPTION_CASE_PLATFORMS),
    OPTION_CASE_MODELS: ("Case_Models", OPTION_CASE_MODELS),
    OPTION_CASE_TARGET_VERSIONS: ("Case_Target_Versions", OPTION_CASE_TARGET_VERSIONS),
}

CONFIG_KEY_SECTIONS: tuple[str, ...] = (
    SECTION_LR_REAR,
    SECTION_DTC,
    SECTION_CENTRAL,
    SECTION_PATHS,
)

CENTRAL_UART_UI_KEY_MAP: dict[str, str] = {
    "uart_comm_port": "port",
    "uart_comm_baudrate": "baudrate",
    "uart_comm_dataBits": "dataBits",
    "uart_comm_stopBits": "stopBits",
    "uart_comm_kHANDSHAKE_DISABLED": "kHANDSHAKE_DISABLED",
    "uart_comm_parity": "parity",
    "uart_comm_frameTypeIs8676": "frameTypeIs8676",
}

CENTRAL_MANAGED_KEYS: frozenset[str] = frozenset(
    {
        "c_pwr",
        "c_rly",
        "c_ig",
        "c_pw",
        "ign_waittime",
        "ign_current",
        "login_username",
        "login_password",
        *UART_COMM_CFG_KEYS,
    }
)

OPTION_INPUTS_CANDIDATES: tuple[str, str] = ("Inputs", OPTION_INPUTS)
OPTION_INPUT_EXCEL_CANDIDATES: tuple[str, str] = ("Input_Excel", OPTION_INPUT_EXCEL)
OPTION_OUTPUT_DIR_CANDIDATES: tuple[str, str] = ("Output_Dir", OPTION_OUTPUT_DIR)
OPTION_OUTPUT_FILENAME_CANDIDATES: tuple[str, str] = ("Output_FileName", OPTION_OUTPUT_FILENAME)
OPTION_DIDINFO_INPUTS_CANDIDATES: tuple[str, str] = ("Didinfo_Inputs", OPTION_DIDINFO_INPUTS)
OPTION_CIN_INPUT_EXCEL_CANDIDATES: tuple[str, str] = ("Cin_Input_Excel", OPTION_CIN_INPUT_EXCEL)

PATHS_UART_INPUT_OPTION_CANDIDATES: tuple[str, ...] = ("Uart_Input_Excel",)
PATHS_UART_OUTPUT_DIR_OPTION_CANDIDATES: tuple[str, ...] = ("Output_Dir_Uart", "Output_Dir")
PATHS_UART_FRAME_TYPE_OPTION_CANDIDATES: tuple[str, ...] = ("Uart_FrameTypeIs8676", "FrameTypeIs8676")
PATHS_UART_KNOWN_OPTION_KEYS: tuple[str, ...] = (
    "Input_Excel",
    "Mapping_Excel",
    "Mapping_Sheets",
    "Output_FileName",
    "Cin_Output_FileName",
    "Cin_Input_Excel",
    "Cin_Input_Sheet",
    "Cin_Mapping_Excel",
    "Cin_Mapping_Sheet",
    "Output_Cin_FileName",
    "Xml_Input_Excel",
    "Xml_Output_FileName",
    "Uart_Input_Excel",
    "Uart_Output_FileName",
    "Output_Dir",
    "Output_Dir_Uart",
    "Output_Dir_Can",
    "Output_Dir_Cin",
    "Output_Dir_Xml",
)
PATHS_CAN_OUTPUT_DIR_OPTION_CANDIDATES: tuple[str, ...] = ("output_dir_can", "Output_Dir_Can", "Output_Dir")
PATHS_DIDINFO_OUTPUT_DIR_OPTION_CANDIDATES: tuple[str, ...] = ("output_dir_didinfo", "Output_Dir_Didinfo", "output_dir", "Output_Dir")
PATHS_DIDINFO_INPUT_OPTION_CANDIDATES: tuple[str, ...] = ("didinfo_inputs", "Didinfo_Inputs", "didinfo_input_excel", "Didinfo_Input_Excel")


def get_io_mapping_section_candidates(domain: str | None) -> tuple[str, ...]:
    """按域返回 IOMAPPING 配置节候选。"""
    if domain and domain != SECTION_LR_REAR:
        return (f"{domain}_IOMAPPING",)
    return (SECTION_IOMAPPING,)


def get_config_enum_section_candidates(domain: str | None) -> tuple[str, ...]:
    """按域返回 CONFIG_ENUM 配置节候选。"""
    if domain and domain != SECTION_LR_REAR:
        return (f"{domain}_CONFIG_ENUM",)
    return (SECTION_CONFIG_ENUM,)


def get_domain_filter_candidates(domain: str | None, option_name: str) -> tuple[tuple[str, str], ...]:
    """返回域配置/FILTER/LR_REAR 的候选键顺序。"""
    option_candidates = FILTER_OPTION_CANDIDATES.get(option_name, (option_name,))
    pairs: list[tuple[str, str]] = []
    if domain:
        pairs.extend((domain, option) for option in option_candidates)
    pairs.extend((SECTION_FILTER, option) for option in option_candidates)
    if domain != SECTION_LR_REAR:
        pairs.extend((SECTION_LR_REAR, option) for option in option_candidates)
    return tuple(pairs)

# 当前端明确传空串时，需要删除的配置项。
LR_EMPTY_STATE_OPTION_MAP: dict[str, tuple[tuple[str, str], ...]] = {
    "can_input": ((SECTION_LR_REAR, OPTION_INPUT_EXCEL),),
    "io_excel": ((SECTION_IOMAPPING, OPTION_INPUTS),),
    "didconfig_excel": (
        (SECTION_DID_CONFIG, OPTION_INPUT_EXCEL),
        (SECTION_CONFIG_ENUM, OPTION_INPUTS),
    ),
    "didinfo_excel": ((SECTION_LR_REAR, OPTION_DIDINFO_INPUTS),),
    "cin_excel": ((SECTION_LR_REAR, OPTION_CIN_INPUT_EXCEL),),
}
