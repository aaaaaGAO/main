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

import logging
import os
import subprocess
import time
from typing import Any, Dict

try:
    from serial.tools import list_ports as serial_list_ports  # type: ignore
except ImportError:  # pragma: no cover - pyserial optional
    serial_list_ports = None

from flask import Blueprint, jsonify, request

from services.config_manager import ConfigManager
from services.config_constants import (
    SECTION_CENTRAL,
    SECTION_DTC,
    SECTION_LR_REAR,
)
from services.config_service import ConfigService
from services.filter_service import parse_shaixuan_config
from services.gui_service import GuiService
from services.state_config_service import StateConfigService
from services.task_orchestrator import TaskOrchestrator
from .route_helpers import get_base_dir

common_bp = Blueprint("common", __name__)
logger = logging.getLogger(__name__)


def current_base_dir() -> str:
    """获取当前应用的项目根目录（主配置 / filter_options.ini 所在目录）。参数：无。返回：根目录绝对路径。"""
    return get_base_dir(__file__)


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
    base_dir = current_base_dir()
    svc = ConfigService.from_base_dir(base_dir)
    data: Dict[str, Any] = svc.get_lr_rear()
    return jsonify({"success": True, "data": data})


@common_bp.route("/get_filter_options", methods=["GET"])
def get_filter_options():
    """获取筛选框选项（等级/平台/车型/UDS_ECU_qualifier），数据来自 config/filter_options.ini。参数：无。返回：JSON 筛选选项。"""
    base_dir = current_base_dir()
    filters = parse_shaixuan_config(base_dir)
    return jsonify(filters)


@common_bp.route("/load_config", methods=["GET"])
def load_config():
    """加载完整配置供前端展示（ConfigManager.load_ui_data）。参数：base_dir — 可选，配置根目录，缺省为当前 BASE_DIR。返回：JSON { success, data }。"""
    base_dir = request.args.get("base_dir") or current_base_dir()
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
    except Exception as error:
        return jsonify({"success": False, "message": str(error)})


@common_bp.route("/parse_file_structure", methods=["POST"])
def parse_file_structure():
    """解析指定文件或文件夹结构，供前端树形展示。参数：path — 请求体中文件或文件夹路径。返回：JSON 树形结构；失败时 { success: false, message }。"""
    try:
        payload = request.get_json(silent=True) or {}
        path = (payload.get("path") or "").strip()
        result = GuiService.parse_file_structure(path, base_dir=current_base_dir())
        return jsonify(result)
    except Exception as error:
        return jsonify({"success": False, "message": str(error)})


def jsonify_generation_result(
    orch: TaskOrchestrator,
    result,
    *,
    config,
    section: str,
    success_prefix: str = "",
    success_separator: str = " | ",
    failure_message: str | None = "生成过程中出错",
    failure_separator: str = " | ",
):
    if not result.success:
        message = failure_message if failure_message is not None else failure_separator.join(result.messages)
        return jsonify({"success": False, "message": message, "detail": result.detail}), 500
    message = orch.build_result_message(
        result,
        config=config,
        section=section,
        prefix=success_prefix,
        separator=success_separator,
    )
    return jsonify({"success": True, "message": message})

@common_bp.route("/get_serial_ports", methods=["GET"])
def get_serial_ports():
    """返回可用串口列表，供中央域串口/电源/继电器配置弹窗使用。参数：无。返回：JSON { success, ports }。"""
    ports = []
    try:
        if serial_list_ports is None:
            raise ImportError("pyserial not available")
        for port in serial_list_ports.comports():
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
    """自动保存配置：将前端 state 写入当前主配置文件。参数：data — 请求体中前端 collectCurrentState() 的 state。返回：JSON { success, message }；异常时 500。"""
    try:
        payload = request.get_json(silent=True) or {}
        state = payload.get("data") or {}
        base = current_base_dir()
        StateConfigService.from_base_dir(base).persist_state_config(state)
        return jsonify({"success": True, "message": "配置已自动保存"})
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@common_bp.route("/generate", methods=["POST"])
def generate():
    """左右后域一键生成（DIDConfig/DIDInfo/CIN/CAN/XML），不含 UART。
    请求体含 state 时先写入配置再执行。"""
    try:
        started = time.perf_counter()
        base = current_base_dir()
        state_config_service = StateConfigService.from_base_dir(base)
        payload = request.get_json(silent=True) or {}
        state = payload.get("data", payload)
        logger.info(
            "[route.generate] event=start domain=%s validate_before_run=%s payload_keys=%s",
            SECTION_LR_REAR,
            payload.get("validate_before_run", True),
            sorted(list(payload.keys())),
        )
        config = state_config_service.prepare_generation_config(
            state=state,
            uds_domain=SECTION_LR_REAR,
        )
        orch = TaskOrchestrator.from_base_dir(base)
        lr_flags = state_config_service.get_lr_generation_flags(state)
        lr_flags["validate_before_run"] = payload.get("validate_before_run", True)
        logger.info("[route.generate] event=flags domain=%s flags=%s", SECTION_LR_REAR, lr_flags)
        result = orch.run_lr_bundle(**lr_flags)
        logger.info(
            "[route.generate] event=done domain=%s success=%s elapsed_ms=%.1f",
            SECTION_LR_REAR,
            result.success,
            (time.perf_counter() - started) * 1000.0,
        )
        return jsonify_generation_result(
            orch,
            result,
            config=config,
            section=SECTION_LR_REAR,
            success_prefix="一键生成完成: ",
            success_separator=" | ",
            failure_message="生成过程中出错",
        )
    except Exception as error:
        logger.exception("[route.generate] event=error domain=%s", SECTION_LR_REAR)
        return jsonify({"success": False, "message": str(error)}), 500


@common_bp.route("/generate_central", methods=["POST"])
def generate_central():
    """中央域一键生成（CAN/XML，UART 仅当 state 中已配置矩阵或串口时执行），请求体含 state 时先写入配置再执行且 skip_lr_rear。
    参数：data — 请求体中可选前端 state（`c_uart` / `c_uart_comm`）；validate_before_run — 可选，默认 True。
    返回：JSON { success, message } 或 500。"""
    try:
        started = time.perf_counter()
        base = current_base_dir()
        state_config_service = StateConfigService.from_base_dir(base)
        payload = request.get_json(silent=True) or {}
        state = payload.get("data", payload)
        logger.info(
            "[route.generate_central] event=start domain=%s validate_before_run=%s payload_keys=%s",
            SECTION_CENTRAL,
            payload.get("validate_before_run", True),
            sorted(list(payload.keys())),
        )
        config = state_config_service.prepare_generation_config(
            state=state,
            uds_domain=SECTION_CENTRAL,
            skip_lr_rear=True,
        )
        orch = TaskOrchestrator.from_base_dir(base)
        central_flags = state_config_service.get_central_generation_flags(state)
        central_flags["validate_before_run"] = payload.get("validate_before_run", True)
        logger.info("[route.generate_central] event=flags domain=%s flags=%s", SECTION_CENTRAL, central_flags)
        result = orch.run_central_bundle(**central_flags)
        logger.info(
            "[route.generate_central] event=done domain=%s success=%s elapsed_ms=%.1f",
            SECTION_CENTRAL,
            result.success,
            (time.perf_counter() - started) * 1000.0,
        )
        return jsonify_generation_result(
            orch,
            result,
            config=config,
            section=SECTION_CENTRAL,
            success_separator=" / ",
            failure_message=None,
            failure_separator=" / ",
        )
    except Exception as error:
        logger.exception("[route.generate_central] event=error domain=%s", SECTION_CENTRAL)
        return jsonify({"success": False, "message": str(error)}), 500


@common_bp.route("/generate_dtc", methods=["POST"])
def generate_dtc():
    """DTC 域一键生成（CAN/XML），请求体含 state 时先写入配置再执行且 skip_lr_rear。
    参数：data — 请求体中可选前端 state；validate_before_run — 可选，默认 True；
    返回：JSON { success, message } 或 500。"""
    try:
        started = time.perf_counter()
        base = current_base_dir()
        state_config_service = StateConfigService.from_base_dir(base)
        payload = request.get_json(silent=True) or {}
        state = payload.get("data", payload)
        logger.info(
            "[route.generate_dtc] event=start domain=%s validate_before_run=%s payload_keys=%s",
            SECTION_DTC,
            payload.get("validate_before_run", True),
            sorted(list(payload.keys())),
        )
        config = state_config_service.prepare_generation_config(
            state=state,
            uds_domain=SECTION_DTC,
            skip_lr_rear=True,
        )
        orch = TaskOrchestrator.from_base_dir(base)
        dtc_flags = state_config_service.get_dtc_generation_flags(state)
        dtc_flags["validate_before_run"] = payload.get("validate_before_run", True)
        logger.info("[route.generate_dtc] event=flags domain=%s flags=%s", SECTION_DTC, dtc_flags)
        result = orch.run_dtc_bundle(**dtc_flags)
        logger.info(
            "[route.generate_dtc] event=done domain=%s success=%s elapsed_ms=%.1f",
            SECTION_DTC,
            result.success,
            (time.perf_counter() - started) * 1000.0,
        )
        return jsonify_generation_result(
            orch,
            result,
            config=config,
            section=SECTION_DTC,
            success_prefix="一键生成完成: ",
            success_separator=" | ",
            failure_message="生成过程中出错",
        )
    except Exception as error:
        logger.exception("[route.generate_dtc] event=error domain=%s", SECTION_DTC)
        return jsonify({"success": False, "message": str(error)}), 500


@common_bp.route("/save_preset", methods=["POST"])
def save_preset():
    """保存配置预设：弹窗选择保存路径，将 state 写入该文件并同步更新当前主配置文件。参数：data — 请求体中前端 state；current_tab — 可选当前 Tab 标识。返回：JSON { success, message, filepath? }；用户取消时 { success: false, message }。"""
    try:
        payload = request.get_json(silent=True) or {}
        state = payload.get("data") or {}
        default_name = f"Configuration_{time.strftime('%Y-%m-%d', time.localtime())}.ini"
        path = GuiService.ask_saveas_filename(initialfile=default_name)
        if not path:
            return jsonify({"success": False, "message": "用户取消了保存"})
        base = current_base_dir()
        StateConfigService.from_base_dir(base).persist_state_config(state, extra_write_path=path)
        return jsonify({"success": True, "message": "配置已保存", "filepath": path})
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@common_bp.route("/import_preset", methods=["POST"])
def import_preset():
    """导入配置预设：弹窗选择配置文件，读取并返回 state 供前端恢复。参数：current_tab — 可选当前 Tab 标识（预留）。返回：JSON { success, data? } 或 { success: false, message }。"""
    try:
        path = GuiService.ask_open_config_filename()
        if not path:
            return jsonify({"success": False, "message": "用户取消了选择"})
        base = current_base_dir()
        mgr = ConfigManager(base, config_path=path)
        data = mgr.load_ui_data()
        return jsonify({"success": True, "data": data})
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500

