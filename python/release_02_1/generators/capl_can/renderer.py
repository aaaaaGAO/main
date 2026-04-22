#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAPL CAN 文本渲染器。"""

from __future__ import annotations

import os
import re
from typing import Iterable, Sequence

from .models import CANTestCase


class CANRenderUtility:
    """CAPL CAN 文本渲染辅助函数统一工具类入口。"""

    @staticmethod
    def split_capl_comment_parts(line: str) -> tuple[str, str]:
        """以首个 ``//`` 为界拆成代码与注释；无则注释为空串。参数：line — 单行 CAPL。返回：``(code, comment)``。"""
        if "//" not in line:
            return line, ""
        code, comment = line.split("//", 1)
        return code, comment

    @staticmethod
    def is_test_step_line(line: str) -> bool:
        """注释中含「测试步骤」关键字（中/简）则视为测试步骤行。参数：line — 已翻译后一行。返回：bool。"""
        _, comment = CANRenderUtility.split_capl_comment_parts(line)
        return "测试步骤" in comment or "\u6d4b\u8bd5\u6b65\u9aa4" in comment

    @staticmethod
    def is_expect_line(line: str) -> bool:
        """注释中含「预期结果」则视为预期结果行。返回：bool。"""
        _, comment = CANRenderUtility.split_capl_comment_parts(line)
        return "预期结果" in comment or "\u9884\u671f\u7ed3\u679c" in comment

    @staticmethod
    def is_soa_expect_check_line(line: str) -> bool:
        """SOA 场景下为 CHECK+CHECKREQ 成对之一（非 `_Prepare` 行）。返回：bool。"""
        if "_Prepare" in line or "_PREPARE" in line:
            return False
        code_part, _ = CANRenderUtility.split_capl_comment_parts(line)
        code_upper = code_part.upper()
        if "SOA" not in code_upper:
            return False
        return "SOA_CHECK(" in code_upper or "CHECKREQ(" in code_upper

    @staticmethod
    def is_soa_expect_check_only_line(line: str) -> bool:
        """仅含 `SOA_CHECK` 且不含 `CHECKREQ` 的预期行。返回：bool。"""
        if "_Prepare" in line or "_PREPARE" in line:
            return False
        code_part, _ = CANRenderUtility.split_capl_comment_parts(line)
        code_upper = code_part.upper()
        if "SOA" not in code_upper:
            return False
        return "SOA_CHECK(" in code_upper and "CHECKREQ(" not in code_upper

    @staticmethod
    def has_traceback_token(line: str) -> bool:
        """行内（含注释）出现 ``traceback`` 类词则 True，用于错误传播识别。返回：bool。"""
        code_part, comment_part = CANRenderUtility.split_capl_comment_parts(line)
        text = f"{code_part} {comment_part}"
        return bool(re.search(r"\btraceback\d*\b", text, re.IGNORECASE))

    @staticmethod
    def is_wait_or_sleep_test_step(line: str) -> bool:
        """测试步骤且注释中匹配 wait/延时等关键字。返回：bool。"""
        _, comment = CANRenderUtility.split_capl_comment_parts(line)
        if not comment.strip():
            return False
        return bool(
            re.search(
                r"\b(?:wait|TC_4G_Time_Delay_Second|TC_Sleep)\b",
                comment,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def is_soa_req_test_step(line: str) -> bool:
        """测试步骤行且代码部含 `SOA_REQ` 等。返回：bool。"""
        if not CANRenderUtility.is_test_step_line(line):
            return False
        code_part, _ = CANRenderUtility.split_capl_comment_parts(line)
        code_upper = code_part.upper()
        return "SOA_REQ(" in code_upper or "SOA REQ" in code_upper

    @staticmethod
    def add_prepare_suffix_to_line(line: str) -> str:
        """在首段函数名后插 `_Prepare`，供 SOA 成对重排。参数：line — 单步 CAPL 行。返回：新行。"""
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

    def __init__(
        self,
        include_files: Sequence[str] | None = None,
        *,
        central_sheet_soa_wrapper_enabled: bool = False,
    ) -> None:
        """
        参数：include_files — Master 中额外 `#include`；central_sheet_soa_wrapper_enabled — 是否注入中央域 SOA 包壳 connect/close。返回：无。
        """
        self.include_files = list(include_files or [])
        self.central_sheet_soa_wrapper_enabled = central_sheet_soa_wrapper_enabled

    def render_single_file(self, case: CANTestCase) -> str:
        """单用例等效于 `render_sheet_file([case])`。"""
        return self.render_sheet_file([case])

    def render_sheet_file(self, cases: Iterable[CANTestCase]) -> str:
        """将同一 sheet 的若干用例拼成单文件 CAPL 文本（含头段 includes/variables 骨架）。参数：cases — 可迭代。返回：CRLF 结尾全文。"""
        case_list = list(cases or [])
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
        for idx, case in enumerate(case_list):
            lines.extend(
                self.render_testcase(
                    case,
                    inject_connect=(
                        self.central_sheet_soa_wrapper_enabled and idx == 0
                    ),
                    inject_close=(
                        self.central_sheet_soa_wrapper_enabled and idx == len(case_list) - 1
                    ),
                )
            )
            lines.append("")
        return "\r\n".join(lines).rstrip() + "\r\n"

    def render_master(self, cases: Iterable[CANTestCase]) -> str:
        """基于各 `case.target_path`  basename 生成仅含 includes+variables 的轻量 Master 文本（`BaseTask.load` 路径用）。"""
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

    def render_testcase(
        self,
        case: CANTestCase,
        *,
        inject_connect: bool = False,
        inject_close: bool = False,
    ) -> list[str]:
        """
        渲染单条 `testcase` 块：TestDescription、可选 SOA 包壳、步骤经 `apply_soa_prepare_reorder` 后落行。

        参数：case — 含 `steps` 等；inject_connect / inject_close — 中央域多 case 时首尾注入 SOA 宏。返回：行列表（无换行符）。
        """
        # CAPL 标识符不能含连字符，需替换为下划线
        case_name = (case.case_id or "unnamed_case").replace("-", "_")

        lines = [f"testcase {case_name}()", "{"]

        if case.name:
            # 统一清洗名称中的换行符，避免 TestDescription 跨多行
            name_str = str(case.name)
            # 将 \r\n / \n / \r 等换行统一替换为空格
            name_str = re.sub(r"[\r\n]+", " ", name_str)
            # 转义：只对单独出现的 \ 转义为 \\，已有的 \\ 原样保留不变成 \\\\
            safe_name = self.escape_capl_string(name_str)
            lines.append(f'  TestDescription("{safe_name}");')
        if inject_connect:
            lines.append("  g_EM_SOAGen_Swc_SOA_CONNECT();")
        if case.case_id_had_issues:
            warning = self.build_caseid_warning(case)
            safe_warning = self.escape_capl_string(str(warning))
            lines.append(f'  teststep("warning","{safe_warning}");')

        # 在渲染前，对步骤应用 SOA REQ / CHECK / CHECKREQ 成对前移与 _Prepare 规则（仅针对 CAN 步骤）
        steps = list(case.steps or [])
        if steps:
            steps = self.apply_soa_prepare_reorder(steps)
            lines.extend(step.rstrip() for step in steps)
        else:
            lines.append('  teststep("info","No translated steps");')

        if inject_close:
            lines.append("  g_EM_SOAGen_Swc_SOA_CLOSE();")
        lines.append("}")
        return lines

    @staticmethod
    def apply_soa_prepare_reorder(lines: list[str]) -> list[str]:
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

        total_line_count = len(lines)
        # 记录每个“节点首行测试步骤”前/后需要插入的 Prepare 行
        prepare_before: dict[int, list[str]] = {}
        prepare_after: dict[int, list[str]] = {}
        # 先记录所有 Prepare 的来源顺序与目标位置，最后统一按来源顺序落位
        scheduled_prepares: list[tuple[int, int, str, str]] = []

        node_scan_index = 0
        while node_scan_index < total_line_count:
            if not CANRenderUtility.is_test_step_line(lines[node_scan_index]):
                node_scan_index += 1
                continue

            node_start = node_scan_index
            node_end_index = node_scan_index + 1
            # 节点范围：[node_start, node_end_index) —— 直到下一个测试步骤或结尾
            while node_end_index < total_line_count and not CANRenderUtility.is_test_step_line(lines[node_end_index]):
                node_end_index += 1

            # 在该节点范围内查找 SOA CHECK / CHECKREQ 预期结果行
            node_is_wait_or_sleep = CANRenderUtility.is_wait_or_sleep_test_step(lines[node_start])
            for line_index in range(node_start, node_end_index):
                if (
                    CANRenderUtility.is_expect_line(lines[line_index])
                    and CANRenderUtility.is_soa_expect_check_line(lines[line_index])
                ):
                    prepare_line = CANRenderUtility.add_prepare_suffix_to_line(lines[line_index])
                    # 新增规则：
                    # SOA_CHECK（不含 CHECKREQ）且该行出现 traceback* 时，
                    # 优先前插到最近的前置 SOA REQ 测试步骤前；
                    # 若前面没有 SOA REQ，则前插到最近的前置 wait/sleep 测试步骤前。
                    if (
                        CANRenderUtility.is_soa_expect_check_only_line(lines[line_index])
                        and CANRenderUtility.has_traceback_token(lines[line_index])
                    ):
                        nearest_soa_req_idx = None
                        for reverse_scan_index in range(line_index - 1, -1, -1):
                            if CANRenderUtility.is_soa_req_test_step(lines[reverse_scan_index]):
                                nearest_soa_req_idx = reverse_scan_index
                                break

                        if nearest_soa_req_idx is not None:
                            scheduled_prepares.append(
                                (line_index, nearest_soa_req_idx, "before", prepare_line)
                            )
                            continue

                        nearest_wait_idx = None
                        for reverse_scan_index in range(line_index - 1, -1, -1):
                            if (
                                CANRenderUtility.is_test_step_line(lines[reverse_scan_index])
                                and CANRenderUtility.is_wait_or_sleep_test_step(lines[reverse_scan_index])
                            ):
                                nearest_wait_idx = reverse_scan_index
                                break

                        if nearest_wait_idx is not None:
                            scheduled_prepares.append(
                                (line_index, nearest_wait_idx, "before", prepare_line)
                            )
                            continue

                    default_placement = "after" if node_is_wait_or_sleep else "before"
                    scheduled_prepares.append(
                        (line_index, node_start, default_placement, prepare_line)
                    )

            node_scan_index = node_end_index

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
    def escape_capl_string(input_text: str) -> str:
        """转义 CAPL 字符串：只对单独出现的 \\ 转义为 \\\\，已有的 \\\\ 原样保留不变成 \\\\\\\\；双引号转义为 \\\"。"""
        # 仅当反斜杠后没有紧跟另一个反斜杠时才替换为双反斜杠（单独 \ -> \\，\\ 保持为 \\）
        escaped_text = re.sub(r"\\(?!\\)", r"\\\\", input_text)
        escaped_text = escaped_text.replace('"', '\\"')
        return escaped_text

    @staticmethod
    def build_caseid_warning(case: CANTestCase) -> str:
        """生成 warning 文案，避免嵌套双引号导致 CAPL 字符串解析错误。"""
        if case.case_id_issue_type == "duplicate" and case.duplicate_original_id:
            return f"原始用例id为{case.duplicate_original_id}"
        raw_id = case.raw_id or case.case_id
        return f"原始用例id为{raw_id}"

__all__ = ["CANFileRenderer", "CANRenderUtility"]
