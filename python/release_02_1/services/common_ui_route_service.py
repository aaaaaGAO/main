#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`web.routes.common` 对应的业务层：与 Flask 解耦，**只返回** ``(响应 dict, HTTP 状态码)``。

涵盖：LR 配置片段、筛选项、整包加载配置、串口枚举、Tk 选文件/解析结构、
自动保存/另存预设、从预设读回。异常统一转为 ``client_error_body`` 风格 JSON，
由路由侧 ``jsonify``；不在此模块内记录 Flask ``request``。
部分方法使用 `service_route_result_decorator.guard_service_route_tuple` 收敛重复 ``try/except``。

与 `StateConfigService`、`ConfigService`、`ConfigManager` 协作，保持路由文件「薄」。
"""

from __future__ import annotations

import os
import subprocess
import time
import importlib
from typing import Any

from services.http_api_constants import (
    HttpStatus,
    RESPONSE_KEY_FILEPATH,
    RESPONSE_KEY_FILENAME,
    RESPONSE_KEY_PATH,
    RESPONSE_KEY_PORT_DESCRIPTION,
    RESPONSE_KEY_PORT_DEVICE,
    RESPONSE_KEY_PORTS,
    api_error,
    api_success,
    make_json_tuple,
)
from services.config_manager import ConfigManager
from services.config_service import ConfigService
from services.filter_service import parse_shaixuan_config
from services.gui_service import GuiService
from services.request_payload_utils import merge_ui_state_from_data_only
from services.service_route_result_decorator import guard_service_route_tuple
from services.state_config_service import StateConfigService

serial_list_ports = None
try:
    serial_list_ports = importlib.import_module("serial.tools.list_ports")
except ModuleNotFoundError:
    pass


class CommonUiRouteService:
    """
    封装 Common 蓝图中**非一键生成**的 UI 操作：无 Flask 依赖，便于单测与复用。

    各方法名与 `web/routes/common.py` 中 `*_result` 调用一一对应。
    """

    def __init__(self, base_dir: str) -> None:
        """
        参数：base_dir — 工程根（含 `config/`，与 `app.config['BASE_DIR']` 一致）。

        返回：无。
        """
        self.base_dir = base_dir

    @guard_service_route_tuple(http_status_on_error=HttpStatus.INTERNAL_SERVER_ERROR)
    def lr_rear_config_result(self) -> tuple[dict[str, Any], int]:
        """
        读取并返回左右后域相关配置子集（经 `ConfigService.get_lr_rear`）。

        参数：无（使用 `self.base_dir`）。

        返回：成功为 ``({"success": True, "data": ...}, 200)``；异常为
        ``(client_error_body(...), 500)``（由 ``guard_service_route_tuple`` 统一捕获）。
        """
        service = ConfigService.from_base_dir(self.base_dir)
        payload_data: dict[str, Any] = service.get_lr_rear()
        return api_success(data=payload_data)

    @guard_service_route_tuple(http_status_on_error=HttpStatus.INTERNAL_SERVER_ERROR)
    def filter_options_result(self) -> tuple[dict[str, Any], int]:
        """
        解析 `config/filter_options.ini` 中筛选项，结构与 `FilterService.parse_shaixuan_config` 一致。

        参数：无。

        返回：成功时**直接**返回 ``(dict, 200)``（**无**外裹 ``success`` 键，与历史前端兼容）；
        异常为错误体 + 500（装饰器统一处理）。
        """
        payload_data = parse_shaixuan_config(self.base_dir)
        return make_json_tuple(payload_data, HttpStatus.OK)

    @guard_service_route_tuple(http_status_on_error=HttpStatus.INTERNAL_SERVER_ERROR)
    def load_config_result(self) -> tuple[dict[str, Any], int]:
        """
        从主/固定配置加载整站 UI 所需 `load_ui_data` 结构，供首屏与「加载配置」使用。

        参数：无。

        返回：``({"success": True, "data": ...}, 200)`` 或 ``(client_error_body, 500)``（异常由装饰器统一处理）。
        """
        manager = ConfigManager.from_base_dir(self.base_dir)
        payload_data = manager.load_ui_data()
        return api_success(data=payload_data)

    @guard_service_route_tuple(http_status_on_error=HttpStatus.OK)
    def serial_ports_result(self) -> tuple[dict[str, Any], int]:
        """
        枚举串口：优先 `pyserial` 的 `comports()`，不可用时在 Windows 上退化为 PowerShell 枚举。

        参数：无。

        返回：通常为 ``({"success": True, "ports": [{"port","description"},...]}, 200)``。
        最外层异常时**仍为 200** 与错误体（与历史行为一致，避免前端误断连）。
        """
        ports: list[dict[str, str]] = []
        try:
            if serial_list_ports is None:
                raise ImportError("pyserial not available")
            for port in serial_list_ports.comports():
                ports.append(
                    {
                        RESPONSE_KEY_PORT_DEVICE: getattr(port, "device", "") or "",
                        RESPONSE_KEY_PORT_DESCRIPTION: getattr(port, "description", "") or "",
                    }
                )
        except Exception:
            if os.name == "nt":
                try:
                    command_parts = [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object",
                    ]
                    output_value = subprocess.check_output(
                        command_parts,
                        text=True,
                        encoding="utf-8",
                        errors="ignore",
                        timeout=5,
                    )
                    seen_names: set[str] = set()
                    for line in output_value.splitlines():
                        port_name = (line or "").strip()
                        if port_name and port_name.upper() not in seen_names:
                            seen_names.add(port_name.upper())
                            ports.append(
                                {
                                    RESPONSE_KEY_PORT_DEVICE: port_name,
                                    RESPONSE_KEY_PORT_DESCRIPTION: "系统检测",
                                }
                            )
                except Exception:
                    ports = []
        return api_success(extra={RESPONSE_KEY_PORTS: ports})

    @guard_service_route_tuple(http_status_on_error=HttpStatus.OK)
    def select_file_result(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """
        调 `GuiService.select_path` 打开 Tk 对话框，返回用户选择的绝对路径。

        参数：payload — 可含 ``file_type``：``"file"`` 或 ``"folder"``，缺省为文件。

        返回：成功为 ``path`` / ``filename``；取消为 ``success: False``（HTTP 200）；
        异常为错误体（HTTP 200，与现网一致）。
        """
        file_type = payload.get("file_type", "file")
        chosen_path = GuiService.select_path(file_type=file_type)
        if chosen_path:
            return api_success(
                extra={
                    RESPONSE_KEY_PATH: chosen_path,
                    RESPONSE_KEY_FILENAME: os.path.basename(chosen_path),
                },
            )
        return api_error("用户取消了选择", status=HttpStatus.OK)

    @guard_service_route_tuple(http_status_on_error=HttpStatus.OK)
    def parse_file_structure_result(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """
        调 `GuiService.parse_file_structure` 解析路径下 Excel/目录结构。

        参数：payload — 须含 ``path``，为待解析的绝对或相对路径（相对 `base_dir` 解析由下层完成）。

        返回：``GuiService`` 返回的 dict 与 200，或错误体 + 200。
        """
        target_path = (payload.get(RESPONSE_KEY_PATH) or "").strip()
        result = GuiService.parse_file_structure(target_path, base_dir=self.base_dir)
        return make_json_tuple(result, HttpStatus.OK)

    @guard_service_route_tuple(http_status_on_error=HttpStatus.INTERNAL_SERVER_ERROR)
    def auto_save_config_result(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """
        从 ``payload["data"]`` 取 state，经 `StateConfigService.persist_state_config` 写主配置。

        参数：payload — 前端自动保存 JSON，通常仅 ``data`` 内为可合并字段。

        返回：``success`` + 提示文案；状态码 200 为成功，500 为 `persist_state_config` 异常。
        """
        state = merge_ui_state_from_data_only(payload)
        StateConfigService.from_base_dir(self.base_dir).persist_state_config(state)
        return api_success("配置已自动保存")

    @guard_service_route_tuple(http_status_on_error=HttpStatus.INTERNAL_SERVER_ERROR)
    def save_preset_result(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """
        将 state 另存为**额外一份** INI：先弹「另存为」对话框，再 `persist_state_config(..., extra_write_path=...)`。

        参数：payload — 同自动保存，从 ``data`` 取 state。

        返回：含 ``filepath`` 的成功体；用户取消为 ``success: False``（200）；失败 500。
        """
        state = merge_ui_state_from_data_only(payload)
        default_name = f"Configuration_{time.strftime('%Y-%m-%d', time.localtime())}.ini"
        chosen_path = GuiService.ask_saveas_filename(initialfile=default_name)
        if not chosen_path:
            return api_error("用户取消了保存", status=HttpStatus.OK)
        StateConfigService.from_base_dir(self.base_dir).persist_state_config(
            state,
            extra_write_path=chosen_path,
        )
        return api_success("配置已保存", extra={RESPONSE_KEY_FILEPATH: chosen_path})

    @guard_service_route_tuple(http_status_on_error=HttpStatus.INTERNAL_SERVER_ERROR)
    def import_preset_result(self) -> tuple[dict[str, Any], int]:
        """
        用户选择一 INI 文件，以该路径构造 `ConfigManager` 并 `load_ui_data` 回灌前端。

        参数：无（路径经 Tk 对话框选择）。

        返回：``{"success": True, "data": load_ui_data 结果}`` 或取消/错误信息。
        """
        chosen_path = GuiService.ask_open_config_filename()
        if not chosen_path:
            return api_error("用户取消了选择", status=HttpStatus.OK)
        manager = ConfigManager(self.base_dir, config_path=chosen_path)
        payload_data = manager.load_ui_data()
        return api_success(data=payload_data)
