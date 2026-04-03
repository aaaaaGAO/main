#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成器日志模块（供 CAN/CIN/XML/DIDInfo/DIDConfig/UART 复用）

封装「按任务建 logger、写文件 + 控制台、进度/排除过滤器、运行结束清理」，
各生成器通过 GeneratorLogger 统一初始化日志，避免各脚本内重复 _setup_logging 逻辑。
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence, Tuple

from utils.logger import (
    PROGRESS_LEVEL,
    ProgressOnlyFilter,
    ExcludeProgressFilter,
    ProgressFormatter,
    get_log_level_from_config,
)

from core.log_run_context import ensure_run_log_dirs
from core.run_context import clear_run_logger


# 单文件：(log_subdir, log_basename)；多文件：列表
LogSpec = Tuple[str, str]  # (subdir, basename)


@dataclass(slots=True)
class LogSpecConfig:
    """单个日志文件的配置。"""

    subdir: str
    basename: str
    file_filters: Sequence[logging.Filter] = field(default_factory=tuple)
    progress_filters: Sequence[logging.Filter] = field(default_factory=tuple)


class GeneratorLogger:
    """
    生成器统一日志类。

    功能：
      - 根据 base_dir 创建 run_dirs（解析表格日志/生成文件日志），按 log_specs 写一个或多个日志文件。
      - 每个日志文件：主 handler（按用户级别，排除 PROGRESS）+ 进度 handler（仅 PROGRESS）。
      - 可选控制台 StreamHandler；可选自定义 formatter、file_filters。
      - setup() 返回 logger；clear() 关闭并清空 handlers，便于下次运行写新目录。

    使用方式（单文件）：
      log_mgr = GeneratorLogger(base_dir, "generate_did_config.log")
      logger = log_mgr.setup()
      ...
      log_mgr.clear()

    使用方式（双文件，如 DIDConfig）：
      log_mgr = GeneratorLogger(
          base_dir,
          None,
          log_specs=[("parse", "DIDConfiguration_Matrix.log"), ("gen", "generate_did_config.log")],
      )
      logger = log_mgr.setup()
    """

    def __init__(
        self,
        base_dir: str,
        log_basename: Optional[str] = None,
        *,
        log_subdir: str = "gen",
        logger_name: Optional[str] = None,
        log_specs: Optional[Sequence[LogSpec | LogSpecConfig]] = None,
        formatter_factory: Optional[Callable[[str], logging.Formatter]] = None,
        file_filters: Optional[Sequence[logging.Filter]] = None,
        console: bool = True,
    ):
        """
        形参：
          base_dir — 工程根目录，用于 ensure_run_log_dirs 与 get_log_level_from_config。
          log_basename — 单文件时的日志文件名（如 generate_did_config.log）；与 log_specs 二选一。
          log_subdir — 单文件时使用的子目录："gen" 即生成文件日志，"parse" 即解析表格日志。
          logger_name — logging.getLogger(name)；None 时用 log_basename 或首项 log_specs 的 basename 去掉 .log。
          log_specs — 多文件时 [(subdir, basename), ...]，如 [("parse", "A.log"), ("gen", "B.log")]。
          formatter_factory — (fmt_str) -> Formatter；None 则用 ProgressFormatter。
          file_filters — 附加到每个文件主 handler 的过滤器（如 ExcludeSubstringsFilter）。
          console — 是否添加 StreamHandler。
        """
        self.base_dir = os.path.abspath(base_dir)
        self._log_basename = log_basename
        self._log_subdir = log_subdir
        self._logger_name = logger_name
        self._log_specs = log_specs or ([(log_subdir, log_basename)] if log_basename else [])
        self._formatter_factory = formatter_factory or (lambda s: ProgressFormatter(s))
        self._file_filters = list(file_filters) if file_filters else []
        self._console = console
        self._logger: Optional[logging.Logger] = None
        self._run_dirs = None
        self._primary_log_path: Optional[str] = None

    def setup(self) -> logging.Logger:
        """创建/返回 logger，添加 RotatingFileHandler（主+进度）及可选控制台。"""
        if self._logger is not None and self._logger.handlers:
            return self._logger

        user_level = get_log_level_from_config(self.base_dir, section=None)
        self._run_dirs = ensure_run_log_dirs(self.base_dir)
        formatter = self._formatter_factory("%(asctime)s %(levelname)s %(message)s")

        logger_name = self._logger_name
        if logger_name is None and self._log_specs:
            logger_name = (self._log_specs[0][1] or "").replace(".log", "").strip() or "generator"
        self._logger = logging.getLogger(logger_name or "generator")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        subdir_to_path = {
            "gen": self._run_dirs.gen_dir,
            "parse": self._run_dirs.parse_dir,
        }
        for spec_index, raw_spec in enumerate(self._log_specs):
            spec = self.normalize_log_spec(raw_spec)
            subdir, basename = spec.subdir, spec.basename
            log_dir = subdir_to_path.get(subdir, self._run_dirs.gen_dir)
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, basename)
            if spec_index == 0:
                self._primary_log_path = log_path

            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=5 * 1024 * 1024,
                backupCount=20,
                encoding="utf-8",
            )
            file_handler.addFilter(ExcludeProgressFilter())
            for file_filter in self._file_filters:
                file_handler.addFilter(file_filter)
            for file_filter in spec.file_filters:
                file_handler.addFilter(file_filter)
            file_handler.setLevel(user_level)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

            progress_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=5 * 1024 * 1024,
                backupCount=20,
                encoding="utf-8",
            )
            progress_handler.addFilter(ProgressOnlyFilter())
            for progress_filter in spec.progress_filters:
                progress_handler.addFilter(progress_filter)
            progress_handler.setLevel(PROGRESS_LEVEL)
            progress_handler.setFormatter(formatter)
            self._logger.addHandler(progress_handler)

        if self._console:
            console_handler = logging.StreamHandler()
            console_handler.addFilter(ExcludeProgressFilter())
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        return self._logger

    @staticmethod
    def normalize_log_spec(spec: LogSpec | LogSpecConfig) -> LogSpecConfig:
        """将 (subdir, basename) 或 LogSpecConfig 统一为 LogSpecConfig。参数: spec — 日志规格。返回: LogSpecConfig。"""
        if isinstance(spec, LogSpecConfig):
            return spec
        subdir, basename = spec
        return LogSpecConfig(subdir=subdir, basename=basename)

    @property
    def logger(self) -> Optional[logging.Logger]:
        """setup() 后返回的 logger。"""
        return self._logger

    @property
    def primary_log_path(self) -> Optional[str]:
        """setup() 后第一个日志文件的完整路径（供 CAN 等脚本写 per-sheet 小日志时复用）。"""
        return self._primary_log_path

    @property
    def run_dirs(self):
        """setup() 后本次运行的日志目录（RunLogDirs）。"""
        return self._run_dirs

    def clear(self) -> None:
        """关闭并清空 logger 的 handlers，便于下次运行重新 setup 并写入新目录。"""
        clear_run_logger(self._logger)
        self._logger = None
