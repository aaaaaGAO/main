#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAPL CAN 文本渲染器。"""

from __future__ import annotations

import os
import re
from typing import Iterable, Sequence

from .models import CANTestCase


def split_capl_comment_parts(line: str) -> tuple[str, str]:
    if "//" not in line:
        return line, ""
    code, comment = line.split("//", 1)
    return code, comment


def _is_test_step_line(line: str) -> bool:
    _, comment = split_capl_comment_parts(line)
    return "测试步骤" in comment or "\u6d4b\u8bd5\u6b65\u9aa4" in comment


def _is_expect_line(line: str) -> bool:
    _, comment = split_capl_comment_parts(line)
    return "预期结果" in comment or "\u9884\u671f\u7ed3\u679c" in comment


def _is_soa_expect_check_line(line: str) -> bool:
    """判断是否为 SOA CHECK / CHECKREQ 的预期结果行（排除已带 _Prepare）。"""
    if "_Prepare" in line or "_PREPARE" in line:
        return False
    code_part, _ = split_capl_comment_parts(line)
    code_upper = code_part.upper()
    if "SOA" not in code_upper:
        return False
    return "SOA_CHECK(" in code_upper or "CHECKREQ(" in code_upper


def _is_soa_expect_check_only_line(line: str) -> bool:
    """仅匹配 SOA_CHECK（不包含 CHECKREQ）的预期结果行。"""
    if "_Prepare" in line or "_PREPARE" in line:
        return False
    code_part, _ = split_capl_comment_parts(line)
    code_upper = code_part.upper()
    if "SOA" not in code_upper:
        return False
    return "SOA_CHECK(" in code_upper and "CHECKREQ(" not in code_upper


def _has_traceback_token(line: str) -> bool:
    """是否包含 traceback（不区分大小写，允许 traceback7 这类写法）。"""
    code_part, comment_part = split_capl_comment_parts(line)
    text = f"{code_part} {comment_part}"
    return bool(re.search(r"\btraceback\d*\b", text, re.IGNORECASE))


def _is_wait_or_sleep_test_step(line: str) -> bool:
    """仅看注释里的测试步骤语义，不看生成后的 CAPL 函数名。"""
    _, comment = split_capl_comment_parts(line)
    if not comment.strip():
        return False
    return bool(
        re.search(
            r"\b(?:wait|TC_4G_Time_Delay_Second|TC_Sleep)\b",
            comment,
            re.IGNORECASE,
        )
    )


def _is_soa_req_test_step(line: str) -> bool:
    """是否为 SOA REQ 测试步骤行（仅看代码部分）。"""
    if not _is_test_step_line(line):
        return False
    code_part, _ = split_capl_comment_parts(line)
    code_upper = code_part.upper()
    return "SOA_REQ(" in code_upper or "SOA REQ" in code_upper


def _add_prepare_suffix_to_line(line: str) -> str:
    """生成带 _Prepare 后缀的副本。"""
    parts = line.split("//", 1)
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
    return line


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
        按“节点”重排 SOA CHECK / CHECKREQ：

        - 不再基于 SOA REQ / CHECK 的行内匹配关系。
        - 一个“节点”从某一行“测试步骤”开始，一直到下一行“测试步骤”之前（或文件结束）。
        - 若该节点内的“预期结果”中出现 SOA CHECK / SOA CHECKREQ：
          * 预期结果行本身不改动；
          * 为每个 SOA CHECK / CHECKREQ 生成一个带 _Prepare 后缀的副本；
          * 若节点首行「测试步骤」行在 // 注释语义中未出现 wait、TC_4G_Time_Delay_Second 或 TC_Sleep（整词，不区分大小写），则将所有 _Prepare 行插入到该测试步骤“上方”；
          * 若 // 注释中出现上述三者之一，则将所有 _Prepare 行插入到该测试步骤“下方”（不依生成后的 CAPL 函数名，如 g_HIL_Gen_Swc_Wait 等）。

        这样既保留了原始步骤顺序，又按节点粒度在测试步骤附近集中插入 Prepare。
        """
        if not lines:
            return lines

        n = len(lines)
        # 记录每个“节点首行测试步骤”前/后需要插入的 Prepare 行
        prepare_before: dict[int, list[str]] = {}
        prepare_after: dict[int, list[str]] = {}
        # 先记录所有 Prepare 的来源顺序与目标位置，最后统一按来源顺序落位
        scheduled_prepares: list[tuple[int, int, str, str]] = []

        i = 0
        while i < n:
            if not _is_test_step_line(lines[i]):
                i += 1
                continue

            node_start = i
            j = i + 1
            # 节点范围：[node_start, j) —— 直到下一个测试步骤或结尾
            while j < n and not _is_test_step_line(lines[j]):
                j += 1

            # 在该节点范围内查找 SOA CHECK / CHECKREQ 预期结果行
            node_is_wait_or_sleep = _is_wait_or_sleep_test_step(lines[node_start])
            for k in range(node_start, j):
                if _is_expect_line(lines[k]) and _is_soa_expect_check_line(lines[k]):
                    prepare_line = _add_prepare_suffix_to_line(lines[k])
                    # 新增规则：
                    # SOA_CHECK（不含 CHECKREQ）且该行出现 traceback* 时，
                    # 优先前插到最近的前置 SOA REQ 测试步骤前；
                    # 若前面没有 SOA REQ，则前插到最近的前置 wait/sleep 测试步骤前。
                    if _is_soa_expect_check_only_line(lines[k]) and _has_traceback_token(lines[k]):
                        nearest_soa_req_idx = None
                        for p in range(k - 1, -1, -1):
                            if _is_soa_req_test_step(lines[p]):
                                nearest_soa_req_idx = p
                                break

                        if nearest_soa_req_idx is not None:
                            scheduled_prepares.append((k, nearest_soa_req_idx, "before", prepare_line))
                            continue

                        nearest_wait_idx = None
                        for p in range(k - 1, -1, -1):
                            if _is_test_step_line(lines[p]) and _is_wait_or_sleep_test_step(lines[p]):
                                nearest_wait_idx = p
                                break

                        if nearest_wait_idx is not None:
                            scheduled_prepares.append((k, nearest_wait_idx, "before", prepare_line))
                            continue

                    default_placement = "after" if node_is_wait_or_sleep else "before"
                    scheduled_prepares.append((k, node_start, default_placement, prepare_line))

            i = j

        # 按预期结果在原文中的出现顺序写入，避免 traceback 分支抢到最前
        scheduled_prepares.sort(key=lambda item: item[0])
        for _, target_idx, placement, prepare_line in scheduled_prepares:
            if placement == "after":
                prepare_after.setdefault(target_idx, []).append(prepare_line)
            else:
                prepare_before.setdefault(target_idx, []).append(prepare_line)

        # 第二阶段：根据 before/after 映射无损生成最终行
        final_output: list[str] = []
        for idx, line in enumerate(lines):
            if idx in prepare_before:
                final_output.extend(prepare_before[idx])
            final_output.append(line)
            if idx in prepare_after:
                final_output.extend(prepare_after[idx])

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
