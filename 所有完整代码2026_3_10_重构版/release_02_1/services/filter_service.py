#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
筛选项服务：解析 filter_options.txt，为前端提供等级/平台/车型等下拉选项。

从原 app.py 中的 parse_shaixuan_config 拆出，便于在新旧入口之间复用。
"""

from __future__ import annotations

import os
import unicodedata
from typing import Dict, List


def parse_shaixuan_config(base_dir: str) -> Dict[str, List[str]]:
    """解析 base_dir 下 filter_options.txt，返回等级/平台/车型/Target Version/UDS_ECU_qualifier 等筛选项字典。
    参数：base_dir — 工程根目录。
    返回：{"levels", "platforms", "models", "target_versions", "uds_ecu_qualifier"}；文件不存在时返回空列表。
    """
    filters = {"levels": [], "platforms": [], "models": [], "target_versions": [], "uds_ecu_qualifier": []}
    path = os.path.join(os.path.abspath(base_dir), "filter_options.txt")

    if not os.path.exists(path):
        print(f"提示: {path} 不存在，前端将显示空列表")
        return filters

    try:
        current_section = None
        # 使用 utf-8-sig 以兼容带 BOM 的 UTF-8 文件，errors='ignore' 防止非法字符崩溃
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            for raw_line in f:
                # 统一做 NFC 归一化，避免中文编码差异
                line = unicodedata.normalize("NFC", raw_line.strip())
                if not line:
                    continue

                # 区分标识符：以此来判断当前行属于哪个分类
                if "用例优先级" in line:
                    current_section = "levels"
                    continue
                elif "测试平台" in line:
                    current_section = "platforms"
                    continue
                elif "测试车型" in line:
                    current_section = "models"
                    continue
                elif "Target Version" in line:
                    current_section = "target_versions"
                    continue
                elif "UDS_ECU_qualifier" in line:
                    current_section = "uds_ecu_qualifier"
                    continue

                # 添加内容到对应分类
                if current_section:
                    filters[current_section].append(line)
    except Exception as e:
        print(f"读取filter_options.txt出现异常: {e}")

    return filters

