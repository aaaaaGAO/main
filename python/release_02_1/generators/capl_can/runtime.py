#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAN 入口运行期辅助。"""

from __future__ import annotations

import os

from core.generator_config import GeneratorConfig
from infra.excel.workbook import ExcelService
from services.config_constants import (
    DEFAULT_DOMAIN_LR_REAR,
    OPTION_CIN_INPUT_EXCEL_CANDIDATES,
    OPTION_INPUT_EXCEL,
    OPTION_OUTPUT_DIR,
    OPTION_UDS_ECU_QUALIFIER,
    SECTION_CENTRAL,
    SECTION_DTC,
    SECTION_LR_REAR,
)
from infra.filesystem.pathing import RuntimePathResolver
from utils.path_utils import list_excel_files, resolve_runtime_path, resolve_target_subdir


class CANEntrypointSupport:
    """收拢 CAN 入口阶段的路径、配置与辅助能力。"""

    @staticmethod
    def parse_bool(raw, default: bool = False) -> bool:
        if raw is None:
            return default
        normalized_text = str(raw).strip().lower()
        if normalized_text in ("1", "true", "yes", "on"):
            return True
        if normalized_text in ("0", "false", "no", "off"):
            return False
        return default

    @staticmethod
    def resolve_uds_qualifier(
        gconfig: GeneratorConfig,
        base_dir: str,
        domain: str,
        output_dir: str,
    ) -> str:
        # 优先使用各域在当前主配置文件中配置的 uds_ecu_qualifier，
        # 这样即使多个域共用同一个 output_dir 也不会互相覆盖。
        cfg_val = gconfig.get(domain, OPTION_UDS_ECU_QUALIFIER, fallback="").strip()
        if cfg_val:
            return cfg_val

        # 若未在配置中显式填写，则尝试从 uds.txt（或自定义 uds_output_filename）中读取。
        fixed = gconfig.fixed_config
        uds_filename = (fixed.get("uds_output_filename") or "uds.txt").strip() or "uds.txt"
        root = resolve_runtime_path(base_dir, output_dir)
        config_dir = (
            root if os.path.basename(root).lower() == "configuration" else os.path.join(root, "Configuration")
        )
        uds_path = os.path.join(config_dir, uds_filename)
        if os.path.isfile(uds_path):
            try:
                with open(uds_path, "r", encoding="utf-8", errors="replace") as uds_file:
                    for line in uds_file:
                        if line.strip().lower().startswith("ecu_qualifier="):
                            return line.split("=", 1)[1].strip()
            except Exception:
                pass
        return ""

    @staticmethod
    def build_runtime_paths(gconfig: GeneratorConfig, domain: str = DEFAULT_DOMAIN_LR_REAR) -> dict:
        base_dir = gconfig.base_dir

        if domain in (SECTION_CENTRAL, SECTION_DTC):
            # CENTRAL / DTC：定点读取本域 input_excel，不做跨节兜底。
            raw_path = gconfig.get_required_from_section(domain, OPTION_INPUT_EXCEL)
        elif domain == SECTION_LR_REAR:
            # LR_REAR：仅在本节内按显式键顺序解析，不读 [PATHS]。
            raw_path = (
                gconfig.get_from_section(domain, OPTION_INPUT_EXCEL, fallback="")
                or gconfig.get_from_section(domain, "Input_Excel", fallback="")
            ).strip()
            if not raw_path:
                raise ValueError(
                    f"未配置输入路径：请在 [{SECTION_LR_REAR}] 配置 input_excel（或 Input_Excel）"
                )
        else:
            raise ValueError(
                f"CAN 不支持 domain={domain!r}，请使用 {SECTION_LR_REAR!r}、{SECTION_CENTRAL!r} 或 {SECTION_DTC!r}"
            )
        if not raw_path:
            raise ValueError(f"未配置输入路径：请配置 [{domain}] 的 input_excel。")

        full_path = resolve_runtime_path(base_dir, raw_path)
        if os.path.isdir(full_path):
            excel_files = list_excel_files(full_path)
            if not excel_files:
                raise FileNotFoundError(f"文件夹内未找到 Excel 文件: {full_path}")
        else:
            excel_files = [full_path]

        mapping_excel_file = gconfig.get_fixed("mapping_excel") or gconfig.get_fixed(
            "unified_mapping_excel"
        )
        if not mapping_excel_file:
            raise ValueError(
                "未配置映射表路径，请在固定配置中配置 mapping_excel 或 unified_mapping_excel。"
            )
        if mapping_excel_file.startswith("./"):
            mapping_excel_file = mapping_excel_file[2:]
        mapping_excel_path = resolve_runtime_path(base_dir, mapping_excel_file)

        if domain in (SECTION_CENTRAL, SECTION_DTC):
            output_dir = gconfig.get_required_from_section(domain, OPTION_OUTPUT_DIR)
        elif domain == SECTION_LR_REAR:
            output_dir = (
                gconfig.get_from_section(domain, "Output_Dir_Can", fallback="")
                or gconfig.get_from_section(domain, "output_dir_can", fallback="")
                or gconfig.get_from_section(domain, "Output_Dir", fallback="")
                or gconfig.get_from_section(domain, OPTION_OUTPUT_DIR, fallback="")
            ).strip()
            if not output_dir:
                raise ValueError(
                    f"未配置 CAN 输出路径：请在 [{SECTION_LR_REAR}] 配置 output_dir 或 Output_Dir_Can / output_dir_can"
                )
        else:
            raise ValueError(
                f"CAN 不支持 domain={domain!r}，请使用 {SECTION_LR_REAR!r}、{SECTION_CENTRAL!r} 或 {SECTION_DTC!r}"
            )
        output_dir = (output_dir or "./output").strip()
        output_filename = gconfig.get_fixed("output_filename") or "generated_from_cases.can"
        cin_output_filename = (
            gconfig.get_fixed("cin_output_filename") or "generated_from_keyword.cin"
        )
        sheet_names_str = gconfig.get_fixed("mapping_sheets") or "HIL用例关键字说明,EM_CAN&Uart&LIN,EM_SOA,EM_总线测试专用,EM_设备&其他"
        sheet_names = [
            sheet_name.strip()
            for sheet_name in (sheet_names_str or "").split(",")
            if sheet_name.strip()
        ]

        testmode_dir = resolve_target_subdir(base_dir, output_dir, "TESTmode")
        testcases_dir = resolve_target_subdir(testmode_dir, ".", "Testcases")
        master_output_path = os.path.join(testmode_dir, output_filename)

        # 是否包含 .cin 由「是否选择了关键字集 Clib 配置表」决定，而非域类型
        cin_excel_path = CANEntrypointSupport.resolve_cin_excel_path(
            gconfig, base_dir, domain=domain
        )
        has_keyword_clib = bool((cin_excel_path or "").strip())

        secoc_qualifier = CANEntrypointSupport.resolve_uds_qualifier(
            gconfig, base_dir, domain, output_dir
        )

        return {
            "domain": domain,
            "excel_files": excel_files,
            "mapping_excel_path": mapping_excel_path,
            "sheet_names": sheet_names,
            "testcases_dir": testcases_dir,
            "master_output_path": master_output_path,
            "cin_output_filename": cin_output_filename,
            "has_keyword_clib": has_keyword_clib,
            "secoc_qualifier": secoc_qualifier,
        }

    @staticmethod
    def load_clib_names_from_excel(excel_path: str) -> set[str]:
        names: set[str] = set()
        if not excel_path or not os.path.exists(excel_path):
            return names
        try:
            wb = ExcelService.open_workbook(excel_path, data_only=True, read_only=False)
        except Exception:
            return names
        try:
            ws = wb["Clib_Matrix"] if "Clib_Matrix" in wb.sheetnames else wb[wb.sheetnames[0]]
            header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
            header_norm = [
                ("" if header_cell is None else str(header_cell).strip()).lower()
                for header_cell in header
            ]
            name_idx = None
            for header_index, header_text in enumerate(header_norm):
                if header_text == "name" or "name" in header_text:
                    name_idx = header_index
                    break
            if name_idx is None:
                name_idx = 1 if len(header_norm) > 1 else 0
            for row in ws.iter_rows(min_row=2, values_only=True):
                if name_idx < len(row):
                    name_value = ("" if row[name_idx] is None else str(row[name_idx]).strip()).lower()
                    if name_value:
                        names.add(name_value)
        finally:
            wb.close()
        return names

    @staticmethod
    def resolve_base_dir(base_dir: str | None = None) -> str:
        """解析工程根目录。"""
        return RuntimePathResolver.resolve_base_dir(__file__, base_dir)

    @staticmethod
    def resolve_config_path(base_dir: str, config_path: str | None = None) -> str:
        return RuntimePathResolver.resolve_config_path(base_dir, config_path)

    @staticmethod
    def load_generator_config(
        base_dir: str,
        config_path: str | None = None,
    ) -> GeneratorConfig:
        resolved_config_path = CANEntrypointSupport.resolve_config_path(base_dir, config_path)
        return GeneratorConfig(base_dir, config_path=resolved_config_path).load()

    @staticmethod
    def resolve_cin_excel_path(
        gconfig: GeneratorConfig,
        base_dir: str,
        *,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
    ) -> str:
        if domain not in (SECTION_CENTRAL, SECTION_DTC, SECTION_LR_REAR):
            raise ValueError(
                f"CAN 不支持 domain={domain!r}，请使用 {SECTION_LR_REAR!r}、{SECTION_CENTRAL!r} 或 {SECTION_DTC!r}"
            )
        cin_excel_path = ""
        for option_name in OPTION_CIN_INPUT_EXCEL_CANDIDATES:
            cin_excel_path = gconfig.get(domain, option_name, fallback="").strip()
            if cin_excel_path:
                break
        if cin_excel_path:
            cin_excel_path = resolve_runtime_path(base_dir, cin_excel_path)
        return cin_excel_path
