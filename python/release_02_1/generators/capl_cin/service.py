#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CIN 生成调度服务。

不再依赖 CINLegacyHooks；关键字加载、读 Clib、步骤渲染、内容拼装均在 runtime_io 内完成。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from core.error_module import ErrorModuleResolver
from core.common.name_sanitize import sanitize_clib_name

from .runtime_io import (
    generate_content as io_generate_content,
    load_keyword_specs as io_load_keyword_specs,
    read_clib_steps as io_read_clib_steps,
    render_step_lines as io_render_step_lines,
)


class CINGeneratorService:
    """接管 CIN 旧版主编排流程的 service。"""

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        """参数: logger — 可选 logger，用于输出进度与错误。"""
        self.logger = logger

    def run_legacy_pipeline(self, runtime: dict) -> str | None:
        """执行 CIN 生成：读 Clib 步骤、翻译、写 .cin 文件。
        参数: runtime — 含 mapping_excel_path, sheet_names_str, input_excel_path, input_sheet, output_dir, output_cin_filename；可选 io_mapping_ctx, config_enum_ctx。
        返回: 生成的 .cin 文件绝对路径，无输出时 None。
        """
        sheet_names = [
            s.strip()
            for s in str(runtime.get("sheet_names_str", "")).split(",")
            if s and str(s).strip()
        ]
        if not sheet_names:
            sheet_names = ["HIL用例关键字说明"]

        keyword_specs = io_load_keyword_specs(runtime["mapping_excel_path"], sheet_names)

        sheet_title, raw_ordered = io_read_clib_steps(
            runtime["input_excel_path"],
            clib_sheet=runtime.get("input_sheet"),
        )

        io_mapping_ctx = runtime.get("io_mapping_ctx")
        config_enum_ctx = runtime.get("config_enum_ctx")

        ordered = []
        for name, raw_steps in raw_ordered:
            export_func = f"g_HIL_Clib_Swc_Clib_{sanitize_clib_name(name)}"
            steps: list[str] = []
            for step_item in raw_steps:
                if isinstance(step_item, tuple):
                    raw, excel_row_num = step_item
                else:
                    raw = step_item
                    excel_row_num = None
                rendered = io_render_step_lines(
                    raw,
                    keyword_specs=keyword_specs,
                    io_mapping_ctx=io_mapping_ctx,
                    config_enum_ctx=config_enum_ctx,
                    logger=self.logger,
                    source_id=name,
                    excel_name=os.path.basename(runtime["input_excel_path"]),
                    sheet_name=sheet_title,
                    name=name,
                    excel_row_num=excel_row_num,
                )
                if rendered:
                    steps.extend(rendered)
            ordered.append((export_func, steps))

        if not ordered:
            return None

        cin_content, error_records = io_generate_content(ordered, include_files=None)
        cin_content = cin_content.replace("\r\n", "\n").replace("\n", "\r\n")
        out_path = os.path.join(runtime["output_dir"], runtime["output_cin_filename"])
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(cin_content.encode("gb18030", errors="replace"))

        self._log_error_records(error_records)
        if self.logger:
            self.logger.info(f"[cin] .cin 文件已生成: {out_path}")
        return out_path

    def _log_error_records(self, error_records) -> None:
        """将 error_records 按行写入 logger。参数: error_records — (func_name, teststep_content, teststepfail_content) 列表。无返回值。"""
        if not error_records or not self.logger:
            return
        for func_name, teststep_content, teststepfail_content in error_records:
            clib_name = "未知"
            if func_name.startswith("g_HIL_Clib_Swc_Clib_"):
                clib_name = func_name[len("g_HIL_Clib_Swc_Clib_"):]

            step_prefix = 'teststep("step","'
            if step_prefix in teststep_content:
                start_idx = teststep_content.find(step_prefix) + len(step_prefix)
                end_idx = teststep_content.rfind('");')
                if end_idx > start_idx:
                    step_text = teststep_content[start_idx:end_idx].replace('\\"', '"')
                else:
                    step_text = teststep_content
            else:
                step_text = teststep_content

            fail_prefix = 'teststepfail("fail","'
            if fail_prefix in teststepfail_content:
                start_idx = teststepfail_content.find(fail_prefix) + len(fail_prefix)
                end_idx = teststepfail_content.rfind('");')
                if end_idx > start_idx:
                    fail_text = teststepfail_content[start_idx:end_idx].replace('\\"', '"')
                else:
                    fail_text = teststepfail_content
            else:
                fail_text = teststepfail_content

            err_mod = ErrorModuleResolver.resolve(fail_text)
            error_msg = f"Clib_Name：{clib_name} 用例步骤：{step_text}  原因：{fail_text}"
            self.logger.error(f"错误模块【{err_mod}】 {error_msg}")
