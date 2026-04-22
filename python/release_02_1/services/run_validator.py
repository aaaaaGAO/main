#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行前校验（Run Validator）

在用户点击「开始运行」后、真正执行生成前，对当前域的必填路径与可写性做前置校验，
避免跑到一半才报错。供 TaskOrchestrator 在 _run_generic_bundle 开头调用。
"""

from __future__ import annotations

import os
from typing import List, Tuple

from infra.filesystem import resolve_configured_path
from services.config_manager import ConfigManager
from services.config_constants import (
    DEFAULT_DOMAIN_LR_REAR,
    LABEL_CIN_CLIB_PATH_CHECK,
    LABEL_CIN_MISSING_DTC,
    LABEL_CIN_MISSING_LR,
    LABEL_DIDCONFIG_MISSING_LR,
    LABEL_DIDCONFIG_PATH_CHECK,
    LABEL_DTC_CIN_CLIB_PATH_CHECK,
    LABEL_DTC_DIDCONFIG_PATH_CHECK,
    LABEL_DTC_DIDINFO_INPUT_TABLE,
    LABEL_RESETDID_VALUE_CONFIG_TABLE,
    OPTION_CIN_INPUT_EXCEL,
    OPTION_DIDINFO_INPUTS,
    OPTION_INPUT_EXCEL,
    OPTION_INPUT_EXCEL_CANDIDATES,
    OPTION_INPUTS,
    OPTION_OUTPUT_DIR,
    OPTION_SRV_EXCEL,
    OPTION_SRV_EXCEL_CANDIDATES,
    OPTION_UART_EXCEL,
    OPTION_XML_INPUT_EXCEL,
    SECTION_CENTRAL,
    SECTION_CONFIG_ENUM,
    SECTION_DID_CONFIG,
    SECTION_DTC,
    SECTION_DTC_CONFIG_ENUM,
    SECTION_DTC_IOMAPPING,
    SECTION_IOMAPPING,
)


class RunValidator:
    """各域在真正生成前对必填项、文件存在与输出可写等做检查；`validate_for_domain` 为入口。"""

    DOMAIN_DISPLAY_NAMES = {
        DEFAULT_DOMAIN_LR_REAR: "左右后域",
        SECTION_CENTRAL: "中央域",
        SECTION_DTC: "DTC域",
    }

    @classmethod
    def domain_display_name(cls, domain: str) -> str:
        """将节名/域常量映射为展示用中文名。参数：domain。返回：中文或原串。"""
        return cls.DOMAIN_DISPLAY_NAMES.get(domain, domain)

    @classmethod
    def extract_first_path(cls, raw_value: str) -> str:
        """
        从「path|sheet」或分号复合串中取**第一段**作为物理路径。参数：raw_value — 配置里读出的原串。返回：路径文本。
        """
        text = (raw_value or "").strip()
        if not text:
            return ""
        return text.replace(";", "|").split("|")[0].strip()

    @classmethod
    def append_required_file_issue(
        cls,
        errors: List[str],
        *,
        domain: str,
        missing_labels: List[str],
        not_found_pairs: List[Tuple[str, str]],
    ) -> None:
        """
        向 `errors` 列表追加人可读缺项/文件不存在信息（不返回新列表）。参数见形参；返回：无。
        """
        domain_name = cls.domain_display_name(domain)
        if missing_labels:
            errors.append(
                f"【{domain_name}】必要输入文件未选择：{'、'.join(missing_labels)}。请先补齐后再运行。"
            )
        if not_found_pairs:
            details = "；".join(f"{label}（{file_path}）" for label, file_path in not_found_pairs)
            errors.append(f"【{domain_name}】必要输入文件不存在：{details}。请检查文件路径后再运行。")

    @staticmethod
    def check_required_path_configured(target_path: str, label: str) -> Tuple[bool, str]:
        """检查必填路径是否已配置。"""
        if target_path and target_path.strip():
            return True, ""
        return False, f"{label} 未配置。"

    @staticmethod
    def resolve_config_path(raw: str, base_dir: str) -> str:
        """将配置中的相对路径解析为绝对路径。
        参数：raw — 配置中的路径字符串；base_dir — 工程根目录。
        返回：规范化的绝对路径，空配置返回空串。
        """
        return resolve_configured_path(base_dir, raw)

    @staticmethod
    def check_output_dir_writable(output_dir: str) -> Tuple[bool, str]:
        """检查输出目录是否可写：若不存在则尝试创建；若存在则检查是否为目录且可写。
        参数：output_dir — 输出目录路径（应已为绝对路径）。
        返回：(是否通过, 错误信息)；通过时错误信息为空串。
        """
        if not output_dir or not output_dir.strip():
            return False, "未配置输出路径（output_dir）。"
        output_dir = output_dir.strip()
        if not os.path.isabs(output_dir):
            return False, "输出路径应为绝对路径或已相对于工程根解析。"
        if os.path.isfile(output_dir):
            return False, f"输出路径是文件而非目录：{output_dir}"
        try:
            os.makedirs(output_dir, exist_ok=True)
            # 简单可写检测：尝试在该目录创建临时文件
            test_file = os.path.join(output_dir, ".write_check_tmp")
            with open(test_file, "w") as temp_file:
                temp_file.write("")
            os.remove(test_file)
            return True, ""
        except PermissionError:
            return False, f"输出目录无写入权限：{output_dir}"
        except Exception as error:
            return False, f"输出目录不可用：{output_dir}（{error}）"

    @staticmethod
    def check_path_exists(target_path: str, label: str) -> Tuple[bool, str]:
        """检查路径是否存在（文件或目录）。未配置路径时视为通过。
        参数：target_path — 待检查路径；label — 用于错误信息的标签。
        返回：(是否通过, 错误信息)。
        """
        if not target_path or not target_path.strip():
            return True, ""  # 未配置则跳过
        target_path = target_path.strip()
        if os.path.isfile(target_path) or os.path.isdir(target_path):
            return True, ""
        return False, f"{label} 不存在：{target_path}"

    @staticmethod
    def check_path_kind(target_path: str, *, expect: str, label: str) -> Tuple[bool, str]:
        """检查路径类型：expect=file|dir|either。未配置路径时视为通过。"""
        if not target_path or not target_path.strip():
            return True, ""
        normalized_expect = (expect or "either").strip().lower()
        if normalized_expect == "file":
            return (True, "") if os.path.isfile(target_path) else (False, f"{label} 需要是文件：{target_path}")
        if normalized_expect == "dir":
            return (True, "") if os.path.isdir(target_path) else (False, f"{label} 需要是文件夹：{target_path}")
        if os.path.isfile(target_path) or os.path.isdir(target_path):
            return True, ""
        return False, f"{label} 不存在：{target_path}"

    @classmethod
    def validate_for_domain(
        cls,
        domain: str,
        base_dir: str,
        config_path: str,
        config_manager: "ConfigManager",
        *,
        run_can: bool = False,
        run_xml: bool = False,
        run_did: bool = False,
        run_cin: bool = False,
        run_soa: bool = False,
    ) -> Tuple[bool, List[str]]:
        """按域校验运行前必填项：输出目录必填且可写；输入路径（若已配置）须存在。
        参数：domain — 业务域（LR_REAR / CENTRAL / DTC）；base_dir — 工程根目录；config_path — 配置文件路径（保留接口）；config_manager — 已初始化的 ConfigManager，用于 _reload() 读配置。
        返回：(是否通过, 错误信息列表)。
        """
        errors: List[str] = []
        config = config_manager.load_config()

        if not config.has_section(domain):
            errors.append(f"配置中缺少 [{domain}] 节。")
            return False, errors

        section = dict(config.items(domain))
        output_dir_raw = section.get(OPTION_OUTPUT_DIR, "").strip()
        output_dir = cls.resolve_config_path(output_dir_raw, base_dir) if output_dir_raw else ""
        missing_required_labels: List[str] = []
        not_found_required_pairs: List[Tuple[str, str]] = []

        # 1. 输出目录必填且可写
        if not output_dir:
            errors.append(f"[{domain}] 未配置 {OPTION_OUTPUT_DIR}（输出路径）。")
        else:
            is_valid, validation_message = cls.check_output_dir_writable(output_dir)
            if not is_valid:
                errors.append(validation_message)

        # 2. 输入路径（用例/Excel）：若已配置则必须存在
        input_excel_raw = section.get(OPTION_INPUT_EXCEL, "").strip()
        require_input_excel = run_can or run_xml
        if require_input_excel and not input_excel_raw:
            missing_required_labels.append("主输入表(input_excel)")
        if input_excel_raw:
            input_path = cls.resolve_config_path(input_excel_raw, base_dir)
            is_valid, validation_message = cls.check_path_exists(input_path, f"[{domain}] 输入用例路径")
            if not is_valid:
                if require_input_excel:
                    not_found_required_pairs.append(("主输入表(input_excel)", input_path))
                else:
                    errors.append(validation_message)
            else:
                is_valid, validation_message = cls.check_path_kind(
                    input_path,
                    expect="either",
                    label=f"[{domain}] 输入用例路径",
                )
                if not is_valid:
                    errors.append(validation_message)

        # 3. LR_REAR 额外校验：DID/CIN/IO 若配置了则存在
        if domain == DEFAULT_DOMAIN_LR_REAR:
            if run_cin:
                cin_required = section.get(OPTION_CIN_INPUT_EXCEL, "").strip()
                if not cin_required:
                    missing_required_labels.append(LABEL_CIN_MISSING_LR)

            if run_did:
                did_excel_raw = ""
                if config.has_section(SECTION_CONFIG_ENUM):
                    enum_inputs = (config.get(SECTION_CONFIG_ENUM, OPTION_INPUTS, fallback="") or "").strip()
                    if enum_inputs:
                        did_excel_raw = cls.extract_first_path(enum_inputs)
                if not did_excel_raw and config.has_section(SECTION_DID_CONFIG):
                    for option_name in OPTION_INPUT_EXCEL_CANDIDATES:
                        did_excel_raw = (config.get(SECTION_DID_CONFIG, option_name, fallback="") or "").strip()
                        if did_excel_raw:
                            break
                if not did_excel_raw:
                    missing_required_labels.append(LABEL_DIDCONFIG_MISSING_LR)
                else:
                    resolved_path = cls.resolve_config_path(did_excel_raw, base_dir)
                    is_valid, validation_message = cls.check_path_exists(resolved_path, LABEL_DIDCONFIG_PATH_CHECK)
                    if not is_valid:
                        errors.append(validation_message)
            if config.has_section(SECTION_IOMAPPING):
                io_inputs = (config.get(SECTION_IOMAPPING, OPTION_INPUTS, fallback="") or "").strip()
                if io_inputs:
                    # 可能为多个路径用 | 或 ; 分隔，取第一个
                    first_input_path = io_inputs.replace(";", "|").split("|")[0].strip()
                    if first_input_path:
                        resolved_path = cls.resolve_config_path(first_input_path, base_dir)
                        is_valid, validation_message = cls.check_path_exists(resolved_path, "IO_Mapping 配置表")
                        if not is_valid:
                            errors.append(validation_message)
            didinfo_raw = section.get(OPTION_DIDINFO_INPUTS, "").strip()
            if didinfo_raw:
                first_didinfo_path = didinfo_raw.split("|")[0].strip() if "|" in didinfo_raw else didinfo_raw
                if first_didinfo_path:
                    resolved_path = cls.resolve_config_path(first_didinfo_path, base_dir)
                    is_valid, validation_message = cls.check_path_exists(
                        resolved_path, LABEL_RESETDID_VALUE_CONFIG_TABLE
                    )
                    if not is_valid:
                        errors.append(validation_message)
            cin_excel = section.get(OPTION_CIN_INPUT_EXCEL, "").strip()
            if cin_excel:
                resolved_path = cls.resolve_config_path(cin_excel, base_dir)
                is_valid, validation_message = cls.check_path_exists(resolved_path, LABEL_CIN_CLIB_PATH_CHECK)
                if not is_valid:
                    if run_cin:
                        not_found_required_pairs.append((LABEL_CIN_MISSING_LR, resolved_path))
                    else:
                        errors.append(validation_message)
            srv_excel_raw = ""
            for option_name in (OPTION_SRV_EXCEL, *OPTION_SRV_EXCEL_CANDIDATES):
                srv_excel_raw = section.get(option_name, "").strip()
                if srv_excel_raw:
                    break
            if run_soa and not srv_excel_raw:
                missing_required_labels.append("服务通信矩阵(srv_excel)")
            if srv_excel_raw:
                resolved_path = cls.resolve_config_path(srv_excel_raw, base_dir)
                is_valid, validation_message = cls.check_path_exists(resolved_path, "[LR_REAR] 服务通信矩阵")
                if not is_valid:
                    if run_soa:
                        not_found_required_pairs.append(("服务通信矩阵(srv_excel)", resolved_path))
                    else:
                        errors.append(validation_message)

        # 4. CENTRAL 域额外校验：补齐必填项（9-2）与类型校验
        if domain == SECTION_CENTRAL:
            uart_excel_raw = section.get(OPTION_UART_EXCEL, "").strip()
            if uart_excel_raw:
                resolved_path = cls.resolve_config_path(uart_excel_raw, base_dir)
                is_valid, validation_message = cls.check_path_exists(resolved_path, "[CENTRAL] UART 通信矩阵 Excel")
                if not is_valid:
                    errors.append(validation_message)
                else:
                    is_valid, validation_message = cls.check_path_kind(
                        resolved_path,
                        expect="file",
                        label="[CENTRAL] UART 通信矩阵 Excel",
                    )
                    if not is_valid:
                        errors.append(validation_message)

            # CENTRAL: XML 输入优先 xml_input_excel；未配置时回退 input_excel（与界面“测试用例/测试文件夹导入”一致）。
            xml_input_raw = section.get(OPTION_XML_INPUT_EXCEL, "").strip()
            if not xml_input_raw:
                xml_input_raw = section.get(OPTION_INPUT_EXCEL, "").strip()
            if run_xml and xml_input_raw:
                resolved_path = cls.resolve_config_path(xml_input_raw, base_dir)
                is_valid, validation_message = cls.check_path_exists(resolved_path, "[CENTRAL] XML 输入 Excel")
                if not is_valid:
                    if run_xml:
                        not_found_required_pairs.append(("XML输入表(xml_input_excel)", resolved_path))
                    else:
                        errors.append(validation_message)
                else:
                    is_valid, validation_message = cls.check_path_kind(
                        resolved_path,
                        expect="either",
                        label="[CENTRAL] XML 输入 Excel",
                    )
                    if not is_valid:
                        errors.append(validation_message)

            srv_excel_raw = ""
            for option_name in (OPTION_SRV_EXCEL, *OPTION_SRV_EXCEL_CANDIDATES):
                srv_excel_raw = section.get(option_name, "").strip()
                if srv_excel_raw:
                    break
            if run_soa and not srv_excel_raw:
                missing_required_labels.append("服务通信矩阵(srv_excel)")
            if srv_excel_raw:
                resolved_path = cls.resolve_config_path(srv_excel_raw, base_dir)
                is_valid, validation_message = cls.check_path_exists(resolved_path, "[CENTRAL] 服务通信矩阵")
                if not is_valid:
                    if run_soa:
                        not_found_required_pairs.append(("服务通信矩阵(srv_excel)", resolved_path))
                    else:
                        errors.append(validation_message)
                else:
                    is_valid, validation_message = cls.check_path_kind(
                        resolved_path,
                        expect="file",
                        label="[CENTRAL] 服务通信矩阵",
                    )
                    if not is_valid:
                        errors.append(validation_message)

        # 5. DTC 域：DTC 专用 IO/DID 节（若存在）
        if domain == SECTION_DTC:
            if run_cin:
                cin_required = section.get(OPTION_CIN_INPUT_EXCEL, "").strip()
                if not cin_required:
                    missing_required_labels.append(LABEL_CIN_MISSING_DTC)

            if config.has_section(SECTION_DTC_IOMAPPING):
                io_inputs = (config.get(SECTION_DTC_IOMAPPING, OPTION_INPUTS, fallback="") or "").strip()
                if io_inputs:
                    first_input_path = io_inputs.replace(";", "|").split("|")[0].strip()
                    if first_input_path:
                        resolved_path = cls.resolve_config_path(first_input_path, base_dir)
                        is_valid, validation_message = cls.check_path_exists(resolved_path, "DTC IO_Mapping 配置表")
                        if not is_valid:
                            errors.append(validation_message)
            if config.has_section(SECTION_DTC_CONFIG_ENUM):
                did_config_inputs = (config.get(SECTION_DTC_CONFIG_ENUM, OPTION_INPUTS, fallback="") or "").strip()
                if did_config_inputs:
                    first_input_path = did_config_inputs.replace(";", "|").split("|")[0].strip()
                    if first_input_path:
                        resolved_path = cls.resolve_config_path(first_input_path, base_dir)
                        is_valid, validation_message = cls.check_path_exists(
                            resolved_path, LABEL_DTC_DIDCONFIG_PATH_CHECK
                        )
                        if not is_valid:
                            errors.append(validation_message)

            didinfo_raw = section.get(OPTION_DIDINFO_INPUTS, "").strip()
            if didinfo_raw:
                first_didinfo_path = cls.extract_first_path(didinfo_raw)
                if first_didinfo_path:
                    resolved_path = cls.resolve_config_path(first_didinfo_path, base_dir)
                    is_valid, validation_message = cls.check_path_exists(
                        resolved_path, LABEL_DTC_DIDINFO_INPUT_TABLE
                    )
                    if not is_valid:
                        errors.append(validation_message)
            cin_excel = section.get(OPTION_CIN_INPUT_EXCEL, "").strip()
            if cin_excel:
                resolved_path = cls.resolve_config_path(cin_excel, base_dir)
                is_valid, validation_message = cls.check_path_exists(
                    resolved_path, LABEL_DTC_CIN_CLIB_PATH_CHECK
                )
                if not is_valid:
                    if run_cin:
                        not_found_required_pairs.append((LABEL_CIN_MISSING_DTC, resolved_path))
                    else:
                        errors.append(validation_message)
            srv_excel_raw = ""
            for option_name in (OPTION_SRV_EXCEL, *OPTION_SRV_EXCEL_CANDIDATES):
                srv_excel_raw = section.get(option_name, "").strip()
                if srv_excel_raw:
                    break
            if run_soa and not srv_excel_raw:
                missing_required_labels.append("服务通信矩阵(srv_excel)")
            if srv_excel_raw:
                resolved_path = cls.resolve_config_path(srv_excel_raw, base_dir)
                is_valid, validation_message = cls.check_path_exists(
                    resolved_path, "[DTC] 服务通信矩阵"
                )
                if not is_valid:
                    if run_soa:
                        not_found_required_pairs.append(("服务通信矩阵(srv_excel)", resolved_path))
                    else:
                        errors.append(validation_message)

        cls.append_required_file_issue(
            errors,
            domain=domain,
            missing_labels=missing_required_labels,
            not_found_pairs=not_found_required_pairs,
        )

        return (len(errors) == 0, errors)


# Backward-compatible module-level alias
validate_for_domain = RunValidator.validate_for_domain
