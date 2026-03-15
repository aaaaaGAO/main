#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAPL CAN 文本渲染器。"""

from __future__ import annotations

import os
import re
from typing import Iterable, Sequence

from .models import CANTestCase


class CANFileRenderer:
    """负责把 `CANTestCase` 集合渲染成 `.can` 文本。"""

    def __init__(self, include_files: Sequence[str] | None = None) -> None:
        self.include_files = list(include_files or [])

    def render_single_file(self, case: CANTestCase) -> str:
        return self.render_sheet_file([case])

    def render_sheet_file(self, cases: Iterable[CANTestCase]) -> str:
        lines: list[str] = [
            "/*@!Encoding: 936*/",
            "",
            "includes",
            "{",
            "}",
            "",
            "variables",
            "{",
            "}",
            "",
        ]
        for case in cases:
            lines.extend(self._render_testcase(case))
            lines.append("")
        return "\r\n".join(lines).rstrip() + "\r\n"

    def render_master(self, cases: Iterable[CANTestCase]) -> str:
        include_files = list(self.include_files)
        for case in cases:
            if case.target_path:
                include_path = os.path.basename(case.target_path).replace("\\", "/")
                if include_path not in include_files:
                    include_files.append(include_path)

        lines = ["includes", "{"]
        for include_file in include_files:
            lines.append(f'  #include "{include_file}"')
        lines.extend(["}", "", "variables", "{", "}", ""])
        return "\r\n".join(lines).rstrip() + "\r\n"

    def _render_testcase(self, case: CANTestCase) -> list[str]:
        # CAPL 标识符不能含连字符，需替换为下划线
        case_name = (case.case_id or "unnamed_case").replace("-", "_")

        lines = [f"testcase {case_name}()", "{"]

        if case.name:
            # 统一清洗名称中的换行符，避免 TestDescription 跨多行
            name_str = str(case.name)
            # 将 \r\n / \n / \r 等换行统一替换为空格
            name_str = re.sub(r"[\r\n]+", " ", name_str)
            # 转义：只对单独出现的 \ 转义为 \\，已有的 \\ 原样保留不变成 \\\\
            safe_name = self._escape_capl_string(name_str)
            lines.append(f'  TestDescription("{safe_name}");')
        if case.case_id_had_issues:
            warning = self._build_caseid_warning(case)
            safe_warning = self._escape_capl_string(str(warning))
            lines.append(f'  teststep("warning","{safe_warning}");')

        # 在渲染前，对步骤应用 SOA REQ / CHECK / CHECKREQ 成对前移与 _Prepare 规则（仅针对 CAN 步骤）
        steps = list(case.steps or [])
        if steps:
            steps = self._apply_soa_prepare_reorder(steps)
            lines.extend(step.rstrip() for step in steps)
        else:
            lines.append('  teststep("info","No translated steps");')

        lines.append("}")
        return lines

    @staticmethod
    def _apply_soa_prepare_reorder(lines: list[str]) -> list[str]:
        """
        SOA 重排 Version 5.0 (多请求无损支持版):
        1. 每一个原始行(REQ, CHECK, 普通步骤)都必须无条件保留在原位置。
        2. 将每个 CHECK 自动关联到它上方最近的一个 REQ。
        3. 遇到 REQ 时，在其上方额外插入它所关联的所有 CHECK 的 Prepare 副本。
        """
        if not lines:
            return lines

        def _is_soa_req(s: str) -> bool:
            """精准判断：代码区含 SOA 和 REQ，且不含 CHECK。"""
            if "//" not in s:
                return False
            parts = s.split("//", 1)
            code_part = parts[0].upper()
            comment_part = parts[1]
            return (
                ("测试步骤" in comment_part or "\u6d4b\u8bd5\u6b65\u9aa4" in comment_part)
                and "SOA" in code_part
                and "REQ" in code_part
                and "CHECK" not in code_part
            )

        def _is_soa_check(s: str) -> bool:
            """精准判断：代码区含 SOA 验证函数，排除副本。"""
            if "//" not in s or "_Prepare" in s or "_PREPARE" in s:
                return False
            parts = s.split("//", 1)
            code_part = parts[0].upper()
            comment_part = parts[1]
            return (
                ("预期结果" in comment_part or "\u9884\u671f\u7ed3\u679c" in comment_part)
                and "SOA" in code_part
                and ("CHECK" in code_part or "CHECKREQ" in code_part)
            )

        def _add_prepare_suffix(src: str) -> str:
            """生成带 _Prepare 后缀的副本。"""
            parts = src.split("//", 1)
            code_part = parts[0]
            comment_part = "//" + parts[1] if len(parts) > 1 else ""
            match = re.search(r"(\b\w+)(\s*\()", code_part)
            if match:
                func_name = match.group(1)
                new_code = (
                    code_part[: match.start(1)]
                    + func_name
                    + "_Prepare"
                    + code_part[match.end(1) :]
                )
                return new_code + comment_part
            return src

        n = len(lines)
        # 第一阶段：建立 REQ 索引 -> 它所属 CHECK 副本列表 的映射
        req_basket: dict[int, list[str]] = {}
        last_req_idx = -1

        for i in range(n):
            if _is_soa_req(lines[i]):
                last_req_idx = i
                req_basket[i] = []
            elif _is_soa_check(lines[i]):
                if last_req_idx != -1:
                    # 发现验证行，将其副本放入当前 REQ 的篮子里
                    req_basket[last_req_idx].append(_add_prepare_suffix(lines[i]))

        # 第二阶段：无损构造最终序列
        final_output: list[str] = []
        for i in range(n):
            # 如果当前行是 REQ，先喷出属于它的篮子（Prepare 副本）
            if i in req_basket:
                final_output.extend(req_basket[i])

            # 无论什么行，原始行 line[i] 必须 append，确保不丢失
            final_output.append(lines[i])

        return final_output

    @staticmethod
    def _escape_capl_string(s: str) -> str:
        """转义 CAPL 字符串：只对单独出现的 \\ 转义为 \\\\，已有的 \\\\ 原样保留不变成 \\\\\\\\；双引号转义为 \\\"。"""
        # 仅当反斜杠后没有紧跟另一个反斜杠时才替换为双反斜杠（单独 \ -> \\，\\ 保持为 \\）
        s = re.sub(r"\\(?!\\)", r"\\\\", s)
        s = s.replace('"', '\\"')
        return s

    @staticmethod
    def _build_caseid_warning(case: CANTestCase) -> str:
        """生成 warning 文案，避免嵌套双引号导致 CAPL 字符串解析错误。"""
        if case.case_id_issue_type == "duplicate" and case.duplicate_original_id:
            return f"原始用例id为{case.duplicate_original_id}"
        raw_id = case.raw_id or case.case_id
        return f"原始用例id为{raw_id}"


__all__ = ["CANFileRenderer"]
