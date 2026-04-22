#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DIDConfig 生成调度 service，通过 .runtime 委托根脚本与公共模块。"""

from __future__ import annotations

import os
import sys

from infra.excel.workbook import ExcelService
from services.config_constants import (
    DEFAULT_DID_CONFIG_FILENAME,
    OPTION_INPUT_EXCEL_CANDIDATES,
    OPTION_INPUTS,
    OPTION_OUTPUT_DIR,
    OPTION_OUTPUT_DIR_CANDIDATES,
    OPTION_OUTPUT_FILENAME_CANDIDATES,
    SECTION_CONFIG_ENUM,
    SECTION_DID_CONFIG,
    SECTION_DTC,
    SECTION_DTC_CONFIG_ENUM,
    SECTION_LR_REAR,
)
from infra.excel.header import find_header_row_and_col_indices
from infra.excel.workbook import merged_cell_value
from infra.filesystem import resolve_target_subdir
from utils.excel_io import norm_str
from utils.path_utils import resolve_runtime_path

from . import runtime as didconfig_generator_runtime


class DIDConfigGeneratorService:
    """接管 DIDConfig 主编排流程的 service。"""

    def run_pipeline(self, domain: str | None = None):
        base_dir = didconfig_generator_runtime.resolve_base_dir()
        gconfig = didconfig_generator_runtime.load_runtime(base_dir)
        if gconfig is None:
            return

        log_mgr, logger, old_stdout, old_stderr = didconfig_generator_runtime.init_logging(base_dir)
        progress_level = didconfig_generator_runtime.get_progress_level()
        try:
            cfg = gconfig.raw_config
            excel_rel_path = ""
            output_dir_rel = ""
            output_name = DEFAULT_DID_CONFIG_FILENAME

            if domain == SECTION_DTC:
                if not cfg.has_section(SECTION_DTC_CONFIG_ENUM):
                    msg = f"未配置 DID_Config 配置节 [{SECTION_DTC_CONFIG_ENUM}]"
                    print(f"错误: {msg}")
                    logger.error(msg)
                    raise ValueError(msg)
                inputs_raw = (cfg.get(SECTION_DTC_CONFIG_ENUM, OPTION_INPUTS, fallback="") or "").strip()
                excel_rel_path = inputs_raw.replace(";", "|").split("|")[0].strip()
                if not excel_rel_path:
                    msg = (
                        "未配置 DID_Config 配置表：未在 [DTC_CONFIG_ENUM] inputs 中找到有效的 Excel 路径"
                    )
                    print(f"错误: {msg}")
                    logger.error(msg)
                    raise ValueError(msg)
                if not cfg.has_section(SECTION_DTC):
                    msg = "未配置 DID_Config 配置节 [DTC]（需要 output_dir）"
                    print(f"错误: {msg}")
                    logger.error(msg)
                    raise ValueError(msg)
                for option_name in OPTION_OUTPUT_DIR_CANDIDATES:
                    output_dir_rel = cfg.get(SECTION_DTC, option_name, fallback=None) or ""
                    if output_dir_rel:
                        break
                if not output_dir_rel:
                    msg = f"未配置 DID_Config 输出目录：请在 [{SECTION_DTC}] 配置 {OPTION_OUTPUT_DIR}"
                    print(f"错误: {msg}")
                    logger.error(msg)
                    raise ValueError(msg)
                output_name = (
                    gconfig.get_fixed("didconfig_output_filename")
                    or next(
                        (
                            item_value
                            for option_name in OPTION_OUTPUT_FILENAME_CANDIDATES
                            if (item_value := cfg.get(SECTION_DTC, option_name, fallback=None))
                        ),
                        DEFAULT_DID_CONFIG_FILENAME,
                    )
                )
            elif domain == SECTION_LR_REAR:
                excel_rel_path = ""
                if cfg.has_section(SECTION_CONFIG_ENUM):
                    inputs_raw = (cfg.get(SECTION_CONFIG_ENUM, OPTION_INPUTS, fallback="") or "").strip()
                    excel_rel_path = inputs_raw.replace(";", "|").split("|")[0].strip()
                if not excel_rel_path and cfg.has_section(SECTION_DID_CONFIG):
                    for option_name in OPTION_INPUT_EXCEL_CANDIDATES:
                        excel_rel_path = cfg.get(SECTION_DID_CONFIG, option_name, fallback=None) or ""
                        if excel_rel_path:
                            break
                if not excel_rel_path:
                    msg = (
                        "未配置 DID_Config 配置表：请在 [CONFIG_ENUM].inputs 或 [DID_CONFIG].input_excel 配置有效的 Excel 路径"
                    )
                    print(f"错误: {msg}")
                    logger.error(msg)
                    raise ValueError(msg)
                if not cfg.has_section(SECTION_LR_REAR):
                    msg = f"未配置 DID_Config 相关节 [{SECTION_LR_REAR}]（需要 output_dir）"
                    print(f"错误: {msg}")
                    logger.error(msg)
                    raise ValueError(msg)
                for option_name in OPTION_OUTPUT_DIR_CANDIDATES:
                    output_dir_rel = cfg.get(SECTION_LR_REAR, option_name, fallback=None) or ""
                    if output_dir_rel:
                        break
                if not output_dir_rel:
                    msg = f"未配置 DID_Config 输出目录：请在 [{SECTION_LR_REAR}] 配置 {OPTION_OUTPUT_DIR}"
                    print(f"错误: {msg}")
                    logger.error(msg)
                    raise ValueError(msg)
                output_name = gconfig.get_fixed("didconfig_output_filename") or DEFAULT_DID_CONFIG_FILENAME
                if cfg.has_section(SECTION_DID_CONFIG):
                    for option_name in OPTION_OUTPUT_FILENAME_CANDIDATES:
                        output_filename_value = cfg.get(SECTION_DID_CONFIG, option_name, fallback=None)
                        if output_filename_value:
                            output_name = output_filename_value
                            break
            else:
                if not cfg.has_section(SECTION_DID_CONFIG):
                    msg = f"未配置 DID_Config 配置节 [{SECTION_DID_CONFIG}]"
                    print(f"错误: {msg}")
                    logger.error(msg)
                    # 抛异常，交由 TaskService 决定是“跳过”还是失败，避免前端误认为已生成
                    raise ValueError(msg)

                for option_name in OPTION_INPUT_EXCEL_CANDIDATES:
                    excel_rel_path = cfg.get(SECTION_DID_CONFIG, option_name, fallback=None) or ""
                    if excel_rel_path:
                        break
                if not excel_rel_path:
                    msg = f"未配置 DID_Config 配置表：配置文件中未找到 {SECTION_DID_CONFIG}.input_excel 或 {SECTION_DID_CONFIG}.Input_Excel"
                    print(f"错误: {msg}")
                    logger.error(msg)
                    # 抛异常以便上层按“未配置时跳过”处理，而不是静默 return
                    raise ValueError(msg)

                output_name = (
                    gconfig.get_fixed("didconfig_output_filename")
                    or next(
                        (
                            item_value
                            for option_name in OPTION_OUTPUT_FILENAME_CANDIDATES
                            if (item_value := cfg.get(SECTION_DID_CONFIG, option_name, fallback=None))
                        ),
                        DEFAULT_DID_CONFIG_FILENAME,
                    )
                )
                for option_name in OPTION_OUTPUT_DIR_CANDIDATES:
                    output_dir_rel = cfg.get(SECTION_DID_CONFIG, option_name, fallback=None) or ""
                    if output_dir_rel:
                        break
                if not output_dir_rel:
                    msg = f"配置文件中未找到 {SECTION_DID_CONFIG}.output_dir 或 {SECTION_DID_CONFIG}.Output_Dir"
                    print(f"错误: {msg}")
                    logger.error(msg)
                    raise ValueError(msg)

            config_dir = gconfig.config_dir
            excel_path = resolve_runtime_path(config_dir, excel_rel_path)
            raw_output_dir = resolve_runtime_path(config_dir, output_dir_rel)

            # 自动寻找或创建 Configuration 文件夹（与 DIDInfo、UART 等模块一致）
            try:
                output_dir = resolve_target_subdir(base_dir, raw_output_dir, "Configuration")
            except Exception as error:
                logger.error(f"无法定位输出目录: {error}")
                return
            output_path = os.path.join(output_dir, output_name)

            if not os.path.exists(excel_path):
                print(f"错误: 找不到 Excel 文件 {excel_path}")
                return

            try:
                wb = ExcelService.open_workbook(excel_path, data_only=True, read_only=False)
            except Exception as error:
                raise ValueError(str(error))

            excel_name = os.path.basename(excel_path)
            output_content: list[str] = []

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                logger.log(progress_level, f"解析 Excel 文件: {excel_name} sheet={sheet_name}")
                header_row, cols, missing = find_header_row_and_col_indices(
                    ws,
                    {
                        "name": ["name", "field_subdataname", "subdataname"],
                        "byte": ["byte", "field_byteposition", "byteposition"],
                        "bit": ["bit", "field_bitposition", "bitposition"],
                    },
                    max_scan_rows=30,
                )
                if header_row < 0 or missing:
                    print(f"错误: Excel={excel_name} sheet='{sheet_name}' 缺少必需列: {', '.join(missing)}，跳过该 sheet。")
                    continue

                parsed_rows: list[tuple[int, str, int, str]] = []
                for row_index in range(header_row + 1, ws.max_row + 1):
                    name_v = merged_cell_value(ws, row_index, cols["name"])
                    byte_v = merged_cell_value(ws, row_index, cols["byte"])
                    bit_v = merged_cell_value(ws, row_index, cols["bit"])

                    name_s = norm_str(name_v)
                    byte_s = norm_str(byte_v)
                    bit_s = norm_str(bit_v)

                    if not name_s and not byte_s and not bit_s:
                        continue

                    shown_name = name_s if name_s else "<空>"
                    if not byte_s and not bit_s:
                        print(f"错误: Excel={excel_name} sheet='{sheet_name}' 行 {row_index} Name='{shown_name}' Byte/Bit 均为空，跳过该行。")
                        continue
                    if not byte_s:
                        print(f"错误: Excel={excel_name} sheet='{sheet_name}' 行 {row_index} Name='{shown_name}' Byte 为空，跳过该行。")
                        continue
                    if not bit_s:
                        print(f"错误: Excel={excel_name} sheet='{sheet_name}' 行 {row_index} Name='{shown_name}' Bit 为空，跳过该行。")
                        continue
                    if not name_s:
                        print(f"错误: Excel={excel_name} sheet='{sheet_name}' 行 {row_index} Name 为空（Byte={byte_s}, Bit={bit_s}），跳过该行。")
                        continue

                    try:
                        byte_int = int(str(byte_v).strip())
                    except Exception:
                        print(f"错误: Excel={excel_name} sheet='{sheet_name}' 行 {row_index} Name='{shown_name}' Byte 无法解析为整数: '{byte_s}'，跳过该行。")
                        continue

                    parsed_rows.append((row_index, name_s, byte_int, bit_s))

                if not parsed_rows:
                    continue

                did_id = sheet_name if sheet_name.startswith("0x") else f"0x{sheet_name}"
                output_content.append(f"[{did_id}]")
                max_byte = max(
                    (
                        byte_position
                        for (excel_row, name, byte_position, bit_raw) in parsed_rows
                    ),
                    default=None,
                )
                did_length = (max_byte + 1) if isinstance(max_byte, int) else 0
                output_content.append(f"DIDLength:{did_length};//DID数据长度BYTE")

                for excel_row, name, byte, bit_raw in parsed_rows:
                    bit_s = norm_str(bit_raw).lower()
                    if bit_s == "all":
                        bit_pos = 0
                        field_len = 8
                    else:
                        try:
                            parts = bit_s.split("-")
                            if len(parts) == 1:
                                bit_pos = int(parts[0])
                                field_len = 1
                            elif len(parts) == 2:
                                start = int(parts[0])
                                end = int(parts[1])
                                bit_pos = start
                                field_len = max(1, end - start + 1)
                            else:
                                raise ValueError(f"Bit 格式不支持: '{bit_raw}'")
                        except Exception:
                            print(f"错误: Excel={excel_name} sheet='{sheet_name}' 行 {excel_row} Name='{name}' Bit 无法解析: '{bit_raw}'，跳过该行。")
                            continue

                    output_content.append(f"Field_subDataName:{name};//字段名称")
                    output_content.append(f"Field_BytePosition:{byte};//字段起始byte")
                    output_content.append(f"Field_bitPosition:{bit_pos};//字段起始bit;")
                    output_content.append(f"Field_FieldLength:{field_len};//字段长度，单位bit;")
                    output_content.append("Field_SortOrder:0;//排序方式0是motorola,1是intel")
                    output_content.append("Field_Data:0x01;//字段数据")
                    output_content.append("")

            with open(output_path, "w", encoding="utf-8") as output_text_file:
                output_text_file.write("\n".join(output_content))

            print(f"成功生成: {output_path}")
            logger.log(progress_level, f"成功生成: {output_path}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            log_mgr.clear()
