#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 HTTP JSON 体中解析前端 state 的工具类（无 Flask 依赖），供路由与 `GenerationRouteService` 等共用。

与 `web/routes`、一键生成、配置自动保存等请求体约定对齐，避免在多处手写 ``payload.get("data")`` 分支。
"""

from __future__ import annotations

from typing import Any, Mapping, TypedDict

from services.http_api_constants import api_error_dict


class GenerationPayload(TypedDict, total=False):
    """一键生成相关请求体的最小结构定义（允许增量扩展）。"""

    data: dict[str, Any]
    validate_before_run: bool


class RequestPayloadUtility:
    """HTTP JSON 请求体解析与错误响应拼装工具类。"""

    @staticmethod
    def merge_ui_state_from_data_only(payload: dict[str, Any]) -> dict[str, Any]:
        """仅接受 ``data`` 键内对象，用于自动保存、导出预设等（不接受整包作 state）。

        参数：payload — 前端 POST JSON 解析后的 dict。

        返回：当 ``data`` 为 dict 时返回其拷贝语义的对象；否则返回空 dict。
        """
        raw = payload.get("data")
        if isinstance(raw, dict):
            return raw
        return {}

    @staticmethod
    def merge_generation_state_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        """一键生成用：优先取 ``data`` 为全量 state；无 ``data`` 时兼容把整个 JSON 当作 state（历史格式）。

        参数：payload — 一键生成接口收到的 dict。

        返回：供 `StateConfigService` / 编排器使用的 state dict；若无法解析则返回空 dict 或空映射。
        """
        raw = payload.get("data")
        if raw is not None:
            return raw if isinstance(raw, dict) else {}
        return dict(payload)

    @staticmethod
    def client_error_body(message: str, *, detail: str | None = None) -> dict[str, Any]:
        """拼装与现有 API 一致的错误响应体（非 Flask Response，仅 dict）。

        参数：message — 用户可见主错误信息。detail — 可选附加说明，将写入同 dict 的 ``detail`` 键。

        返回：含 ``success: False`` 与 ``message`` 的 dict，若 `detail` 非空则含 ``detail`` 键。
        """
        return api_error_dict(message, detail=detail)
