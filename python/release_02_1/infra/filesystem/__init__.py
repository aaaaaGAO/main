#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infra.filesystem：路径与文件系统相关能力（底层）

导出符号与参数说明：
- get_base_dir(reference_file=None) -> str
  运行基准目录。打包时为 exe 所在目录；开发时为 reference_file 所在目录，None 则用本模块 __file__。
- get_project_root(reference_file=None) -> str
  工程根目录（含 Configuration.txt 的目录）。打包时为 exe 所在目录；开发时从 reference_file 向上查找。
- find_config_path(base_dir: str, filename='Configuration.txt') -> str | None
  在 base_dir 及 base_dir/../release 下查找配置文件，返回找到的绝对路径，未找到返回 None。
"""

from infra.filesystem.pathing import find_config_path, get_base_dir, get_project_root

__all__ = [
    "get_base_dir",
    "find_config_path",
    "get_project_root",
]

