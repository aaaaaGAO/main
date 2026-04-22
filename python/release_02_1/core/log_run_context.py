#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每次“生成任务”创建独立日志目录：

<base_dir>/log/log_YYYYMMDD_HHMMSS/
  ├─ 生成文件日志/
  └─ 解析表格日志/

并通过环境变量在同一进程内共享，确保 Web 一键生成（CAN/XML/CIN/解析表）落在同一批日志目录中。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from core.caseid_log_dedup import reset_dedup_filter


ENV_RUN_LOG_ROOT = "RUN_LOG_ROOT"
ENV_RUN_LOG_GEN_DIR = "RUN_LOG_GEN_DIR"
ENV_RUN_LOG_PARSE_DIR = "RUN_LOG_PARSE_DIR"
ENV_RUN_LOG_DOMAIN = "RUN_LOG_DOMAIN"


def set_run_domain(domain: str | None) -> None:
    """设置当前运行域（LR_REAR/CENTRAL/DTC），供解析表格日志等按域读取 log_level_min。"""
    if domain:
        os.environ[ENV_RUN_LOG_DOMAIN] = str(domain).strip()
    else:
        os.environ.pop(ENV_RUN_LOG_DOMAIN, None)


def get_run_domain() -> str | None:
    """获取当前运行域；未设置时返回 None。"""
    return (os.environ.get(ENV_RUN_LOG_DOMAIN) or "").strip() or None


@dataclass(frozen=True)
class RunLogDirs:
    root_dir: str     # log/log_YYYYMMDD_HHMMSS
    gen_dir: str      # .../生成文件日志
    parse_dir: str    # .../解析表格日志


def reset_run_context() -> None:
    """
    重置当前进程内的运行日志上下文。
    - 清除用于缓存本次“生成任务”日志目录的环境变量，
      使得下一次调用 ensure_run_log_dirs 时一定会基于最新时间戳创建新目录。
    - 清空 caseid_clean_dup 的去重集合，确保二次点击时能写入新日志目录。
    - 典型用法：在每次任务入口（如 generators.capl_can.entrypoint.run_generation）开始时调用，
      确保每次点击“生成”都会落在全新的 log_YYYYMMDD_HHMMSS 目录中。
    """
    for item_key in (ENV_RUN_LOG_ROOT, ENV_RUN_LOG_GEN_DIR, ENV_RUN_LOG_PARSE_DIR, ENV_RUN_LOG_DOMAIN):
        os.environ.pop(item_key, None)
    try:
        reset_dedup_filter()
    except Exception:
        pass


def ensure_run_log_dirs(base_dir: str, *, force_new: bool = False) -> RunLogDirs:
    """获取或创建本次运行的日志目录（log_时间戳 及 生成文件日志、解析表格日志 子目录）。
    参数:
        base_dir: 项目根目录，日志将创建在 base_dir/log 下。
        force_new: 为 True 时忽略环境变量缓存，每次创建新时间戳目录。
    返回: RunLogDirs（root_dir、gen_dir、parse_dir）。
    """
    base_dir = os.path.abspath(base_dir)

    root_env = os.environ.get(ENV_RUN_LOG_ROOT, "").strip()
    gen_env = os.environ.get(ENV_RUN_LOG_GEN_DIR, "").strip()
    parse_env = os.environ.get(ENV_RUN_LOG_PARSE_DIR, "").strip()
    # 默认：同一进程内复用已有目录；但当 force_new=True 时，每次调用都新建一批目录
    if (not force_new
            and root_env
            and gen_env
            and parse_env
            and os.path.isdir(root_env)
            and os.path.isdir(gen_env)
            and os.path.isdir(parse_env)):
        return RunLogDirs(root_env, gen_env, parse_env)

    log_root = os.path.join(base_dir, "log")
    os.makedirs(log_root, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    root_dir = os.path.join(log_root, f"log_{ts}")
    gen_dir = os.path.join(root_dir, "生成文件日志")
    parse_dir = os.path.join(root_dir, "解析表格日志")

    os.makedirs(gen_dir, exist_ok=True)
    os.makedirs(parse_dir, exist_ok=True)

    os.environ[ENV_RUN_LOG_ROOT] = root_dir
    os.environ[ENV_RUN_LOG_GEN_DIR] = gen_dir
    os.environ[ENV_RUN_LOG_PARSE_DIR] = parse_dir

    return RunLogDirs(root_dir, gen_dir, parse_dir)
