#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件写入工具（供所有生成器复用）。

本模块仅保留 `FileIOUtility` 类，负责文本安全写入：
优先使用主编码，失败时自动回退到备用编码。
"""

from __future__ import annotations

from typing import Union


class FileIOUtility:
    """文件写入工具类。"""

    @staticmethod
    def write_text_safe(
        file_path: str,
        content: Union[str, list[str]],
        encoding: str = "utf-8",
        fallback_encoding: str = "gb18030",
        newline: str = "\n",
    ) -> None:
        """将文本内容安全写入文件。优先 encoding，失败时 fallback_encoding。"""
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

