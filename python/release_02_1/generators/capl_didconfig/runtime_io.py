#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIDConfig 运行期 IO 与编排用 API（去脚本化）。

从根目录迁入：resolve_base_dir、load_runtime、init_logging（setup_generator_logger + tee）。
供 DIDConfigGeneratorService 与任务编排层调用。
"""

from __future__ import annotations

import os
from typing import Optional

from core.generator_config import GeneratorConfig
from core.generator_logging import GeneratorLogger, LogSpecConfig
from core.run_context import tee_stdout_stderr

from utils.logger import PROGRESS_LEVEL, ExcludeSubstringsFilter

from infra.filesystem.pathing import RuntimePathResolver


def resolve_base_dir() -> str:
    """解析 DIDConfig 运行根目录（项目根）。"""
    return RuntimePathResolver.resolve_base_dir(__file__)


def load_runtime(base_dir: str) -> Optional[GeneratorConfig]:
    """阶段 ①：读取 DIDConfig 配置（GeneratorConfig）。"""
    gconfig = GeneratorConfig(base_dir).load()
    if not gconfig.config_path or not os.path.exists(gconfig.config_path):
        print(f"错误: 找不到配置文件 {gconfig.config_path or 'Configuration.ini'}")
        return None
    return gconfig


def setup_generator_logger(base_dir: str) -> GeneratorLogger:
    """创建 DIDConfig 双日志管理器（parse + gen）。"""
    return GeneratorLogger(
        base_dir,
        logger_name="generate_did_config",
        log_specs=[
            # 解析表格日志：排除“成功生成:”行（包括普通日志和 PROGRESS 进度日志）
            LogSpecConfig(
                subdir="parse",
                basename="DIDConfiguration_Matrix.log",
                file_filters=(ExcludeSubstringsFilter("成功生成:"),),
                progress_filters=(ExcludeSubstringsFilter("成功生成:"),),
            ),
            # 生成文件日志：完整保留所有日志
            ("gen", "generate_did_config.log"),
        ],
    )


def init_logging(base_dir: str) -> tuple:
    """
    阶段 ②：初始化 DIDConfig 双日志与 Tee。
    返回 (log_mgr, logger, old_stdout, old_stderr)。
    """
    log_mgr = setup_generator_logger(base_dir)
    logger = log_mgr.setup()
    old_stdout, old_stderr = tee_stdout_stderr(
        logger,
        skip_prefixes=("检测到重复选项 [PATHS] ",),
    )
    return log_mgr, logger, old_stdout, old_stderr


def get_progress_level() -> int:
    """供 service 使用的 PROGRESS_LEVEL。"""
    return PROGRESS_LEVEL


class DIDConfigRuntimeIOUtility:
    """DIDConfig 运行期 IO 与编排接口统一工具类。"""

    resolve_base_dir = staticmethod(resolve_base_dir)
    load_runtime = staticmethod(load_runtime)
    setup_generator_logger = staticmethod(setup_generator_logger)
    init_logging = staticmethod(init_logging)
    get_progress_level = staticmethod(get_progress_level)
