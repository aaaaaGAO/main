#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一错误模块判断，供 CAN / CIN / XML 等生成器共用。

规则：
- io_mapping 解析失败     -> io_mapping
- Configuration 解析失败  -> Configuration
- 关键字匹配失败          -> 关键字映射表
- clib 表中没有           -> clib
- 其他                    -> 写入错误
"""

from __future__ import annotations


class ErrorModuleResolver:
    """根据错误原因返回错误模块名称，用于日志格式：ERROR 错误模块【xxx】"""

    @staticmethod
    def resolve(fail_text: str) -> str:
        """根据错误原因返回错误模块名（用于日志「错误模块【xxx】」）。
        参数: fail_text — 失败原因/错误文案。
        返回: 模块名（io_mapping / Configuration / 关键字映射表 / clib / 写入错误）。
        """
        if not fail_text:
            return "写入错误"
        fail_lower = fail_text.lower()
        if "io_mapping" in fail_lower or "io_mapping 解析失败" in fail_text:
            return "io_mapping"
        if (
            "configuration 解析失败" in fail_lower
            or "配置枚举解析失败" in fail_text
            or "config_enum" in fail_lower
        ):
            return "Configuration"
        if "关键字不存在" in fail_text or "关键字匹配失败" in fail_text:
            return "关键字映射表"
        # 兼容 CAN 的「clib表中没有」与 CIN 的「Clib表中未找到...关键字」
        if "clib表中没有" in fail_text or (
            "clib表中未找到" in fail_text.lower() and "关键字" in fail_text
        ):
            return "clib"
        return "写入错误"
