#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件写入工具（供所有生成器复用）

- write_text_safe() : 以指定编码写入文本，失败时回退到 fallback 编码
"""

from __future__ import annotations

from typing import Union


def write_text_safe(
    file_path: str,
    content: Union[str, list[str]],
    encoding: str = "utf-8",
    fallback_encoding: str = "gb18030",
    newline: str = "\n",
) -> None:
    """
    将文本内容安全写入文件。优先使用 encoding，若写入失败则用 fallback_encoding 重试。

    形参：
        path — 输出文件路径。
        content — 字符串或行列表（list 时用 newline 连接）。
        encoding — 首选编码，默认 utf-8。
        fallback_encoding — 首选编码失败时的回退编码，默认 gb18030。
        newline — content 为 list 时使用的行分隔符。
    返回值：无。
    """
    if isinstance(content, list):
        text = newline.join(content)
    else:
        text = content

    try:
        with open(file_path, "w", encoding=encoding, newline="") as text_output_file:
            text_output_file.write(text)
        return
    except (UnicodeEncodeError, OSError):
        pass
    with open(file_path, "w", encoding=fallback_encoding, newline="") as text_output_file:
        text_output_file.write(text)
