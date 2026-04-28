#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置节名、键名与前端 state 键的统一出口。

先集中最常改、最容易散落的常量，供路由层与配置服务共用，
避免后续做命名、路径、配置读写改造时重复搬迁字面量。

维护顺序（新增配置时按下面顺序改，避免漏改）：
1) 先补「配置节名 / 常用配置项名」常量；
2) 再补「UI/state 键」与必要的标签文案；
3) 再补「候选别名 *_CANDIDATES」；
4) 再补「保存规范 *_SAVE_NORMALIZE_OPTION_NAMES」；
5) 最后补「空值清理映射 LR_EMPTY_STATE_OPTION_MAP」。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 配置节名
# ---------------------------------------------------------------------------
# 新增一个 ini 节时，先在这里定义 SECTION_*。

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
# 新增一个 ini 键（如 input_excel）时，先在这里定义 OPTION_*。

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
# 历史键：仅填单个 Excel 路径（与 ``didinfo_inputs`` 的 ``路径 | *`` 管道格式不同）
OPTION_DIDINFO_INPUT_EXCEL = "didinfo_input_excel"
OPTION_CIN_INPUT_EXCEL = "cin_input_excel"
OPTION_SRV_EXCEL = "srv_excel"
OPTION_SOA_SETSERVER_OUTPUT_FILENAME = "soa_setserver_output_filename"
OPTION_SOA_DATATAB_OUTPUT_FILENAME = "soa_datatab_output_filename"

# ---------------------------------------------------------------------------
# 需求第3条：界面「ResetDid」/ DIDInfo 源表 ↔ collectCurrentState 键 ↔ ini didinfo_inputs
# ---------------------------------------------------------------------------
# 这一段放“前端字段名（UI_FIELD_* / STATE_KEY_*）+ 写入格式函数 + 用户可见文案标签”。
# 传给 ConfigManager.ui_state_key(prefix, …) 的域内字段名：LR 空前缀 → didinfo_excel；DTC prefix=d → d_didinfo_excel
UI_FIELD_DIDINFO_EXCEL = "didinfo_excel"
STATE_KEY_LR_DIDINFO_EXCEL = UI_FIELD_DIDINFO_EXCEL
STATE_KEY_DTC_DIDINFO_EXCEL = "d_didinfo_excel"
# 写入 ini 的历史格式：单路径 + sheet 通配
DIDINFO_INPUTS_VALUE_SUFFIX = " | *"


def didinfo_inputs_value_from_ui_single_path(raw: object) -> str:
    """将 UI 选择的单 Excel 路径转为 ``didinfo_inputs`` 选项值（空路径返回空串）。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    return f"{text}{DIDINFO_INPUTS_VALUE_SUFFIX}"


# 运行前校验 / 报错中的用户可见称呼（与界面 ResetDid 对应）
LABEL_RESETDID_VALUE_CONFIG_TABLE = "ResetDid_Value 配置表"
LABEL_DTC_DIDINFO_INPUT_TABLE = "DTC DIDInfo 配置表"

# ---------------------------------------------------------------------------
# 需求第3条：CIN / 关键字 Clib ↔ collectCurrentState ↔ ini cin_input_excel
# ---------------------------------------------------------------------------
# 同上：如果是某一业务域的字段映射，优先按这种“分主题段”集中放置。
UI_FIELD_CIN_EXCEL = "cin_excel"
STATE_KEY_LR_CIN_EXCEL = UI_FIELD_CIN_EXCEL
STATE_KEY_DTC_CIN_EXCEL = "d_cin_excel"
UI_FIELD_SRV_EXCEL = "srv_excel"
STATE_KEY_LR_SRV_EXCEL = UI_FIELD_SRV_EXCEL
STATE_KEY_DTC_SRV_EXCEL = "d_srv_excel"


def cin_input_excel_value_from_ui_path(raw: object) -> str:
    """将 UI 路径写入 ``cin_input_excel``；空串表示未配置。"""
    return str(raw or "").strip()


LABEL_CIN_CLIB_PATH_CHECK = "关键字集 Clib 配置表"
LABEL_DTC_CIN_CLIB_PATH_CHECK = "DTC 关键字集 Clib 配置表"
LABEL_CIN_MISSING_LR = "关键字配置表(cin_excel)"
LABEL_CIN_MISSING_DTC = "关键字配置表(d_cin_excel)"

# ---------------------------------------------------------------------------
# 需求第3条：DID_Config 表 ↔ state ↔ [DID_CONFIG].input_excel / [CONFIG_ENUM|DTC_CONFIG_ENUM].inputs
# ---------------------------------------------------------------------------
UI_FIELD_DIDCONFIG_EXCEL = "didconfig_excel"
STATE_KEY_LR_DIDCONFIG_EXCEL = UI_FIELD_DIDCONFIG_EXCEL
STATE_KEY_DTC_DIDCONFIG_EXCEL = "d_didconfig_excel"

LABEL_DIDCONFIG_PATH_CHECK = "DID_Config 配置表"
LABEL_DIDCONFIG_MISSING_LR = "DID_Config 配置表([CONFIG_ENUM].inputs 或 [DID_CONFIG].input_excel)"
LABEL_DTC_DIDCONFIG_PATH_CHECK = "DTC DID_Config 配置表"

# ---------------------------------------------------------------------------
# 需求第3条：CAN / IO_Mapping ↔ collectCurrentState ↔ input_excel / inputs
# ---------------------------------------------------------------------------
UI_FIELD_CAN_INPUT = "can_input"
STATE_KEY_LR_CAN_INPUT = UI_FIELD_CAN_INPUT
STATE_KEY_DTC_CAN_INPUT = "d_input"
UI_FIELD_IO_EXCEL = "io_excel"
STATE_KEY_LR_IO_EXCEL = UI_FIELD_IO_EXCEL
STATE_KEY_DTC_IO_EXCEL = "d_io_excel"


def input_excel_value_from_ui_path(raw: object) -> str:
    """将 UI 路径写入 ``input_excel``；空串表示未配置。"""
    return str(raw or "").strip()


def io_inputs_value_from_ui_single_path(raw: object) -> str:
    """将 UI 选择的单 Excel 路径转为 ``inputs`` 选项值（空路径返回空串）。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    return f"{text}{DIDINFO_INPUTS_VALUE_SUFFIX}"

# ---------------------------------------------------------------------------
# 需求第3条：输出目录 / 选中 sheets / 日志等级 ↔ collectCurrentState
# ---------------------------------------------------------------------------
UI_FIELD_OUT_ROOT = "out_root"
STATE_KEY_LR_OUT_ROOT = UI_FIELD_OUT_ROOT
STATE_KEY_DTC_OUT_ROOT = "d_out_root"
UI_FIELD_SELECTED_SHEETS = "selected_sheets"
STATE_KEY_LR_SELECTED_SHEETS = UI_FIELD_SELECTED_SHEETS
STATE_KEY_DTC_SELECTED_SHEETS = "d_selected_sheets"
UI_FIELD_LOG_LEVEL = "log_level"
STATE_KEY_LR_LOG_LEVEL = UI_FIELD_LOG_LEVEL
STATE_KEY_DTC_LOG_LEVEL = "d_log_level"
UI_FIELD_LEVELS = "levels"
STATE_KEY_LR_LEVELS = UI_FIELD_LEVELS
STATE_KEY_DTC_LEVELS = "d_levels"
UI_FIELD_PLATFORMS = "platforms"
STATE_KEY_LR_PLATFORMS = UI_FIELD_PLATFORMS
STATE_KEY_DTC_PLATFORMS = "d_platforms"
UI_FIELD_MODELS = "models"
STATE_KEY_LR_MODELS = UI_FIELD_MODELS
STATE_KEY_DTC_MODELS = "d_models"
UI_FIELD_TARGET_VERSIONS = "target_versions"
STATE_KEY_LR_TARGET_VERSIONS = UI_FIELD_TARGET_VERSIONS
STATE_KEY_DTC_TARGET_VERSIONS = "d_target_versions"
UI_FIELD_UDS_ECU_QUALIFIER = OPTION_UDS_ECU_QUALIFIER
STATE_KEY_LR_UDS_ECU_QUALIFIER = UI_FIELD_UDS_ECU_QUALIFIER

OPTION_UART_EXCEL = "uart_excel"
OPTION_XML_INPUT_EXCEL = "xml_input_excel"
OPTION_IGN_WAITTIME = "ign_waittime"
OPTION_IGN_CURRENT = "ign_current"
OPTION_LOGIN_USERNAME = "login_username"
OPTION_LOGIN_PASSWORD = "login_password"
OPTION_C_PWR = "c_pwr"
OPTION_C_RLY = "c_rly"
OPTION_C_IG = "c_ig"
OPTION_C_PW = "c_pw"
OPTION_IGNITION_CYCLE_WAIT_TIME = "waitTime"
OPTION_IGNITION_CYCLE_CURRENT = "current"

DEFAULT_DID_CONFIG_FILENAME = "DIDConfig.txt"
DEFAULT_UDS_FILENAME = "uds.txt"
DEFAULT_POWER_RELAY_CONFIG_FILENAME = "PowerRelayConfig.txt"
DEFAULT_IGNITION_CYCLE_FILENAME = "IgnitionCycle.txt"
DEFAULT_LOGIN_FILENAME = "login.txt"
DEFAULT_DOMAIN_LR_REAR = SECTION_LR_REAR

VALID_LOG_LEVELS: tuple[str, ...] = ("info", "warning", "error")

# ---------------------------------------------------------------------------
# 各域 state 键（前端 collectCurrentState）— 与 ini / 产物关系说明（需求第3条）
#
# 不在其它模块重复维护平行「映射表」；增删键时只改下方元组，并同步
# StateConfigService / ConfigService 的写入与 load_ui_data 的读取。
#
# LR_REAR（键名即 LR_STATE_KEYS 元素）：
#   STATE_KEY_LR_CAN_INPUT —→ [LR_REAR] input_excel（及别名）—→ CAN/XML 用例与输出
#   STATE_KEY_LR_OUT_ROOT —→ [LR_REAR] output_dir —→ 本域生成物根路径
#   STATE_KEY_LR_LEVELS/STATE_KEY_LR_PLATFORMS/STATE_KEY_LR_MODELS/STATE_KEY_LR_TARGET_VERSIONS/STATE_KEY_LR_SELECTED_SHEETS/STATE_KEY_LR_LOG_LEVEL —→ 同节过滤与日志
#   STATE_KEY_LR_DIDINFO_EXCEL —→ [LR_REAR] didinfo_inputs 等 —→ 界面「ResetDid」/ DIDInfo 产物
#   STATE_KEY_LR_CIN_EXCEL —→ [LR_REAR] cin_input_excel 等 —→ CIN / Clib
#   STATE_KEY_LR_IO_EXCEL —→ [IOMAPPING] inputs —→ IO 映射
#   STATE_KEY_LR_DIDCONFIG_EXCEL —→ [CONFIG_ENUM].inputs（首段）与 [DID_CONFIG] 兜底 —→ DID_Config
#   uds_ecu_qualifier —→ [LR_REAR] uds_ecu_qualifier —→ UDS.txt
#
# CENTRAL：c_* 键 —→ [CENTRAL] 等（含 c_uart / uart_comm_* —→ UART 仅中央域）
# DTC：d_* 键 —→ [DTC] / [DTC_CONFIG_ENUM] / [DTC_IOMAPPING] 等
# ---------------------------------------------------------------------------
# 新增 state 键时：先定义常量，再把键加入对应 *_STATE_KEYS。

LR_STATE_KEYS: tuple[str, ...] = (
    STATE_KEY_LR_CAN_INPUT,
    STATE_KEY_LR_OUT_ROOT,
    STATE_KEY_LR_LEVELS,
    STATE_KEY_LR_PLATFORMS,
    STATE_KEY_LR_MODELS,
    STATE_KEY_LR_TARGET_VERSIONS,
    STATE_KEY_LR_SELECTED_SHEETS,
    STATE_KEY_LR_LOG_LEVEL,
    STATE_KEY_LR_DIDINFO_EXCEL,
    STATE_KEY_LR_CIN_EXCEL,
    STATE_KEY_LR_SRV_EXCEL,
    STATE_KEY_LR_IO_EXCEL,
    STATE_KEY_LR_DIDCONFIG_EXCEL,
    STATE_KEY_LR_UDS_ECU_QUALIFIER,
)

# CENTRAL 域 state 键（用于 StateConfigService / Route 统一引用）
STATE_KEY_CENTRAL_CAN_INPUT = "c_input"
STATE_KEY_CENTRAL_OUT_ROOT = "c_out_root"
STATE_KEY_CENTRAL_LEVELS = "c_levels"
STATE_KEY_CENTRAL_PLATFORMS = "c_platforms"
STATE_KEY_CENTRAL_MODELS = "c_models"
STATE_KEY_CENTRAL_TARGET_VERSIONS = "c_target_versions"
STATE_KEY_CENTRAL_SELECTED_SHEETS = "c_selected_sheets"
STATE_KEY_CENTRAL_LOG_LEVEL = "c_log_level"
STATE_KEY_CENTRAL_UDS_ECU_QUALIFIER = "c_uds_ecu_qualifier"
STATE_KEY_CENTRAL_UART = "c_uart"
STATE_KEY_CENTRAL_SRV_EXCEL = "c_srv"
STATE_KEY_CENTRAL_UART_COMM = "c_uart_comm"
STATE_KEY_CENTRAL_PWR = "c_pwr"
STATE_KEY_CENTRAL_RLY = "c_rly"
STATE_KEY_CENTRAL_IG = "c_ig"
STATE_KEY_CENTRAL_PW = "c_pw"
STATE_KEY_CENTRAL_IGN_WAIT_TIME = "c_ign_waitTime"
STATE_KEY_CENTRAL_IGN_CURRENT = "c_ign_current"
STATE_KEY_CENTRAL_LOGIN_USERNAME = "c_login_username"
STATE_KEY_CENTRAL_LOGIN_PASSWORD = "c_login_password"

# DTC 域补充 state 键
STATE_KEY_DTC_UDS_ECU_QUALIFIER = "d_uds_ecu_qualifier"
STATE_KEY_DTC_IO_SELECTED_SHEETS = "d_io_selected_sheets"

CENTRAL_STATE_KEYS: tuple[str, ...] = (
    STATE_KEY_CENTRAL_CAN_INPUT,
    STATE_KEY_CENTRAL_OUT_ROOT,
    STATE_KEY_CENTRAL_LEVELS,
    STATE_KEY_CENTRAL_PLATFORMS,
    STATE_KEY_CENTRAL_MODELS,
    STATE_KEY_CENTRAL_TARGET_VERSIONS,
    STATE_KEY_CENTRAL_UART,
    STATE_KEY_CENTRAL_SRV_EXCEL,
    STATE_KEY_CENTRAL_UART_COMM,
    STATE_KEY_CENTRAL_SELECTED_SHEETS,
    STATE_KEY_CENTRAL_UDS_ECU_QUALIFIER,
    STATE_KEY_CENTRAL_PWR,
    STATE_KEY_CENTRAL_RLY,
    STATE_KEY_CENTRAL_IG,
    STATE_KEY_CENTRAL_PW,
    STATE_KEY_CENTRAL_IGN_WAIT_TIME,
    STATE_KEY_CENTRAL_IGN_CURRENT,
    STATE_KEY_CENTRAL_LOGIN_USERNAME,
    STATE_KEY_CENTRAL_LOGIN_PASSWORD,
)

DTC_STATE_KEYS: tuple[str, ...] = (
    STATE_KEY_DTC_CAN_INPUT,
    STATE_KEY_DTC_OUT_ROOT,
    STATE_KEY_DTC_LEVELS,
    STATE_KEY_DTC_PLATFORMS,
    STATE_KEY_DTC_MODELS,
    STATE_KEY_DTC_TARGET_VERSIONS,
    STATE_KEY_DTC_SELECTED_SHEETS,
    STATE_KEY_DTC_UDS_ECU_QUALIFIER,
    STATE_KEY_DTC_IO_EXCEL,
    STATE_KEY_DTC_DIDCONFIG_EXCEL,
    STATE_KEY_DTC_DIDINFO_EXCEL,
    STATE_KEY_DTC_CIN_EXCEL,
    STATE_KEY_DTC_SRV_EXCEL,
)

# CIN 运行期上下文字典键（runtime dict）
CIN_RUNTIME_KEY_CONFIG_PATH = "config_path"
CIN_RUNTIME_KEY_CFG = "cfg"
CIN_RUNTIME_KEY_INPUT_SHEET = "input_sheet"
CIN_RUNTIME_KEY_INPUT_EXCEL_PATH = "input_excel_path"
CIN_RUNTIME_KEY_MAPPING_EXCEL_PATH = "mapping_excel_path"
CIN_RUNTIME_KEY_SHEET_NAMES_STR = "sheet_names_str"
CIN_RUNTIME_KEY_OUTPUT_DIR = "output_dir"
CIN_RUNTIME_KEY_OUTPUT_CIN_FILENAME = "output_cin_filename"
CIN_RUNTIME_KEY_IO_MAPPING_CTX = "io_mapping_ctx"
CIN_RUNTIME_KEY_CONFIG_ENUM_CTX = "config_enum_ctx"

# XML 运行期上下文字典键（runtime dict）
XML_RUNTIME_KEY_EXCEL_PATH = "excel_path"
XML_RUNTIME_KEY_OUTPUT_XML_PATH = "output_xml_path"
XML_RUNTIME_KEY_ALLOWED_LEVELS = "allowed_levels"
XML_RUNTIME_KEY_ALLOWED_PLATFORMS = "allowed_platforms"
XML_RUNTIME_KEY_ALLOWED_MODELS = "allowed_models"
XML_RUNTIME_KEY_ALLOWED_TARGET_VERSIONS = "allowed_target_versions"
XML_RUNTIME_KEY_SELECTED_FILTER = "selected_filter"

# ---------------------------------------------------------------------------
# 前端状态键与配置项映射
# ---------------------------------------------------------------------------
# 这一段放“跨模块共用的映射关系/候选键集合”，避免业务文件散落字面量。

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
    (STATE_KEY_CENTRAL_LEVELS, OPTION_CASE_LEVELS),
    (STATE_KEY_CENTRAL_PLATFORMS, OPTION_CASE_PLATFORMS),
    (STATE_KEY_CENTRAL_MODELS, OPTION_CASE_MODELS),
    (STATE_KEY_CENTRAL_TARGET_VERSIONS, OPTION_CASE_TARGET_VERSIONS),
]

DTC_FILTER_KEY_MAP: list[tuple[str, str]] = [
    (STATE_KEY_DTC_LEVELS, OPTION_CASE_LEVELS),
    (STATE_KEY_DTC_PLATFORMS, OPTION_CASE_PLATFORMS),
    (STATE_KEY_DTC_MODELS, OPTION_CASE_MODELS),
    (STATE_KEY_DTC_TARGET_VERSIONS, OPTION_CASE_TARGET_VERSIONS),
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

FILTER_OPTIONS_UI_KEYS: tuple[tuple[str, str], ...] = (
    (UI_FIELD_LEVELS, UI_FIELD_LEVELS),
    (UI_FIELD_PLATFORMS, UI_FIELD_PLATFORMS),
    (UI_FIELD_MODELS, UI_FIELD_MODELS),
    (UI_FIELD_TARGET_VERSIONS, UI_FIELD_TARGET_VERSIONS),
    (UI_FIELD_UDS_ECU_QUALIFIER, UI_FIELD_UDS_ECU_QUALIFIER),
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
        OPTION_C_PWR,
        OPTION_C_RLY,
        OPTION_C_IG,
        OPTION_C_PW,
        OPTION_IGN_WAITTIME,
        OPTION_IGN_CURRENT,
        OPTION_LOGIN_USERNAME,
        OPTION_LOGIN_PASSWORD,
        *UART_COMM_CFG_KEYS,
    }
)

OPTION_INPUTS_CANDIDATES: tuple[str, str] = ("Inputs", OPTION_INPUTS)
OPTION_INPUT_EXCEL_CANDIDATES: tuple[str, str] = ("Input_Excel", OPTION_INPUT_EXCEL)
DEPRECATED_INPUT_EXCEL_DIR_OPTION_CANDIDATES: tuple[str, str] = ("Input_Excel_Dir", "input_excel_dir")
OPTION_OUTPUT_DIR_CANDIDATES: tuple[str, str] = ("Output_Dir", OPTION_OUTPUT_DIR)
OPTION_OUTPUT_FILENAME_CANDIDATES: tuple[str, str] = ("Output_FileName", OPTION_OUTPUT_FILENAME)
OPTION_DIDINFO_INPUTS_CANDIDATES: tuple[str, str] = ("Didinfo_Inputs", OPTION_DIDINFO_INPUTS)
OPTION_DIDINFO_INPUT_EXCEL_CANDIDATES: tuple[str, str] = ("Didinfo_Input_Excel", OPTION_DIDINFO_INPUT_EXCEL)
OPTION_DIDINFO_OUTPUT_DIR_CANDIDATES: tuple[str, str] = ("Output_Dir_Didinfo", "output_dir_didinfo")
OPTION_DIDINFO_VARIANTS_CANDIDATES: tuple[str, str] = ("Didinfo_Variants", "didinfo_variants")
OPTION_CIN_INPUT_EXCEL_CANDIDATES: tuple[str, str] = ("Cin_Input_Excel", OPTION_CIN_INPUT_EXCEL)
OPTION_SRV_EXCEL_CANDIDATES: tuple[str, str] = ("Srv_Excel", OPTION_SRV_EXCEL)
# 候选键维护规则：
# - 元组顺序表达“读取优先级”；
# - 新增历史别名时，只改这里，业务代码里用循环/拼接引用这些候选。

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
# [PATHS] 节：didinfo_inputs 管道键与 didinfo_input_excel 单路径键的候选顺序（历史说明）
PATHS_DIDINFO_INPUT_PIPE_OPTION_CANDIDATES: tuple[str, str] = (
    OPTION_DIDINFO_INPUTS,
    OPTION_DIDINFO_INPUTS_CANDIDATES[0],
)
PATHS_DIDINFO_INPUT_EXCEL_OPTION_CANDIDATES: tuple[str, str] = tuple(
    reversed(OPTION_DIDINFO_INPUT_EXCEL_CANDIDATES)
)
PATHS_DIDINFO_INPUT_OPTION_CANDIDATES: tuple[str, ...] = (
    *PATHS_DIDINFO_INPUT_PIPE_OPTION_CANDIDATES,
    *PATHS_DIDINFO_INPUT_EXCEL_OPTION_CANDIDATES,
)

# ---------------------------------------------------------------------------
# ConfigManager.save_formatted_config：PATHS 备份键、各域规范化写入键、需预建节
# （单一来源，避免与 config_manager 字面量双份维护）
# ---------------------------------------------------------------------------
# 新增需要“保存时稳定写回”的键时，优先补到下面 *_SAVE_NORMALIZE_OPTION_NAMES。

PATHS_REDIRECTABLE_OPTION_NAMES: tuple[str, ...] = ("mapping_excel", "cin_mapping_excel")

PATHS_STABLE_OUTPUT_RELATED_OPTION_NAMES: tuple[str, ...] = (
    "unified_mapping_excel",
    "mapping_sheets",
    "cin_mapping_sheet",
    OPTION_OUTPUT_FILENAME,
    "cin_output_filename",
    "xml_output_filename",
    "didinfo_output_filename",
    "didconfig_output_filename",
    "uart_output_filename",
    "uds_output_filename",
    OPTION_SOA_SETSERVER_OUTPUT_FILENAME,
    OPTION_SOA_DATATAB_OUTPUT_FILENAME,
    "didinfo_variants",
)

PATHS_MERGED_PRESERVE_OPTION_NAMES: tuple[str, ...] = (
    *PATHS_STABLE_OUTPUT_RELATED_OPTION_NAMES,
    *PATHS_REDIRECTABLE_OPTION_NAMES,
)

LR_REAR_SAVE_NORMALIZE_OPTION_NAMES: tuple[str, ...] = (
    OPTION_INPUT_EXCEL,
    OPTION_SRV_EXCEL,
    OPTION_OUTPUT_DIR,
    *FILTER_OPTION_KEYS,
    OPTION_SELECTED_SHEETS,
    OPTION_LOG_LEVEL_MIN,
    OPTION_DIDINFO_INPUTS,
    OPTION_CIN_INPUT_EXCEL,
    OPTION_UDS_ECU_QUALIFIER,
)

CENTRAL_SAVE_NORMALIZE_OPTION_NAMES: tuple[str, ...] = (
    OPTION_INPUT_EXCEL,
    OPTION_SRV_EXCEL,
    OPTION_UART_EXCEL,
    OPTION_SRV_EXCEL,
    "pwr_excel",
    "rly_excel",
    OPTION_SELECTED_SHEETS,
    *UART_COMM_CFG_KEYS,
    OPTION_IGN_WAITTIME,
    OPTION_IGN_CURRENT,
    OPTION_C_PWR,
    OPTION_C_RLY,
    OPTION_C_IG,
    OPTION_C_PW,
    OPTION_OUTPUT_DIR,
    *FILTER_OPTION_KEYS,
    OPTION_LOG_LEVEL_MIN,
    OPTION_UDS_ECU_QUALIFIER,
    OPTION_LOGIN_USERNAME,
    OPTION_LOGIN_PASSWORD,
)

DTC_SAVE_NORMALIZE_OPTION_NAMES: tuple[str, ...] = (
    OPTION_INPUT_EXCEL,
    OPTION_SRV_EXCEL,
    OPTION_SELECTED_SHEETS,
    OPTION_OUTPUT_DIR,
    *FILTER_OPTION_KEYS,
    OPTION_LOG_LEVEL_MIN,
    OPTION_DIDINFO_INPUTS,
    OPTION_CIN_INPUT_EXCEL,
    OPTION_UDS_ECU_QUALIFIER,
)

FORMATTED_SAVE_SECTIONS_TO_ENSURE: tuple[str, ...] = (
    SECTION_LR_REAR,
    SECTION_IOMAPPING,
    SECTION_DID_CONFIG,
    SECTION_CONFIG_ENUM,
    SECTION_CENTRAL,
    SECTION_IGNITION_CYCLE,
    SECTION_DTC,
    SECTION_DTC_IOMAPPING,
    SECTION_DTC_CONFIG_ENUM,
)


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
# 新增“前端传空需要删除”的键时，在这里补映射，避免在业务逻辑里写 remove_option 字面量。
LR_EMPTY_STATE_OPTION_MAP: dict[str, tuple[tuple[str, str], ...]] = {
    STATE_KEY_LR_CAN_INPUT: ((SECTION_LR_REAR, OPTION_INPUT_EXCEL),),
    STATE_KEY_LR_IO_EXCEL: ((SECTION_IOMAPPING, OPTION_INPUTS),),
    STATE_KEY_LR_DIDCONFIG_EXCEL: (
        (SECTION_DID_CONFIG, OPTION_INPUT_EXCEL),
        (SECTION_CONFIG_ENUM, OPTION_INPUTS),
    ),
    STATE_KEY_LR_DIDINFO_EXCEL: ((SECTION_LR_REAR, OPTION_DIDINFO_INPUTS),),
    STATE_KEY_LR_CIN_EXCEL: ((SECTION_LR_REAR, OPTION_CIN_INPUT_EXCEL),),
}
