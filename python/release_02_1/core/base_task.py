#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BaseGeneratorTask —— 模板方法基类

所有生成器任务（CAN、CIN、XML、UART、DID）的通用执行流程：

    1. setup()         —— 初始化日志、配置、上下文
    2. extract_data()  —— 从 Excel / 配置文件读取源数据
    3. transform(data) —— 将源数据转换为目标格式
    4. load(content)   —— 将内容写入输出文件
    5. cleanup()       —— 恢复 stdout/stderr、flush 日志

子类只需实现 extract_data / transform / load，
通用的日志初始化、异常处理、stdout 劫持由基类统一管理。
"""

from __future__ import annotations

import logging
import os
import sys
from abc import ABC, abstractmethod
from typing import Any, Optional

from infra.filesystem import get_base_dir, resolve_main_config_path
from infra.logger import PROGRESS_LEVEL, TeeToLogger
from infra.config import read_config_if_exists, read_fixed_config
from core.run_context import clear_run_logger


class BaseGeneratorTask(ABC):
    """
    生成器任务基类（模板方法模式）。

    子类必须实现：
        - task_name       : 任务显示名（如 "CAN 生成"）
        - setup_logging() : 初始化该任务专用的 logger
        - extract_data()  : 提取源数据 -> Any
        - transform(data) : 转换 -> Any
        - load(content)   : 写入文件

    可选覆盖：
        - tee_error_prefixes / tee_warning_prefixes : TeeToLogger 前缀配置
        - cleanup()        : 额外清理逻辑
    """

    def __init__(self, base_dir: str | None = None, *, reference_file: str | None = None):
        """
        初始化基类。

        参数:
            base_dir: 项目根目录路径，为 None 时自动推断
            reference_file: 用于推断根目录的参考文件路径
        """
        self.base_dir = base_dir or get_base_dir(reference_file or __file__)
        self.config_path = resolve_main_config_path(self.base_dir)
        self.config = None
        self.fixed_config: dict[str, str] = {}
        self.logger: Optional[logging.Logger] = None
        self.previous_stdout = None
        self.previous_stderr = None

    # ------------------------------------------------------------------
    # 子类必须实现的抽象接口
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def task_name(self) -> str:
        """任务显示名（如 "CAN 生成"）。无参数。返回: 字符串。"""

    @abstractmethod
    def setup_logging(self) -> logging.Logger:
        """初始化该任务专用的 logger。无参数。返回: 配置好的 Logger 实例。"""

    @abstractmethod
    def extract_data(self) -> Any:
        """从 Excel / 配置文件读取源数据。无参数。返回: 任意结构的源数据，供 transform 使用。"""

    @abstractmethod
    def transform(self, data: Any) -> Any:
        """将源数据转换为目标格式。参数: data — extract_data 的返回值。返回: 供 load 写入的内容。"""

    @abstractmethod
    def load(self, content: Any) -> None:
        """将转换后的内容写入输出文件。参数: content — transform 的返回值。无返回值。"""

    # ------------------------------------------------------------------
    # TeeToLogger 前缀配置（子类可按需覆盖）
    # ------------------------------------------------------------------

    @property
    def tee_error_prefixes(self) -> tuple[str, ...]:
        """TeeToLogger 识别为错误级别的输出前缀。参数：无。返回：前缀元组。"""
        return ("错误", "[错误]", "[error]", "[ERROR]")

    @property
    def tee_warning_prefixes(self) -> tuple[str, ...]:
        """TeeToLogger 识别为警告级别的输出前缀。参数：无。返回：前缀元组。"""
        return ("警告", "[警告]", "[warn]", "[WARNING]")

    @property
    def tee_skip_prefixes(self) -> tuple[str, ...]:
        """TeeToLogger 需要跳过（不记录到日志）的输出前缀。参数：无。返回：前缀元组。"""
        return ()

    @property
    def tee_start_trigger(self) -> str | None:
        """TeeToLogger 开始记录的触发字符串，为 None 则立即开始记录。参数：无。返回：触发字符串或 None。"""
        return None

    # ------------------------------------------------------------------
    # 可选覆盖的钩子方法
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """子类可覆盖，做额外清理；默认调用 clear_run_logger。参数：无。返回：无返回值。"""
        clear_run_logger(self.logger)

    # ------------------------------------------------------------------
    # 模板方法：标准执行流程
    # ------------------------------------------------------------------

    def run(self) -> None:
        """标准执行流程（模板方法）：加载配置、初始化日志、重定向输出、提取数据、转换、写入、清理并恢复输出。参数：无。返回：无返回值。"""
        self.initialize_configuration()
        self.logger = self.setup_logging()
        self.redirect_stdout_streams()

        try:
            print(f"{'=' * 60}")
            print(f"开始执行任务: {self.task_name}")
            print(f"{'=' * 60}")

            data = self.extract_data()
            content = self.transform(data)
            self.load(content)

            print(f"任务完成: {self.task_name}")
            if self.logger:
                self.logger.log(PROGRESS_LEVEL, "任务完成: %s", self.task_name)
        except Exception as error:
            error_msg = str(error)
            print(f"错误: {error_msg}")
            if self.logger:
                self.logger.exception("任务异常: %s", self.task_name)
            raise
        finally:
            self.cleanup()
            self.restore_stdout_streams()

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def initialize_configuration(self) -> None:
        """加载主配置文件和固定配置文件到 self.config / self.fixed_config。参数：无。返回：无返回值。"""
        if self.config_path and os.path.exists(self.config_path):
            self.config = read_config_if_exists(self.config_path)
        self.fixed_config = read_fixed_config(self.base_dir)

    def redirect_stdout_streams(self) -> None:
        """将 stdout/stderr 重定向到 TeeToLogger，同时保留原始输出。参数：无。返回：无返回值。"""
        if self.logger is None:
            return
        self.previous_stdout = sys.stdout
        self.previous_stderr = sys.stderr
        if sys.__stdout__ is not None and sys.__stderr__ is not None:
            sys.stdout = TeeToLogger(
                self.logger,
                logging.INFO,
                sys.__stdout__,
                error_prefixes=self.tee_error_prefixes,
                warning_prefixes=self.tee_warning_prefixes,
                skip_prefixes=self.tee_skip_prefixes,
                start_trigger=self.tee_start_trigger,
            )
            sys.stderr = TeeToLogger(
                self.logger,
                logging.ERROR,
                sys.__stderr__,
                error_prefixes=self.tee_error_prefixes,
                warning_prefixes=self.tee_warning_prefixes,
            )

    def restore_stdout_streams(self) -> None:
        """恢复 stdout/stderr 到重定向前的原始状态。参数：无。返回：无返回值。"""
        if self.previous_stdout is not None:
            sys.stdout = self.previous_stdout
        if self.previous_stderr is not None:
            sys.stderr = self.previous_stderr
        self.previous_stdout = None
        self.previous_stderr = None

    def get_config_value(self, section: str, key: str, fallback: str = "") -> str:
        """获取配置值：优先从固定配置文件读取，其次从主配置文件读取。参数：section — 节名；key — 配置项键名；fallback — 未找到时的默认值。返回：对应的配置值字符串。"""
        fixed_val = self.fixed_config.get(key)
        if fixed_val is not None:
            return fixed_val
        if self.config is None:
            return fallback
        try:
            return self.config.get(section, key, fallback=fallback)
        except Exception:
            return fallback
