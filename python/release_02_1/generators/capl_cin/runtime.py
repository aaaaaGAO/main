#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIN 入口运行期辅助。"""

from __future__ import annotations

import os

from infra.filesystem.pathing import get_project_root
from openpyxl import load_workbook

from core.generator_config import GeneratorConfig
from core.mapping_context import MappingContext
from utils.path_utils import resolve_target_subdir_smart


class CINEntrypointSupport:
    """收拢 CIN 入口阶段的路径、配置与上下文初始化。"""

    @staticmethod
    def resolve_base_dir() -> str:
        """返回项目根目录（Configuration.txt 所在目录），统一使用 infra.filesystem.pathing.get_project_root。"""
        return get_project_root(__file__)

    @staticmethod
    def load_runtime_config(base_dir: str) -> dict:
        gconfig = GeneratorConfig(base_dir).load()
        config_path = gconfig.config_path or os.path.join(base_dir, "config", "Configuration.txt")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"未找到配置文件: {config_path}")

        cfg = gconfig.raw_config
        input_excel_file = gconfig.get_first(
            [
                ("LR_REAR", "cin_input_excel"),
                ("LR_REAR", "Cin_Input_Excel"),
                ("PATHS", "Cin_Input_Excel"),
                ("PATHS", "cin_input_excel"),
            ]
        )
        input_sheet = gconfig.get_first(
            [
                ("LR_REAR", "Cin_Input_Sheet"),
                ("LR_REAR", "cin_input_sheet"),
                ("PATHS", "Cin_Input_Sheet"),
                ("PATHS", "cin_input_sheet"),
            ],
            fallback="",
        )
        mapping_excel_file = gconfig.get_fixed("cin_mapping_excel") or gconfig.get_fixed(
            "unified_mapping_excel"
        )
        if not mapping_excel_file:
            mapping_excel_file = gconfig.get(
                "PATHS",
                "Cin_Mapping_Excel",
                fallback="input/关键字-CAPL函数映射表.xlsx",
            )

        cin_mapping_sheet = gconfig.get_fixed("cin_mapping_sheet") or gconfig.get(
            "PATHS", "Cin_Mapping_Sheet", fallback=""
        )
        sheet_names_str = gconfig.get_fixed("mapping_sheets") or gconfig.get(
            "PATHS",
            "Mapping_Sheets",
            fallback="HIL用例关键字说明,EM_CAN&Uart&LIN,EM_SOA,EM_总线测试专用,EM_设备&其他",
        )
        if (
            cin_mapping_sheet
            and str(cin_mapping_sheet).strip()
            and str(cin_mapping_sheet).strip() != "HIL用例关键字说明"
        ):
            sheet_names_str = str(cin_mapping_sheet).strip()

        output_dir_cin = gconfig.get_first(
            [
                ("LR_REAR", "Output_Dir_Cin"),
                ("LR_REAR", "output_dir_cin"),
                ("PATHS", "Output_Dir_Cin"),
                ("PATHS", "output_dir_cin"),
            ]
        )
        output_dir = gconfig.get_first(
            [
                ("LR_REAR", "Output_Dir"),
                ("LR_REAR", "output_dir"),
                ("PATHS", "Output_Dir"),
                ("PATHS", "output_dir"),
            ]
        )
        if output_dir_cin and str(output_dir_cin).strip():
            output_dir = output_dir_cin
        if not output_dir or not str(output_dir).strip():
            output_dir = "output"

        output_cin_filename = (
            gconfig.get_fixed("cin_output_filename") or "generated_from_keyword.cin"
        )

        if not input_excel_file:
            raise ValueError("未配置 Cin_Input_Excel 或 cin_input_excel")
        input_excel_path = (
            input_excel_file
            if os.path.isabs(input_excel_file)
            else os.path.join(base_dir, input_excel_file)
        )
        if mapping_excel_file.startswith("./"):
            mapping_excel_file = mapping_excel_file[2:]
        mapping_excel_path = (
            mapping_excel_file
            if os.path.isabs(mapping_excel_file)
            else os.path.join(base_dir, mapping_excel_file)
        )
        output_dir = resolve_target_subdir_smart(base_dir, output_dir, "TESTmode")

        return {
            "config_path": config_path,
            "cfg": cfg,
            "input_sheet": input_sheet,
            "input_excel_path": input_excel_path,
            "mapping_excel_path": mapping_excel_path,
            "sheet_names_str": sheet_names_str,
            "output_dir": output_dir,
            "output_cin_filename": output_cin_filename,
        }

    @staticmethod
    def detect_sheet_title(input_excel_path: str, input_sheet: str | None) -> str:
        try:
            wb_temp = load_workbook(input_excel_path, data_only=True, read_only=True)
            ws_temp = wb_temp.active
            if input_sheet and str(input_sheet).strip():
                sn = str(input_sheet).strip()
                if sn in wb_temp.sheetnames:
                    ws_temp = wb_temp[sn]
            sheet_title = ws_temp.title
            wb_temp.close()
            return sheet_title
        except Exception:
            return input_sheet if input_sheet else "未知"

    @staticmethod
    def load_mapping_context(cfg, base_dir: str, config_path: str, domain: str = "LR_REAR"):
        mapping_ctx = MappingContext.from_config(
            cfg,
            base_dir=base_dir,
            config_path=config_path,
            domain=domain,
        )
        return mapping_ctx.io_mapping, mapping_ctx.config_enum
