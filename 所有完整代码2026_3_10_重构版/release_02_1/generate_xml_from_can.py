#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML 生成入口脚本

本脚本为执行入口，将 XML 生成委托给 generators.capl_xml.service 执行。
执行顺序：① 读配置 → ② 初始化日志 → ③ 查找 Excel → ④ 解析并分组 → ⑤ 写 XML → ⑥ 汇总。
实现已迁入 generators/capl_xml/（runtime.py + runtime_io.py），根脚本仅保留入口与 --noconsole 防护。
"""

import os
import sys

# 在无控制台（如 --noconsole 打包）时 stdout/stderr 可能为 None，子模块 print 会导致 Bad file descriptor 或阻塞
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from generators.capl_xml.service import XMLGeneratorService


def main(
    config_path: str | None = None,
    base_dir: str | None = None,
    domain: str = "LR_REAR",
) -> None:
    """XML 生成统一入口，依次执行读配置、初始化日志、查找 Excel、解析分组、写 XML、汇总。

    功能：创建 XMLGeneratorService 并执行 run_legacy_pipeline，从配置的输入路径读用例 Excel，生成 XML 文件并写入配置的输出目录。

    参数：
        config_path — 配置文件路径；None 时在 base_dir 下查找 Configuration.txt。
        base_dir — 工程根目录；None 时由 Service 内部解析。
        domain — 业务域，用于读取对应域的输入输出路径等配置。

    返回：无返回值。
    """
    service = XMLGeneratorService()
    service.run_legacy_pipeline(
        config_path=config_path,
        base_dir=base_dir,
        domain=domain,
    )


if __name__ == "__main__":
    main()
