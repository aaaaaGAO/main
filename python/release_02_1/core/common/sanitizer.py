#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用例 ID 清洗工具。

真实逻辑已下沉到 core.common，供 CAN/XML 等生成器复用。
"""

from __future__ import annotations

import re
from typing import Any, Tuple

# 用于从混杂字符串中尽量提取出 SYS-... 片段（宽松，避免误删中间内容）
_RE_SYS_ID = re.compile(r"(SYS-[^\r\n]+)")
# 末尾需要剔除的标点符号（只处理尾部）
_TRAILING_PUNCT = " \t,，。.;；:：!！?？、/\\@#￥$%^&*+=~`|<>《》“”\"'）)】]"
# 非法字符：全角括号、空格等，替换为空白再 strip
_RE_ILLEGAL = re.compile(r"[\s\u3000\uFF08\uFF09\u3010\u3011（）【】]+")
_RE_HAS_CJK = re.compile(r"[\u4e00-\u9fff]")
# CAPL 标识符仅允许：字母、数字、下划线、连字符（连字符在 renderer 中会再替换为下划线）
_RE_CAPL_SAFE = re.compile(r"[^a-zA-Z0-9_\-]")


def _chinese_to_pinyin(text: str) -> str:
    """将字符串中的中文转为拼音，非中文字符原样保留。参数: text — 原始字符串。返回: 转换后的字符串。"""
    try:
        from pypinyin import Style, lazy_pinyin  # type: ignore
    except ImportError:
        return text

    result: list[str] = []
    for c in text:
        if "\u4e00" <= c <= "\u9fff":
            py = lazy_pinyin(c, style=Style.NORMAL)
            result.append(py[0] if py else c)
        else:
            result.append(c)
    return "".join(result)


def sanitize_case_id(raw: Any) -> Tuple[str, bool, str]:
    """清洗用例 ID：非法字符、中文转拼音、SYS- 提取等。
    参数: raw — 原始用例 ID（任意类型，会转 str）。
    返回: (cleaned, changed, reason)，cleaned 为清洗后字符串，changed 为是否改动，reason 为原因说明。
    """
    if raw is None:
        return ("", False, "empty")

    raw_str = str(raw).strip()
    if not raw_str:
        return ("", False, "empty")

    m = _RE_SYS_ID.search(raw_str)
    candidate = m.group(1).strip() if m else raw_str

    cleaned = _RE_ILLEGAL.sub("", candidate)
    cleaned = cleaned.rstrip(_TRAILING_PUNCT).strip()

    had_cjk = bool(_RE_HAS_CJK.search(cleaned))
    if had_cjk:
        cleaned = _chinese_to_pinyin(cleaned)
        cleaned = cleaned.rstrip(_TRAILING_PUNCT).strip()

    # 仅保留 CAPL 合法字符（无空格、中文、逗号、括号等），供 testcase 名称等使用
    cleaned = _RE_CAPL_SAFE.sub("", cleaned)

    if had_cjk:
        if cleaned:
            return (cleaned, True, "chinese_to_pinyin")
        return (cleaned, True, "chinese_to_pinyin_strip_all")

    changed = cleaned != raw_str
    if not changed:
        return (cleaned, False, "ok")
    if not cleaned:
        return (cleaned, True, "strip_all")
    if m and candidate != raw_str:
        return (cleaned, True, "extract_SYS_pattern")
    if _RE_ILLEGAL.search(candidate) or " " in candidate:
        return (cleaned, True, "remove_spaces_or_illegal_chars")
    return (cleaned, True, "strip_trailing_punct")


__all__ = ["sanitize_case_id"]
