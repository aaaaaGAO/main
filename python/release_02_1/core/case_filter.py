#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用例筛选：等级 / 平台 / 车型 / 自动测试 过滤逻辑，供 CAN / XML 等生成器共用。

表头约定：等级、平台、车型、Target Version、用例类型为可选列。若 Excel 表头不包含某一列，
生成器会在 TestCases.log 打 warning（如「表头不包含平台列，默认平台均符合要求」），
并将该维度按默认通过（等级/平台/车型/Target Version 传 ALL 或空，用例类型传 自动）参与本类 is_filtered。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass
class FilterStats:
    """筛选统计（仅过滤计数）。"""

    filtered_by_level: int = 0
    filtered_by_platform: int = 0
    filtered_by_model: int = 0
    filtered_by_type: int = 0
    filtered_by_target_version: int = 0


class CaseFilter:
    """
    等级 / 平台 / 车型 / Target Version / 用例类型（自动测试）过滤，与 XML/CAN 行为一致。
    过滤优先级：等级 -> 平台 -> 车型 -> Target Version -> 用例类型。
    Target Version 含 IPDT 的选项：选中某版本时自动包含该版本及以下所有 IPDT 版本（如选 IPDT4.0 则含 1.0~4.0）。
    用例的 Target Version 为空时一律通过（参与生成）。
    """

    def __init__(
        self,
        allowed_levels: Optional[Set[str]] = None,
        allowed_platforms: Optional[Set[str]] = None,
        allowed_models: Optional[Set[str]] = None,
        allowed_target_versions: Optional[Set[str]] = None,
    ) -> None:
        """初始化用例筛选器，绑定允许的等级/平台/车型/Target Version 集合。
        参数:
            allowed_levels: 允许的用例等级集合（如 S/A/B/C），None 或空表示不过滤等级。
            allowed_platforms: 允许的平台集合，None 或空表示不过滤。
            allowed_models: 允许的车型集合，None 或空表示不过滤。
            allowed_target_versions: 允许的 Target Version 集合（已按 IPDT 规则展开），None 或空表示不过滤。
        """
        self.allowed_levels = {
            str(level_item).upper().strip() for level_item in (allowed_levels or set())
        }
        self.allowed_platforms = {
            str(platform_item).upper().strip()
            for platform_item in (allowed_platforms or set())
        }
        self.allowed_models = {
            str(model_item).upper().strip() for model_item in (allowed_models or set())
        }
        self.allowed_target_versions = {
            str(version_item).upper().strip()
            for version_item in (allowed_target_versions or set())
        }
        self.stats = FilterStats()

    @staticmethod
    def is_auto_case_type(case_type: str) -> bool:
        """判断用例类型是否视为「自动测试」（空或包含「自动」则通过）。参数：case_type — 用例类型字符串。返回：True 表示通过自动测试过滤。"""
        if not case_type:
            return True
        raw = str(case_type).strip()
        if not raw:
            return True
        return "自动" in raw

    def is_filtered(
        self,
        level: str,
        platform: str,
        model: str,
        case_type: str,
        target_version: Optional[str] = None,
    ) -> tuple[bool, str]:
        """判断一条用例是否被过滤，及过滤原因。target_version 为空时该维度一律通过。"""
        level = str(level or "").strip().upper()
        platform = str(platform or "").strip().upper()
        model = str(model or "").strip().upper()
        target_version_str = str(target_version or "").upper().strip()

        if self.allowed_levels and level and "ALL" not in level and level not in self.allowed_levels:
            self.stats.filtered_by_level += 1
            allowed = ",".join(sorted(self.allowed_levels))
            return True, f"等级过滤：生成{{{allowed}}} 当前'{level}'"

        if self.allowed_platforms and platform and "ALL" not in platform and platform not in self.allowed_platforms:
            self.stats.filtered_by_platform += 1
            allowed = ",".join(sorted(self.allowed_platforms))
            return True, f"平台过滤：生成{{{allowed}}} 当前'{platform}'"

        if self.allowed_models and model and "ALL" not in model and model not in self.allowed_models:
            self.stats.filtered_by_model += 1
            allowed = ",".join(sorted(self.allowed_models))
            return True, f"车型过滤：生成{{{allowed}}} 当前'{model}'"

        if self.allowed_target_versions and target_version_str:
            if target_version_str not in self.allowed_target_versions:
                self.stats.filtered_by_target_version += 1
                allowed = ",".join(sorted(self.allowed_target_versions))[:80]
                if len(sorted(self.allowed_target_versions)) > 1:
                    allowed += "..."
                return True, f"Target Version 过滤：生成{{{allowed}}} 当前'{target_version_str}'"
        # Target Version 为空时默认通过

        if not self.is_auto_case_type(case_type):
            self.stats.filtered_by_type += 1
            return True, "非自动测试/空"

        return False, ""

    @staticmethod
    def parse_levels(text: Optional[str]) -> Optional[Set[str]]:
        """解析 Case_Levels 配置字符串为允许的等级集合。
        参数: text — 配置字符串，空或 ALL 表示不过滤；支持逗号/空格分隔及 SABC 连写。
        返回: 允许的等级集合；None 表示不过滤等级。
        """
        if text is None:
            return None
        normalized_text = str(text).strip()
        if not normalized_text:
            return None
        parts_raw = [
            item.strip()
            for item in normalized_text.replace("，", ",").replace(" ", ",").split(",")
            if item.strip()
        ]
        parts: list[str] = []
        for part in parts_raw:
            upper_part = part.upper()
            if len(upper_part) > 1 and all(ch in {"S", "A", "B", "C"} for ch in upper_part):
                parts.extend(list(upper_part))
            else:
                parts.append(upper_part)
        if not parts or "ALL" in parts:
            return None
        return set(parts)

    @staticmethod
    def parse_platforms_or_models(text: Optional[str]) -> Optional[Set[str]]:
        """解析 Case_Platforms 或 Case_Models 配置字符串为集合。参数：text — 配置字符串，空或仅 ALL 表示不过滤；逗号/空格分隔。返回：允许的平台或车型集合；None 表示不过滤。"""
        if text is None:
            return None
        normalized_text = str(text).strip()
        if not normalized_text:
            return None
        parts = [
            item.strip().upper()
            for item in normalized_text.replace("，", ",").replace(" ", ",").split(",")
            if item.strip()
        ]
        if not parts:
            return None
        if "ALL" in parts and len(parts) == 1:
            return None
        return set(parts)

    _IPDT_NUMBER_RE = re.compile(r"IPDT\s*(\d+)", re.IGNORECASE)

    @staticmethod
    def extract_ipdt_number(option: str) -> Optional[int]:
        """从选项字符串中提取 IPDT 编号（如 CEA2.x_IPDT4.0 -> 4，CEA2.x_VP1.1(IPDT1.0) -> 1）。"""
        match = CaseFilter._IPDT_NUMBER_RE.search(option)
        return int(match.group(1)) if match else None

    @staticmethod
    def parse_target_versions(
        selected_text: Optional[str],
        all_options: Optional[List[str]] = None,
    ) -> Optional[Set[str]]:
        """解析前端勾选的 Target Version 为允许集合，并对含 IPDT 的选项做展开：选中某版本则包含该版本及以下所有 IPDT 版本。
        参数：selected_text — 逗号/空格分隔的勾选项；all_options — filter_options 中 Target Version 的完整列表，用于 IPDT 展开。
        返回：允许的 Target Version 集合；None 或空表示不过滤。
        """
        if selected_text is None:
            return None
        normalized_text = str(selected_text).strip()
        if not normalized_text:
            return None
        selected = [
            item.upper().strip()
            for item in normalized_text.replace("，", ",").replace(" ", ",").split(",")
            if item.strip()
        ]
        if not selected:
            return None
        if "ALL" in selected and len(selected) == 1:
            return None

        allowed: Set[str] = set(selected)
        all_opts = [str(option).upper().strip() for option in (all_options or []) if str(option).strip()]
        # 含 IPDT 的选项：取选中项中的最大 IPDT 编号 N，将 all_options 中所有 IPDT 编号 <= N 的项加入 allowed
        max_ipdt: Optional[int] = None
        for selected_option in selected:
            ipdt_number = CaseFilter.extract_ipdt_number(selected_option)
            if ipdt_number is not None:
                max_ipdt = ipdt_number if max_ipdt is None else max(max_ipdt, ipdt_number)
        if max_ipdt is not None and all_opts:
            for available_option in all_opts:
                option_text = available_option.strip()
                if not option_text or option_text in allowed:
                    continue
                candidate_ipdt_number = CaseFilter.extract_ipdt_number(option_text)
                if candidate_ipdt_number is not None and candidate_ipdt_number <= max_ipdt:
                    allowed.add(option_text)
        return allowed if allowed else None
