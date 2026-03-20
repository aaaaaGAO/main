#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用路由（common_bp）

职责：
- 提供基础的健康检查 / 心跳接口
- 预留“配置读取”这类轻量接口，逐步把 app.py 中的逻辑迁移到 services 层

注意：
- 本文件只做 HTTP 层的参数解析与返回 JSON，不直接做文件 IO 和 configparser 操作。
"""

from __future__ import annotations

import os
import subprocess
import time
import json
from typing import Any, Dict


def _flush_config_to_disk() -> None:
    """写入配置后强制同步到磁盘，避免生成脚本读到未刷新的文件。参数：无。返回：无返回值。"""
    try:
        if hasattr(os, "sync"):
            os.sync()
    except Exception:
        pass

from flask import Blueprint, current_app, jsonify, request

from services.config_manager import ConfigManager
from services.config_service import ConfigService
from services.filter_service import parse_shaixuan_config
from services.gui_service import GuiService
from services.task_orchestrator import TaskOrchestrator

common_bp = Blueprint("common", __name__)


def _base_dir() -> str:
    """获取当前应用的项目根目录（Configuration.txt / filter_options.txt 所在目录）。参数：无。返回：根目录绝对路径。"""
    return current_app.config.get("BASE_DIR", "") or os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


@common_bp.route("/healthz", methods=["GET"])
def healthz():
    """健康检查接口，用于前端或监控确认服务是否存活。参数：无。返回：JSON { status, ts }。"""
    return jsonify({"status": "ok", "ts": time.time()})


@common_bp.route("/heartbeat", methods=["POST"])
def api_heartbeat():
    """心跳接口（轻量版占位），目前仅返回 alive。参数：无。返回：JSON { status: alive }。"""
    return jsonify({"status": "alive"})


@common_bp.route("/config/lr_rear", methods=["GET"])
def get_lr_rear_config():
    """获取 [LR_REAR] 配置供前端使用。参数：无。返回：JSON { success, data }。"""
    base_dir = _base_dir()
    svc = ConfigService.from_base_dir(base_dir)
    data: Dict[str, Any] = svc.get_lr_rear()
    return jsonify({"success": True, "data": data})


@common_bp.route("/get_filter_options", methods=["GET"])
def get_filter_options():
    """获取筛选框选项（等级/平台/车型/UDS_ECU_qualifier），数据来自 filter_options.txt。参数：无。返回：JSON 筛选选项。"""
    base_dir = _base_dir()
    filters = parse_shaixuan_config(base_dir)
    return jsonify(filters)


@common_bp.route("/load_config", methods=["GET"])
def load_config():
    """加载完整配置供前端展示（ConfigManager.load_ui_data）。参数：base_dir — 可选，配置根目录，缺省为当前 BASE_DIR。返回：JSON { success, data }。"""
    base_dir = request.args.get("base_dir") or _base_dir()
    manager = ConfigManager.from_base_dir(base_dir)
    data = manager.load_ui_data()
    return jsonify({"success": True, "data": data})


@common_bp.route("/select_file", methods=["POST"])
def select_file():
    """弹出系统选择文件/文件夹窗口（GuiService.select_path）。参数：file_type — 请求体中可选，\"file\" 或 \"folder\"，缺省 \"file\"。返回：JSON { success, path?, filename? } 或 { success: false, message }。"""
    try:
        payload = request.get_json(silent=True) or {}
        file_type = payload.get("file_type", "file")
        path = GuiService.select_path(file_type=file_type)
        if path:
            return jsonify({
                "success": True,
                "path": path,
                "filename": os.path.basename(path),
            })
        return jsonify({"success": False, "message": "用户取消了选择"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@common_bp.route("/parse_file_structure", methods=["POST"])
def parse_file_structure():
    """解析指定文件或文件夹结构，供前端树形展示。参数：path — 请求体中文件或文件夹路径。返回：JSON 树形结构；失败时 { success: false, message }。"""
    try:
        payload = request.get_json(silent=True) or {}
        path = (payload.get("path") or "").strip()
        result = GuiService.parse_file_structure(path)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


def _state_to_lr_preset(state: Dict[str, Any]) -> Dict[str, Any]:
    """将前端 collectCurrentState 的 state 转为 ConfigService.update_lr_rear_and_related 所需的 preset_data。参数：state — 前端提交的完整 state 字典。返回：仅含左右后域相关键的字典。"""
    def _str(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return ",".join(str(x) for x in v) if v else "ALL"
        return str(v).strip()

    return {
        "can_input": _str(state.get("can_input")),
        "out_root": _str(state.get("out_root")),
        "levels": _str(state.get("levels")) or "ALL",
        "platforms": _str(state.get("platforms")),
        "models": _str(state.get("models")),
        "target_versions": _str(state.get("target_versions")),
        "selected_sheets": _str(state.get("selected_sheets")),
        "log_level": _str(state.get("log_level")) or "info",
        "didinfo_excel": _str(state.get("didinfo_excel")),
        "cin_excel": _str(state.get("cin_excel")),
        "io_excel": _str(state.get("io_excel")),
        "didconfig_excel": _str(state.get("didconfig_excel")),
    }


def _has_any_lr_state(state: Dict[str, Any]) -> bool:
    """判断 state 是否包含任意左右后域相关字段，用于决定是否更新 LR_REAR 等配置。参数：state — 前端提交的 state 字典。返回：True 表示含有 can_input、out_root、levels 等任一项。"""
    lr_keys = (
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
    return any(k in state for k in lr_keys)


def _resolve_uds_output_path(cfg, base_dir: str, section: str) -> str:
    """按 ConfigManager._write_uds_files 的规则推导指定域的 uds.txt 输出路径。参数：cfg — 已读入的 ConfigParser；base_dir — 项目根目录；section — 域节名（如 LR_REAR、CENTRAL、DTC）。返回：uds.txt 的完整路径，无配置时返回空串。"""
    if not cfg.has_section(section):
        return ""
    out_dir = (cfg.get(section, "output_dir", fallback="") or "").strip()
    uds_val = (cfg.get(section, "uds_ecu_qualifier", fallback="") or "").strip()
    if not out_dir or not uds_val:
        return ""

    if not os.path.isabs(out_dir):
        root = os.path.abspath(os.path.join(base_dir, out_dir))
    else:
        root = os.path.abspath(out_dir)

    if os.path.basename(root).lower() == "configuration":
        config_dir = root
    else:
        config_dir = None
        if os.path.isdir(root):
            for name in os.listdir(root):
                if name.lower() == "configuration":
                    cand = os.path.join(root, name)
                    if os.path.isdir(cand):
                        config_dir = cand
                        break
        if config_dir is None:
            config_dir = os.path.join(root, "Configuration")
    fixed = ConfigManager.from_base_dir(base_dir)._read_fixed_config()
    uds_filename = (fixed.get("uds_output_filename") or "uds.txt").strip() or "uds.txt"
    return os.path.join(config_dir, uds_filename)


def _apply_state_to_config(
    state: Dict[str, Any], cfg, svc: ConfigService, *, skip_lr_rear: bool = False
) -> None:
    """将前端 state 合并写入 config（LR_REAR、CENTRAL、DTC 等），并同步 FILTER/PATHS。参数：state — 前端 state 字典；cfg — 将被原地修改的 ConfigParser；svc — ConfigService 实例；skip_lr_rear — 为 True 时跳过左右后域更新。返回：无返回值。"""
    if not skip_lr_rear and _has_any_lr_state(state):
        preset = _state_to_lr_preset(state)
        svc.update_lr_rear_and_related(cfg, preset)
        # uds_ecu_qualifier 单独处理
        if state.get("uds_ecu_qualifier"):
            if not cfg.has_section("LR_REAR"):
                cfg.add_section("LR_REAR")
            cfg.set("LR_REAR", "uds_ecu_qualifier", str(state["uds_ecu_qualifier"]).strip())
        # 前端明确传了空字符串时，认为用户想“删除/清空”这些路径项
        if cfg.has_section("LR_REAR"):
            if state.get("can_input") == "":
                if cfg.has_option("LR_REAR", "input_excel"):
                    cfg.remove_option("LR_REAR", "input_excel")
            if state.get("io_excel") == "":
                # IO_Mapping：对应 [IOMAPPING].inputs
                if cfg.has_section("IOMAPPING") and cfg.has_option("IOMAPPING", "inputs"):
                    cfg.remove_option("IOMAPPING", "inputs")
            if state.get("didconfig_excel") == "":
                # DID_Config：对应 [DID_CONFIG].input_excel
                if cfg.has_section("DID_CONFIG") and cfg.has_option("DID_CONFIG", "input_excel"):
                    cfg.remove_option("DID_CONFIG", "input_excel")
                # 枚举配置：对应 [CONFIG_ENUM].inputs
                if cfg.has_section("CONFIG_ENUM") and cfg.has_option("CONFIG_ENUM", "inputs"):
                    cfg.remove_option("CONFIG_ENUM", "inputs")
            if state.get("didinfo_excel") == "":
                if cfg.has_option("LR_REAR", "didinfo_inputs"):
                    cfg.remove_option("LR_REAR", "didinfo_inputs")
            if state.get("cin_excel") == "":
                if cfg.has_option("LR_REAR", "cin_input_excel"):
                    cfg.remove_option("LR_REAR", "cin_input_excel")
    # CENTRAL
    if any(
        k in state
        for k in (
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
    ):
        if not cfg.has_section("CENTRAL"):
            cfg.add_section("CENTRAL")
        if state.get("c_input"):
            cfg.set("CENTRAL", "input_excel", str(state["c_input"]).strip())
        elif state.get("c_input") == "":
            # 清空中央域用例路径时，同时删掉 input_excel 与 selected_sheets
            if cfg.has_option("CENTRAL", "input_excel"):
                cfg.remove_option("CENTRAL", "input_excel")
            if cfg.has_option("CENTRAL", "selected_sheets"):
                cfg.remove_option("CENTRAL", "selected_sheets")
        if state.get("c_out_root"):
            cfg.set("CENTRAL", "output_dir", str(state["c_out_root"]).strip())
        for k, opt in [
            ("c_levels", "case_levels"),
            ("c_platforms", "case_platforms"),
            ("c_models", "case_models"),
            ("c_target_versions", "case_target_versions"),
        ]:
            v = state.get(k)
            if v is not None:
                val = ",".join(v) if isinstance(v, list) else str(v)
                cfg.set("CENTRAL", opt, val.strip() if isinstance(val, str) else val)
        if state.get("c_selected_sheets"):
            cfg.set("CENTRAL", "selected_sheets", str(state["c_selected_sheets"]).strip())
        elif state.get("c_selected_sheets") == "":
            if cfg.has_option("CENTRAL", "selected_sheets"):
                cfg.remove_option("CENTRAL", "selected_sheets")
        if state.get("c_log_level"):
            cfg.set("CENTRAL", "log_level_min", str(state["c_log_level"]).strip().lower())
        if state.get("c_uds_ecu_qualifier"):
            cfg.set("CENTRAL", "uds_ecu_qualifier", str(state["c_uds_ecu_qualifier"]).strip())
        if state.get("c_uart"):
            cfg.set("CENTRAL", "uart_excel", str(state["c_uart"]).strip())
        elif state.get("c_uart") == "":
            if cfg.has_option("CENTRAL", "uart_excel"):
                cfg.remove_option("CENTRAL", "uart_excel")
        # 串口通信：仅当「配置里已有 uart_comm_*」或「state 里 port 非空」时才写入；否则不写入，避免运行/保存时自动写入默认（与运行账号一致）
        _uart_keys = [
            "uart_comm_port", "uart_comm_baudrate", "uart_comm_dataBits", "uart_comm_stopBits",
            "uart_comm_kHANDSHAKE_DISABLED", "uart_comm_parity", "uart_comm_frameTypeIs8676",
        ]
        _has_uart_in_cfg = cfg.has_section("CENTRAL") and any(cfg.has_option("CENTRAL", k) for k in _uart_keys)
        _uart_comm_raw = state.get("c_uart_comm")
        uart_comm = _uart_comm_raw if isinstance(_uart_comm_raw, dict) else None
        port_set = bool((uart_comm.get("port") or "").strip()) if uart_comm else False
        if _has_uart_in_cfg or port_set:
            if uart_comm and port_set:
                key_map = {
                    "port": "uart_comm_port", "baudrate": "uart_comm_baudrate", "dataBits": "uart_comm_dataBits",
                    "stopBits": "uart_comm_stopBits", "kHANDSHAKE_DISABLED": "uart_comm_kHANDSHAKE_DISABLED",
                    "parity": "uart_comm_parity", "frameTypeIs8676": "uart_comm_frameTypeIs8676",
                }
                for src_key, cfg_key in key_map.items():
                    if src_key in uart_comm:
                        cfg.set("CENTRAL", cfg_key, str(uart_comm.get(src_key) or "").strip())
            elif _has_uart_in_cfg:
                for cfg_key in _uart_keys:
                    if cfg.has_option("CENTRAL", cfg_key):
                        cfg.remove_option("CENTRAL", cfg_key)
        ign_wt = str(state.get("c_ign_waitTime") or "").strip()
        ign_cur = str(state.get("c_ign_current") or "").strip()
        # 点火循环配置：只要前端有传 c_ign_*（包括第一次配置），就根据 state 创建/更新/清空 CENTRAL 与 [IgnitionCycle]
        if state.get("c_ign_waitTime") is not None or state.get("c_ign_current") is not None:
            if ign_wt or ign_cur:
                if not cfg.has_section("IgnitionCycle"):
                    cfg.add_section("IgnitionCycle")
                if state.get("c_ign_waitTime") is not None:
                    cfg.set("CENTRAL", "ign_waittime", ign_wt)
                    cfg.set("IgnitionCycle", "waitTime", ign_wt)
                if state.get("c_ign_current") is not None:
                    cfg.set("CENTRAL", "ign_current", ign_cur)
                    cfg.set("IgnitionCycle", "current", ign_cur)
            else:
                if cfg.has_section("CENTRAL"):
                    if cfg.has_option("CENTRAL", "ign_waittime"):
                        cfg.remove_option("CENTRAL", "ign_waittime")
                    if cfg.has_option("CENTRAL", "ign_current"):
                        cfg.remove_option("CENTRAL", "ign_current")
                if cfg.has_section("IgnitionCycle"):
                    if cfg.has_option("IgnitionCycle", "waitTime"):
                        cfg.remove_option("IgnitionCycle", "waitTime")
                    if cfg.has_option("IgnitionCycle", "current"):
                        cfg.remove_option("IgnitionCycle", "current")
        # 运行账号（写入 CENTRAL，并生成 output_dir/Configuration/login.txt）
        if state.get("c_login_username") is not None:
            cfg.set("CENTRAL", "login_username", str(state.get("c_login_username") or "").strip())
        if state.get("c_login_password") is not None:
            cfg.set("CENTRAL", "login_password", str(state.get("c_login_password") or "").strip())
        # 程控电源/继电器/IG/PW：仅当“有意义配置”时才写入；未配置则从 CENTRAL 移除，不自动写入默认值
        def _is_configured_c_pwr(d: Any) -> bool:
            return isinstance(d, dict) and bool((d.get("port") or "").strip())
        def _is_configured_c_rly(lst: Any) -> bool:
            if not isinstance(lst, list) or len(lst) == 0:
                return False
            for r in lst:
                if r.get("relayID") or r.get("relayType") or (r.get("coilStatuses") and len(r.get("coilStatuses", [])) > 0) or r.get("port"):
                    return True
            return False
        def _is_configured_ig_pw(d: Any) -> bool:
            return isinstance(d, dict) and bool(d.get("equipmentType") or d.get("channelNumber"))

        if state.get("c_pwr") is not None:
            try:
                if _is_configured_c_pwr(state["c_pwr"]):
                    cfg.set("CENTRAL", "c_pwr", json.dumps(state["c_pwr"], ensure_ascii=False))
                elif cfg.has_section("CENTRAL") and cfg.has_option("CENTRAL", "c_pwr"):
                    cfg.remove_option("CENTRAL", "c_pwr")
            except Exception:
                pass
        if state.get("c_rly") is not None:
            rly = state["c_rly"]
            try:
                if _is_configured_c_rly(rly):
                    cfg.set("CENTRAL", "c_rly", json.dumps(rly, ensure_ascii=False))
                elif cfg.has_section("CENTRAL") and cfg.has_option("CENTRAL", "c_rly"):
                    cfg.remove_option("CENTRAL", "c_rly")
            except Exception:
                pass
        # IG/PW：根据 state 决定写入或删除；只要前端有传就处理，不再强依赖配置里原本已经存在 c_ig/c_pw
        if state.get("c_ig") is not None:
            try:
                if _is_configured_ig_pw(state["c_ig"]):
                    cfg.set("CENTRAL", "c_ig", json.dumps(state["c_ig"], ensure_ascii=False))
                elif cfg.has_section("CENTRAL") and cfg.has_option("CENTRAL", "c_ig"):
                    cfg.remove_option("CENTRAL", "c_ig")
            except Exception:
                pass
        if state.get("c_pw") is not None:
            try:
                if _is_configured_ig_pw(state["c_pw"]):
                    cfg.set("CENTRAL", "c_pw", json.dumps(state["c_pw"], ensure_ascii=False))
                elif cfg.has_section("CENTRAL") and cfg.has_option("CENTRAL", "c_pw"):
                    cfg.remove_option("CENTRAL", "c_pw")
            except Exception:
                pass
    # DTC
    if any(
        k in state
        for k in (
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
    ):
        if not cfg.has_section("DTC"):
            cfg.add_section("DTC")
        if state.get("d_input"):
            cfg.set("DTC", "input_excel", str(state["d_input"]).strip())
        elif state.get("d_input") == "":
            if cfg.has_option("DTC", "input_excel"):
                cfg.remove_option("DTC", "input_excel")
        elif state.get("d_input") == "":
            if cfg.has_option("DTC", "input_excel"):
                cfg.remove_option("DTC", "input_excel")
        if state.get("d_out_root"):
            cfg.set("DTC", "output_dir", str(state["d_out_root"]).strip())
        for k, opt in [
            ("d_levels", "case_levels"),
            ("d_platforms", "case_platforms"),
            ("d_models", "case_models"),
            ("d_target_versions", "case_target_versions"),
        ]:
            v = state.get(k)
            if v is not None:
                val = ",".join(v) if isinstance(v, list) else str(v)
                cfg.set("DTC", opt, val.strip() if isinstance(val, str) else val)
        if state.get("d_selected_sheets"):
            cfg.set("DTC", "selected_sheets", str(state["d_selected_sheets"]).strip())
        elif state.get("d_selected_sheets") == "":
            if cfg.has_option("DTC", "selected_sheets"):
                cfg.remove_option("DTC", "selected_sheets")
        if state.get("d_log_level"):
            cfg.set("DTC", "log_level_min", str(state["d_log_level"]).strip().lower())
        if state.get("d_uds_ecu_qualifier"):
            cfg.set("DTC", "uds_ecu_qualifier", str(state["d_uds_ecu_qualifier"]).strip())
        if state.get("d_didinfo_excel"):
            cfg.set("DTC", "didinfo_inputs", f"{str(state['d_didinfo_excel']).strip()} | *")
        elif state.get("d_didinfo_excel") == "":
            if cfg.has_option("DTC", "didinfo_inputs"):
                cfg.remove_option("DTC", "didinfo_inputs")
        if state.get("d_cin_excel"):
            cfg.set("DTC", "cin_input_excel", str(state["d_cin_excel"]).strip())
        elif state.get("d_cin_excel") == "":
            if cfg.has_option("DTC", "cin_input_excel"):
                cfg.remove_option("DTC", "cin_input_excel")
        # DTC IO Mapping：路径与 Sheet 勾选合并写入 [DTC_IOMAPPING].inputs，格式为
        # path | sheet1,sheet2；当 sheets 为空时使用 * 表示“全选”
        if "d_io_excel" in state or "d_io_selected_sheets" in state:
            if not cfg.has_section("DTC_IOMAPPING"):
                cfg.add_section("DTC_IOMAPPING")
            path = str(state.get("d_io_excel") or "").strip()
            sheets = str(state.get("d_io_selected_sheets") or "").strip()
            if path:
                val = f"{path} | {sheets if sheets else '*'}"
                cfg.set("DTC_IOMAPPING", "inputs", val)
            else:
                if cfg.has_option("DTC_IOMAPPING", "inputs"):
                    cfg.remove_option("DTC_IOMAPPING", "inputs")
        if state.get("d_didconfig_excel"):
            if not cfg.has_section("DTC_CONFIG_ENUM"):
                cfg.add_section("DTC_CONFIG_ENUM")
            cfg.set("DTC_CONFIG_ENUM", "inputs", f"{str(state['d_didconfig_excel']).strip()} | *")
        elif state.get("d_didconfig_excel") == "":
            if cfg.has_section("DTC_CONFIG_ENUM") and cfg.has_option("DTC_CONFIG_ENUM", "inputs"):
                cfg.remove_option("DTC_CONFIG_ENUM", "inputs")


@common_bp.route("/get_serial_ports", methods=["GET"])
def get_serial_ports():
    """返回可用串口列表，供中央域串口/电源/继电器配置弹窗使用。参数：无。返回：JSON { success, ports }。"""
    ports = []
    try:
        from serial.tools import list_ports  # type: ignore

        for port in list_ports.comports():
            ports.append(
                {
                    "port": getattr(port, "device", "") or "",
                    "description": getattr(port, "description", "") or "",
                }
            )
    except Exception:
        # Windows 下优先用系统真实串口列表，避免给出并不存在的 COM 号
        if os.name == "nt":
            try:
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object",
                ]
                output = subprocess.check_output(
                    cmd,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=5,
                )
                seen = set()
                for line in output.splitlines():
                    port = (line or "").strip()
                    if port and port.upper() not in seen:
                        seen.add(port.upper())
                        ports.append({"port": port, "description": "系统检测"})
            except Exception:
                ports = []
    return jsonify({"success": True, "ports": ports})


@common_bp.route("/auto_save_config", methods=["POST"])
def auto_save_config():
    """自动保存配置：将前端 state 写入 Configuration.txt。参数：data — 请求体中前端 collectCurrentState() 的 state。返回：JSON { success, message }；异常时 500。"""
    try:
        payload = request.get_json(silent=True) or {}
        state = payload.get("data") or {}
        base = _base_dir()
        mgr = ConfigManager.from_base_dir(base)
        svc = ConfigService.from_base_dir(base)
        cfg = mgr._reload()
        _apply_state_to_config(state, cfg, svc)
        mgr._write_formatted_config(cfg)
        return jsonify({"success": True, "message": "配置已自动保存"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@common_bp.route("/generate", methods=["POST"])
def generate():
    """左右后域一键生成（CAN/XML/CIN/DID/UART 等），请求体含 state 时先写入配置再执行。参数：data — 请求体中可选前端 state。返回：JSON { success, message } 或 500 { success: false, message, detail }。"""
    try:
        base = _base_dir()
        payload = request.get_json(silent=True) or {}
        state = payload.get("data", payload)
        if state:
            mgr = ConfigManager.from_base_dir(base)
            svc = ConfigService.from_base_dir(base)
            cfg = mgr._reload()
            _apply_state_to_config(state, cfg, svc)
            mgr._write_formatted_config(cfg, uds_domains=["LR_REAR"])
            _flush_config_to_disk()
        orch = TaskOrchestrator.from_base_dir(base)
        # 左右后域默认不跑 UART；仅当前端传了串口矩阵路径（中央域配置）时才尝试生成 UART
        has_uart_config = bool(state.get("c_uart") if state else False)
        # 关键字集 Clib（CIN）：仅当配置里实际有 cin_input_excel/关键字集路径时才生成 CIN；否则跳过 CIN 生成
        has_cin_config = bool(state.get("cin_excel") if state else False)
        result = orch.run_lr_bundle(
            run_can=True,
            run_xml=True,
            run_cin=has_cin_config,
            run_did=True,
            run_uart=has_uart_config,
        )
        if not result.success:
            return jsonify(
                {
                    "success": False,
                    "message": "生成过程中出错",
                    "detail": result.detail,
                }
            ), 500
        message = "一键生成完成: " + " | ".join(result.messages)
        uds_path = _resolve_uds_output_path(cfg, base, "LR_REAR") if state else ""
        if uds_path and os.path.isfile(uds_path):
            message += " | UDS.txt 生成完成"
        return jsonify({"success": True, "message": message})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@common_bp.route("/generate_central", methods=["POST"])
def generate_central():
    """中央域一键生成（CAN/XML/UART），请求体含 state 时先写入配置再执行且 skip_lr_rear。参数：data — 请求体中可选前端 state。返回：JSON { success, message } 或 500。"""
    try:
        base = _base_dir()
        payload = request.get_json(silent=True) or {}
        state = payload.get("data", payload)
        mgr = ConfigManager.from_base_dir(base)
        svc = ConfigService.from_base_dir(base)
        cfg = mgr._reload()
        if state:
            _apply_state_to_config(state, cfg, svc, skip_lr_rear=True)
            mgr._write_formatted_config(cfg, uds_domains=["CENTRAL"])
            _flush_config_to_disk()
        orch = TaskOrchestrator.from_base_dir(base)
        result = orch.run_central_bundle(run_can=True, run_xml=True, run_uart=True)
        if not result.success:
            return jsonify({"success": False, "message": " / ".join(result.messages), "detail": result.detail}), 500
        message = " / ".join(result.messages)
        uds_path = _resolve_uds_output_path(cfg, base, "CENTRAL")
        if uds_path and os.path.isfile(uds_path):
            message += " / UDS.txt 生成完成"
        return jsonify({"success": True, "message": message})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@common_bp.route("/generate_dtc", methods=["POST"])
def generate_dtc():
    """DTC 域一键生成（CAN/XML），请求体含 state 时先写入配置再执行且 skip_lr_rear。参数：data — 请求体中可选前端 state。返回：JSON { success, message } 或 500。"""
    try:
        base = _base_dir()
        payload = request.get_json(silent=True) or {}
        state = payload.get("data", payload)
        mgr = ConfigManager.from_base_dir(base)
        svc = ConfigService.from_base_dir(base)
        cfg = mgr._reload()
        if state:
            _apply_state_to_config(state, cfg, svc, skip_lr_rear=True)
            mgr._write_formatted_config(cfg, uds_domains=["DTC"])
            _flush_config_to_disk()
        orch = TaskOrchestrator.from_base_dir(base)
        # DTC 关键字集 Clib：仅当 DTC Tab 配置了 d_cin_excel 时才生成 DTC CIN，否则跳过
        has_cin_config = bool(state.get("d_cin_excel") if state else False)
        result = orch.run_dtc_bundle(run_can=True, run_xml=True, run_cin=has_cin_config)
        if not result.success:
            return jsonify(
                {
                    "success": False,
                    "message": "生成过程中出错",
                    "detail": result.detail,
                }
            ), 500
        # 与第一界面保持完全一致的提示风格：
        # - 前缀固定为「一键生成完成:」
        # - 各子任务结果（DIDConfig/DIDInfo/CIN/CAN/XML）按顺序用「 | 」拼接，
        #   包括“未生成（已按要求跳过）”这类文案
        message = "一键生成完成: " + " | ".join(result.messages)
        uds_path = _resolve_uds_output_path(cfg, base, "DTC")
        if uds_path and os.path.isfile(uds_path):
            message += " | UDS.txt 生成完成"
        return jsonify({"success": True, "message": message})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@common_bp.route("/save_preset", methods=["POST"])
def save_preset():
    """保存配置预设：弹窗选择保存路径，将 state 写入该文件并同步更新 Configuration.txt。参数：data — 请求体中前端 state；current_tab — 可选当前 Tab 标识。返回：JSON { success, message, filepath? }；用户取消时 { success: false, message }。"""
    try:
        payload = request.get_json(silent=True) or {}
        state = payload.get("data") or {}
        default_name = f"Configuration_{time.strftime('%Y-%m-%d', time.localtime())}.txt"
        path = GuiService.ask_saveas_filename(initialfile=default_name)
        if not path:
            return jsonify({"success": False, "message": "用户取消了保存"})
        base = _base_dir()
        mgr = ConfigManager.from_base_dir(base)
        svc = ConfigService.from_base_dir(base)
        cfg = mgr._reload()
        _apply_state_to_config(state, cfg, svc)
        mgr._write_formatted_config(cfg)
        mgr._write_formatted_config(cfg, path)
        return jsonify({"success": True, "message": "配置已保存", "filepath": path})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@common_bp.route("/import_preset", methods=["POST"])
def import_preset():
    """导入配置预设：弹窗选择配置文件，读取并返回 state 供前端恢复。参数：current_tab — 可选当前 Tab 标识（预留）。返回：JSON { success, data? } 或 { success: false, message }。"""
    try:
        path = GuiService.ask_open_config_filename()
        if not path:
            return jsonify({"success": False, "message": "用户取消了选择"})
        base = _base_dir()
        mgr = ConfigManager(base, config_path=path)
        data = mgr.load_ui_data()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

