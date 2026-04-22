#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「一键生成」类路由的**服务层**：合并请求体、写配置、解析各域子任务开关、调用 `TaskOrchestrator`。

与 `web/routes/common.py` 中 ``/generate``、``/generate_central``、``/generate_dtc`` 对应：

- 使用 `merge_generation_state_from_payload` 统一 JSON 体格式；
- 经 `StateConfigService.prepare_generation_config` 在生成前落盘；
- 用 `GenerationRouteOptions` 描述**域**、**skip_lr_rear**、以及 `StateConfigService` 上
  取 flags 的方法名、编排器上的 bundle 方法名、成功/失败展示模板。

`safe_execute_generation_from_payload_fetch` 将 Flask ``request.get_json`` 的惰性读取与
异常兜底收拢，避免每个路由重复 try/except。
"""

from __future__ import annotations

import inspect
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from services.config_constants import SECTION_CENTRAL, SECTION_DTC, SECTION_LR_REAR
from services.request_payload_utils import merge_generation_state_from_payload
from services.state_config_service import StateConfigService
from services.task_orchestrator import TaskOrchestrator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationRouteOptions:
    """
    描述「某条生成路由」在 **StateConfigService / TaskOrchestrator** 上的固定绑定关系。

    字段说明：
        route_name — 日志与异常信息中的路由标识（如 ``generate_central``）。
        domain — UDS/配置节名：``LR_REAR``、``CENTRAL``、``DTC`` 之一，用于 `prepare_generation_config`。
        skip_lr_rear — 为 True 时写配置跳过左右后区（中央/DTC 保存勿覆盖 LR 节）。
        flag_resolver_name — `StateConfigService` 上**方法名字符串**，
            如 ``get_central_generation_flags``，将合并为可调用并传入 state。
        orchestrator_method_name — `TaskOrchestrator` 上**方法名**，如 ``run_central_bundle``。
        success_prefix / success_separator — 成功摘要文案前后缀，传入 `build_result_message`。
        failure_message — 为 None 时表示失败消息用 `failure_separator` 拼接 `result.messages`。
        failure_separator — 失败时拼接 ``result.messages`` 或覆盖文案的分隔符。
    """

    route_name: str
    domain: str
    skip_lr_rear: bool
    flag_resolver_name: str
    orchestrator_method_name: str
    success_prefix: str = ""
    success_separator: str = " | "
    failure_message: str | None = "生成过程中出错"
    failure_separator: str = " | "


class GenerationRouteService:
    """
    执行单次「从 payload 到编排结果」的完整流水线，**不**接触 Flask，仅返回 ``(dict, status)``。

    由 `safe_execute_generation_from_payload_fetch` 或测试代码直接调用。
    """

    def __init__(
        self,
        *,
        base_dir: str,
        state_config_service: StateConfigService,
        task_orchestrator: TaskOrchestrator,
    ) -> None:
        """
        参数：
            base_dir — 工程根（当前逻辑主要经注入的服务访问配置，仍保留作扩展）。
            state_config_service — 已针对 `base_dir` 构建的 `StateConfigService`。
            task_orchestrator — 同 `base_dir` 下的 `TaskOrchestrator`。
        返回：无。
        """
        self.base_dir = base_dir
        self.state_config_service = state_config_service
        self.task_orchestrator = task_orchestrator

    @classmethod
    def from_base_dir(cls, base_dir: str) -> "GenerationRouteService":
        """
        以工程根同时构造 `StateConfigService` 与 `TaskOrchestrator` 的便捷工厂。

        参数：base_dir — 工程根目录。

        返回：配置好的 `GenerationRouteService` 实例。
        """
        return cls(
            base_dir=base_dir,
            state_config_service=StateConfigService.from_base_dir(base_dir),
            task_orchestrator=TaskOrchestrator.from_base_dir(base_dir),
        )

    def execute_from_payload(
        self,
        payload: dict[str, Any],
        *,
        options: GenerationRouteOptions,
    ) -> tuple[dict[str, Any], int]:
        """
        合并 state → 落盘主配置（若 state 非空）→ 解析子任务 bool → 调用对应 ``run_*_bundle``。

        参数：
            payload — 原始 JSON dict，可含 ``data``、``validate_before_run`` 等键。
            options — 域与绑定方法名，见 `GenerationRouteOptions` 字段说明。

        返回：成功为 ``({"success": True, "message": ...}, 200)``，摘要由
        `TaskOrchestrator.build_result_message` 生成；失败为 ``(success: False, message, detail), 500``。
        """
        started = time.perf_counter()
        state = merge_generation_state_from_payload(payload)
        validate_before_run = payload.get("validate_before_run", True)
        logger.info(
            "[route.%s] event=start domain=%s validate_before_run=%s payload_keys=%s",
            options.route_name,
            options.domain,
            validate_before_run,
            sorted(list(payload.keys())),
        )

        config = self.state_config_service.prepare_generation_config(
            state=state,
            uds_domain=options.domain,
            skip_lr_rear=options.skip_lr_rear,
        )
        resolve_flags = getattr(self.state_config_service, options.flag_resolver_name)
        generation_flags = resolve_flags(state)
        generation_flags["validate_before_run"] = validate_before_run
        logger.info(
            "[route.%s] event=flags domain=%s flags=%s",
            options.route_name,
            options.domain,
            generation_flags,
        )

        run_bundle = getattr(self.task_orchestrator, options.orchestrator_method_name)
        run_bundle_signature = inspect.signature(run_bundle)
        accepted_parameters = {
            parameter_name
            for parameter_name, parameter in run_bundle_signature.parameters.items()
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }
        filtered_generation_flags = {
            item_key: item_value
            for item_key, item_value in generation_flags.items()
            if item_key in accepted_parameters
        }
        unknown_flag_names = sorted(set(generation_flags.keys()) - accepted_parameters)
        if unknown_flag_names:
            logger.warning(
                "[route.%s] event=ignore_unknown_flags method=%s unknown_flags=%s",
                options.route_name,
                options.orchestrator_method_name,
                unknown_flag_names,
            )

        required_parameter_names = [
            parameter_name
            for parameter_name, parameter in run_bundle_signature.parameters.items()
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
            and parameter.default is inspect.Parameter.empty
        ]
        missing_parameter_names = sorted(
            parameter_name
            for parameter_name in required_parameter_names
            if parameter_name not in filtered_generation_flags
        )
        if missing_parameter_names:
            raise TypeError(
                f"{options.orchestrator_method_name} 缺少必填参数: {', '.join(missing_parameter_names)}; "
                f"当前 flags: {sorted(filtered_generation_flags.keys())}"
            )

        result = run_bundle(**filtered_generation_flags)
        logger.info(
            "[route.%s] event=done domain=%s success=%s elapsed_ms=%.1f",
            options.route_name,
            options.domain,
            result.success,
            (time.perf_counter() - started) * 1000.0,
        )

        if not result.success:
            message = (
                options.failure_message
                if options.failure_message is not None
                else options.failure_separator.join(result.messages)
            )
            return {"success": False, "message": message, "detail": result.detail}, 500

        message = self.task_orchestrator.build_result_message(
            result,
            config=config,
            section=options.domain,
            prefix=options.success_prefix,
            separator=options.success_separator,
        )
        return {"success": True, "message": message}, 200


def generation_route_options_lr_rear() -> GenerationRouteOptions:
    """
    左右后域「一键生成」的路由元信息：跑 LR 子任务，编排方法 `run_lr_bundle`，flags 来自 `get_lr_generation_flags`。

    参数：无。返回：冻结的 `GenerationRouteOptions`。
    """
    return GenerationRouteOptions(
        route_name="generate",
        domain=SECTION_LR_REAR,
        skip_lr_rear=False,
        flag_resolver_name="get_lr_generation_flags",
        orchestrator_method_name="run_lr_bundle",
        success_prefix="一键生成完成: ",
        success_separator=" | ",
        failure_message="生成过程中出错",
        failure_separator=" | ",
    )


def generation_route_options_central() -> GenerationRouteOptions:
    """
    中央域：写配置时 **skip_lr_rear=True**，`get_central_generation_flags` + `run_central_bundle`；失败消息默认拼 `result.messages`。

    参数：无。返回：`GenerationRouteOptions`。
    """
    return GenerationRouteOptions(
        route_name="generate_central",
        domain=SECTION_CENTRAL,
        skip_lr_rear=True,
        flag_resolver_name="get_central_generation_flags",
        orchestrator_method_name="run_central_bundle",
        success_prefix="",
        success_separator=" / ",
        failure_message=None,
        failure_separator=" / ",
    )


def generation_route_options_dtc() -> GenerationRouteOptions:
    """
    DTC 域：`get_dtc_generation_flags` + `run_dtc_bundle`，不覆盖 `[LR_REAR]`。

    参数：无。返回：`GenerationRouteOptions`。
    """
    return GenerationRouteOptions(
        route_name="generate_dtc",
        domain=SECTION_DTC,
        skip_lr_rear=True,
        flag_resolver_name="get_dtc_generation_flags",
        orchestrator_method_name="run_dtc_bundle",
        success_prefix="一键生成完成: ",
        success_separator=" | ",
        failure_message="生成过程中出错",
        failure_separator=" | ",
    )


def safe_execute_generation_from_payload_fetch(
    fetch_payload: Callable[[], dict[str, Any]],
    *,
    base_dir: str,
    options: GenerationRouteOptions,
    route_logger: logging.Logger,
) -> tuple[dict[str, Any], int]:
    """
    从惰性回调取得 JSON（通常 ``lambda: request.get_json(silent=True) or {}``），再执行
    `GenerationRouteService.execute_from_payload`；**任意**异常打栈并统一 500。

    参数：
        fetch_payload — 无参可调用，返回本次请求的 payload dict（勿在注册路由前提前读 body）。
        base_dir — 工程根。
        options — 域与编排绑定，见同模块工厂函数。
        route_logger — 一般为蓝图 ``logger``，用于 ``exception`` 级日志。

    返回：与 `execute_from_payload` 相同；异常时为 ``{"success": False, "message": str(error)}, 500``。
    """
    try:
        payload = fetch_payload()
        service = GenerationRouteService.from_base_dir(base_dir)
        return service.execute_from_payload(payload, options=options)
    except Exception as error:
        route_logger.exception(
            "[route.%s] event=error domain=%s",
            options.route_name,
            options.domain,
        )
        return {"success": False, "message": str(error)}, 500
