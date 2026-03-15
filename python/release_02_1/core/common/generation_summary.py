#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成结果汇总辅助。

统一拼装“未生成”的原因说明，供 CAN/XML 等目录模式汇总复用。
"""

from __future__ import annotations


def build_ungenerated_reason(
    stats: dict,
    *,
    generated_label: str,
) -> str:
    """根据生成统计拼装「未生成」原因说明，供目录模式汇总展示。
    参数:
        stats: 含 total_cases、filtered_by_*、header_validation_failed 等键的统计字典。
        generated_label: 生成物名称（如「CAN 用例」），用于最终原因文案。
    返回: 拼接后的一条原因字符串（多条用「；」连接）。
    """
    reasons: list[str] = []
    if stats.get("header_validation_failed", 0) > 0:
        details = stats.get("header_validation_details", [])
        if details:
            for detail in details:
                sheet_name = detail.get("sheet", "未知工作表")
                col_details = detail.get("details", [])
                if col_details:
                    reasons.append(
                        f"表格格式不符（工作表'{sheet_name}'：{'; '.join(col_details)}）"
                    )
        else:
            reasons.append(
                f"表格格式不符（{stats.get('header_validation_failed', 0)}个工作表验证失败）"
            )

    total = stats.get("total_cases", 0)
    if total == 0 and not reasons:
        reasons.append("未读取到任何用例（可能是表格格式问题或文件为空）")
    else:
        for key, label in (
            ("filtered_by_level", "等级过滤"),
            ("filtered_by_platform", "平台过滤"),
            ("filtered_by_model", "车型过滤"),
            ("filtered_by_type", "用例类型过滤"),
        ):
            value = stats.get(key, 0)
            if value <= 0:
                continue
            if key == "filtered_by_type":
                reasons.append(f"{label}：{value}个用例被过滤（非自动测试）")
            else:
                reasons.append(f"{label}：{value}个用例被过滤")

        if not reasons and total > 0:
            reasons.append(f"所有{total}个用例均通过过滤，但未生成{generated_label}（可能是其他原因）")

    if not reasons:
        reasons.append("原因未知（请查看详细日志）")
    return "；".join(reasons)
