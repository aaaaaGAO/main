#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按关键字映射表生成错误描述（CAN / CIN 等共用）。

根据原始步骤行与 keyword_specs 推断“哪个函数/关键字不存在”，
用于统一错误文案（如 "Set_CF05关键字不存在"）。
"""

from __future__ import annotations

from typing import Any, Dict, List


class KeywordErrorDescriber:
    """根据关键字映射表描述“关键字不存在”类错误，供 CAN/CIN 错误注释与日志使用。"""

    def __init__(self) -> None:
        """初始化描述器，内部维护 keyword_specs 的索引缓存。"""
        self.index_cache: Dict[int, Dict[str, Dict[str, Any]]] = {}

    def build_index(self, keyword_specs: dict) -> Dict[str, Dict[str, Any]]:
        """根据 keyword_specs 构建「函数名 -> 关键字 token 列表」索引。参数: keyword_specs — 关键字规格字典。返回: 索引字典。"""
        index_map: Dict[str, Dict[str, Any]] = {}
        for spec in keyword_specs.values():
            func = str(getattr(spec, "func_name", "") or "").strip()
            if not func:
                continue
            func_key = func.casefold()
            func_record = index_map.setdefault(func_key, {"has_func_only": False, "keyword_tokens_list": []})
            kw = str(getattr(spec, "keyword", "") or "").strip()
            if kw:
                func_record["keyword_tokens_list"].append([token for token in kw.split() if token])
            else:
                func_record["has_func_only"] = True
        return index_map

    def get_index(self, keyword_specs: dict) -> Dict[str, Dict[str, Any]]:
        """获取或构建 keyword_specs 的索引（带缓存）。参数: keyword_specs — 关键字规格字典。返回: 索引字典。"""
        cache_key = id(keyword_specs)
        if cache_key not in self.index_cache:
            self.index_cache[cache_key] = self.build_index(keyword_specs)
        return self.index_cache[cache_key]

    def describe(self, original_line: str, keyword_specs: dict) -> str:
        """根据原始步骤行与关键字映射表返回错误描述。
        参数: original_line — 原始步骤行；keyword_specs — 关键字规格字典。
        返回: 错误描述（如「写入错误」「{func}关键字不存在」等）。
        """
        line_no_comment = str(original_line).split("//", 1)[0].strip()
        tokens = line_no_comment.split()
        if tokens and tokens[0].lower() == "step":
            tokens = tokens[1:]
        if not tokens:
            return "写入错误"

        func = tokens[0]
        rest = tokens[1:]
        index_map = self.get_index(keyword_specs)
        func_record = index_map.get(func.casefold())
        if func_record is None:
            return f"{func}关键字不存在"

        kw_tokens_list: List[List[str]] = func_record.get("keyword_tokens_list") or []
        if not kw_tokens_list:
            return "写入错误"
        if not rest:
            return "关键字不存在"

        candidates = list(kw_tokens_list)
        for token_index, token_text in enumerate(rest):
            new_candidates = [
                keyword_tokens
                for keyword_tokens in candidates
                if len(keyword_tokens) > token_index
                and keyword_tokens[token_index].casefold() == token_text.casefold()
            ]
            if not new_candidates:
                return f"{token_text}关键字不存在"
            candidates = new_candidates
        return f"{' '.join(rest)}关键字不存在"


# 单例，供 CIN/CAN 等处直接调用
_default_describer: KeywordErrorDescriber | None = None


def describe_keyword_error(original_line: str, keyword_specs: dict) -> str:
    """根据映射表描述关键字错误（使用默认 KeywordErrorDescriber）。参数: original_line — 原始步骤行；keyword_specs — 关键字规格字典。返回: 错误描述字符串。"""
    global _default_describer
    if _default_describer is None:
        _default_describer = KeywordErrorDescriber()
    return _default_describer.describe(original_line, keyword_specs)
