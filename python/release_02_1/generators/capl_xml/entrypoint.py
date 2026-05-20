#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML 生成入口模块。

从配置的输入路径读用例 Excel，生成 XML 测试模块文件并写入配置的输出目录，
供 TaskService 与命令行调用。具体实现委托同包下 service.XMLGeneratorService。
"""

from __future__ import annotations

import os
import sys
from typing import Any

from services.config_constants import DEFAULT_DOMAIN_LR_REAR

# 无控制台（如 --noconsole 打包）时 stdout/stderr 可能为 None，子模块 print 会报错，此处做防护
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from .service import XMLGeneratorService


class XMLEntrypointWorkflowUtility:
    """XML 入口编排统一工具类。"""

    @classmethod
    def run_generation(
        cls,
        config_path: str | None = None,
        base_dir: str | None = None,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
        workbook_cache: dict[str, Any] | None = None,
    ) -> None:
        """XML 生成统一入口，供 TaskService 与命令行调用。"""
        service = XMLGeneratorService()
        service.run_pipeline(
            config_path=config_path,
            base_dir=base_dir,
            domain=domain,
            workbook_cache=workbook_cache,
        )


def run_generation(
    config_path: str | None = None,
    base_dir: str | None = None,
    domain: str = DEFAULT_DOMAIN_LR_REAR,
    workbook_cache: dict[str, Any] | None = None,
) -> None:
    """兼容入口：转发到 XMLEntrypointWorkflowUtility.run_generation。"""
    XMLEntrypointWorkflowUtility.run_generation(
        config_path=config_path,
        base_dir=base_dir,
        domain=domain,
        workbook_cache=workbook_cache,
    )


if __name__ == "__main__":
    XMLEntrypointWorkflowUtility.run_generation()
