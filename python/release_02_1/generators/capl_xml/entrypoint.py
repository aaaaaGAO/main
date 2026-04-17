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

from services.config_constants import DEFAULT_DOMAIN_LR_REAR

# 无控制台（如 --noconsole 打包）时 stdout/stderr 可能为 None，子模块 print 会报错，此处做防护
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from .service import XMLGeneratorService


def main(
    config_path: str | None = None,
    base_dir: str | None = None,
    domain: str = DEFAULT_DOMAIN_LR_REAR,
) -> None:
    """XML 生成统一入口，供 TaskService 与命令行调用。

    功能：创建 XMLGeneratorService 并执行 run_legacy_pipeline，依次完成读配置、初始化日志、
    查找 Excel、解析分组、写 XML、汇总。

    形参：
        config_path：配置文件路径；None 时按主配置默认解析规则查找 `Configuration.ini`。
        base_dir：工程根目录；None 时由 Service 内部解析。
        domain：业务域，用于读取对应域的输入输出路径等配置。

    返回：无。
    """
    service = XMLGeneratorService()
    service.run_legacy_pipeline(
        config_path=config_path,
        base_dir=base_dir,
        domain=domain,
    )


def run_generation(
    config_path: str | None = None,
    base_dir: str | None = None,
    domain: str = DEFAULT_DOMAIN_LR_REAR,
) -> None:
    """语义化入口别名：等价于 main。"""
    main(config_path=config_path, base_dir=base_dir, domain=domain)


if __name__ == "__main__":
    main()
