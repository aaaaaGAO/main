#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
步骤解析错误详情与 teststep/teststepfail 输出（CAN / CIN 共用）。

- StepErrorDetailBuilder : 根据 error_type + reason + 原始行 + 关键字表 生成用户可见错误文案
- format_step_error_lines : 将「原始行 + 错误详情」格式化为注释 + teststep + teststepfail 三行
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from core.keyword_error import describe_keyword_error


class StepErrorDetailBuilder:
    """
    根据解析阶段记录的 error_type / reason 与原始步骤行、关键字表，
    生成用于注释和 teststepfail 的详细错误文案（与 CAN/CIN 展示一致）。
    """

    @staticmethod
    def parse_io_name_value_from_line(original_line: str) -> tuple[str, str]:
        """从步骤行中解析首个 J_ 开头的 token 作为 name_tok，后续作为 value_tok。参数: original_line — 原始步骤行。返回: (name_tok, value_tok)。"""
        tokens = original_line.split()
        name_tok = ""
        value_tok = ""
        for token_index, token_text in enumerate(tokens):
            if token_text.upper().startswith("J_"):
                name_tok = token_text
                if token_index + 1 < len(tokens):
                    value_tok = " ".join(tokens[token_index + 1 :]).strip()
                break
        return name_tok, value_tok

    @staticmethod
    def parse_name_value_from_reason(reason: str) -> tuple[str, str]:
        """从 reason 中解析 Name=... 与 Value=...。参数: reason — 错误原因字符串。返回: (name_val, value_val)。"""
        name_val = ""
        value_val = ""
        if "Name=" in reason:
            tmp = reason.split("Name=", 1)[1]
            name_val = (tmp.split(",", 1)[0].strip() if "," in tmp else tmp.strip())
        if "Value=" in reason:
            tmp = reason.split("Value=", 1)[1]
            value_val = (tmp.split(",", 1)[0].strip() if "," in tmp else tmp.strip())
        return name_val, value_val

    @classmethod
    def build_detail(
        cls,
        error_type: str,
        reason: str,
        original_line: str,
        keyword_specs: Dict[str, Any],
    ) -> str:
        """根据 error_type、reason、原始行与关键字表生成错误详情文案。
        参数: error_type — 错误类型（iomapping/config_enum/keyword/syntax 等）；reason — 原因字符串；original_line — 原始步骤行；keyword_specs — 关键字规格字典。
        返回: 用户可见错误详情字符串。
        """
        reason = reason or ""
        original_line = (original_line or "").strip()

        if error_type == "iomapping":
            name_tok, value_tok = cls.parse_io_name_value_from_line(original_line)
            if reason.startswith("Name 未找到"):
                return f"IO_mapping 表中Name 未找到: {name_tok or reason.split(':', 1)[-1].strip()}"
            if "Name 找不到" in reason:
                return f"IO_mapping 表中 Name 找不到: {name_tok or (reason.split(':', 1)[-1].strip() if ':' in reason else reason)}"
            if reason.startswith("Path 为空"):
                return f"IO_mapping 表中{reason}"
            if reason.startswith("Values 为空"):
                name_val, value_val = cls.parse_name_value_from_reason(reason)
                name_show = name_tok or name_val
                value_show = value_val or value_tok
                if name_show and value_show:
                    return f"IO_mapping 表中 name {name_show} 的Values 为空，现在跟的是 {value_show}"
                if name_show:
                    return f"IO_mapping 表中 name {name_show} 的Values 为空"
                return f"IO_mapping 表中{reason}"
            if "未匹配" in reason or "Values 未匹配" in reason or reason.startswith("Values 未匹配"):
                if name_tok and value_tok:
                    return f"IO_mapping 表中 name {name_tok} 的Values 未匹配: {value_tok}"
                if value_tok:
                    return f"IO_mapping 表中Values 未匹配: {value_tok}"
                return f"IO_mapping 表中{reason}"
            return f"IO_mapping 表中{reason}"

        if error_type == "config_enum":
            line_lower = original_line.lower()
            table_prefix = "DID Configuration 表中" if ("set_cf" in line_lower or "set_config" in line_lower) else "Configuration 表中"
            name_val, value_val = cls.parse_name_value_from_reason(reason)
            if reason.startswith("Name 未找到"):
                return f"{table_prefix}{reason}"
            if reason.startswith("Values 为空"):
                if name_val and value_val:
                    return f"{table_prefix} name {name_val} 的Values 为空，现在跟的是 {value_val}"
                if name_val:
                    return f"{table_prefix} name {name_val} 的Values 为空"
                return f"{table_prefix}{reason}"
            if "Values 未匹配" in reason:
                if name_val and value_val:
                    return f"{table_prefix} name {name_val} 的Values 未匹配: {value_val}"
                if name_val:
                    return f"{table_prefix} name {name_val} 的Values 未匹配"
                if value_val:
                    return f"{table_prefix}Values 未匹配: {value_val}"
                return f"{table_prefix}{reason}"
            return f"{table_prefix}{reason}"

        if error_type == "keyword":
            tokens = original_line.split()
            first_tok = (tokens[1] if (len(tokens) > 1 and tokens[0].lower() == "step") else (tokens[0] if tokens else "")) or ""
            first_tok = first_tok.strip()
            is_format_error = False
            if first_tok:
                if first_tok.lower().startswith("step") and re.match(r"^step\d+:?$", first_tok.lower()):
                    is_format_error = True
                elif first_tok.endswith(":"):
                    is_format_error = True
                elif len(first_tok) <= 4 and first_tok.lower() in {"tep", "set", "get", "chk", "ch", "ck"}:
                    is_format_error = True
            if is_format_error:
                return "写入错误"
            return describe_keyword_error(original_line, keyword_specs)

        if error_type == "syntax":
            return "写入错误"

        return "写入错误"


def format_step_error_lines(
    original_line: str,
    error_detail: str,
    role_prefix: str = "测试步骤",
) -> List[str]:
    """将「原始行 + 错误详情」格式化为 CAPL 注释 + teststep + teststepfail 三行（CAN/CIN 共用）。
    参数: original_line — 原始步骤行；error_detail — 错误详情文案；role_prefix — 注释中角色前缀（如「测试步骤」「预期结果」）。
    返回: 三行字符串列表 [注释行, teststep 行, teststepfail 行]。
    """
    original_line = (original_line or "").strip()
    error_detail = (error_detail or "").strip()
    if not error_detail:
        return [
            f"  // {original_line} // {role_prefix}关键字匹配失败",
            f'  teststep("step","{original_line.replace(chr(34), chr(92)+chr(34))}");',
            f'  teststepfail("fail","");',
        ]
    escaped_line = original_line.replace('"', '\\"')
    escaped_detail = error_detail.replace('"', '\\"')
    return [
        f"  // {original_line} // {role_prefix}{error_detail}",
        f'  teststep("step","{escaped_line}");',
        f'  teststepfail("fail","{escaped_detail}");',
    ]
