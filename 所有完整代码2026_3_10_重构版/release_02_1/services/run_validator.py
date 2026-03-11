#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行前校验（Run Validator）

在用户点击「开始运行」后、真正执行生成前，对当前域的必填路径与可写性做前置校验，
避免跑到一半才报错。供 TaskOrchestrator 在 _run_generic_bundle 开头调用。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from services.config_manager import ConfigManager


def _resolve_path(raw: str, base_dir: str) -> str:
    """将配置中的相对路径解析为绝对路径。
    参数：raw — 配置中的路径字符串；base_dir — 工程根目录。
    返回：规范化的绝对路径，空配置返回空串。
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    path = raw.replace("/", os.sep)
    if not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    return os.path.normpath(path)


def _check_output_dir_writable(out_dir: str) -> Tuple[bool, str]:
    """检查输出目录是否可写：若不存在则尝试创建；若存在则检查是否为目录且可写。
    参数：out_dir — 输出目录路径（应已为绝对路径）。
    返回：(是否通过, 错误信息)；通过时错误信息为空串。
    """
    if not out_dir or not out_dir.strip():
        return False, "未配置输出路径（output_dir）。"
    out_dir = out_dir.strip()
    if not os.path.isabs(out_dir):
        return False, "输出路径应为绝对路径或已相对于工程根解析。"
    if os.path.isfile(out_dir):
        return False, f"输出路径是文件而非目录：{out_dir}"
    try:
        os.makedirs(out_dir, exist_ok=True)
        # 简单可写检测：尝试在该目录创建临时文件
        test_file = os.path.join(out_dir, ".write_check_tmp")
        with open(test_file, "w") as f:
            f.write("")
        os.remove(test_file)
        return True, ""
    except PermissionError:
        return False, f"输出目录无写入权限：{out_dir}"
    except Exception as e:
        return False, f"输出目录不可用：{out_dir}（{e}）"


def _check_path_exists(path: str, label: str) -> Tuple[bool, str]:
    """检查路径是否存在（文件或目录）。未配置路径时视为通过。
    参数：path — 待检查路径；label — 用于错误信息的标签。
    返回：(是否通过, 错误信息)。
    """
    if not path or not path.strip():
        return True, ""  # 未配置则跳过
    path = path.strip()
    if os.path.isfile(path) or os.path.isdir(path):
        return True, ""
    return False, f"{label} 不存在：{path}"


def validate_for_domain(
    domain: str,
    base_dir: str,
    config_path: str,
    config_manager: "ConfigManager",
) -> Tuple[bool, List[str]]:
    """按域校验运行前必填项：输出目录必填且可写；输入路径（若已配置）须存在。
    参数：domain — 业务域（LR_REAR / CENTRAL / DTC）；base_dir — 工程根目录；config_path — 配置文件路径（保留接口）；config_manager — 已初始化的 ConfigManager，用于 _reload() 读配置。
    返回：(是否通过, 错误信息列表)。
    """
    errors: List[str] = []
    config = config_manager._reload()

    if not config.has_section(domain):
        errors.append(f"配置中缺少 [{domain}] 节。")
        return False, errors

    section = dict(config.items(domain))
    output_dir_raw = section.get("output_dir", "").strip()
    output_dir = _resolve_path(output_dir_raw, base_dir) if output_dir_raw else ""

    # 1. 输出目录必填且可写
    if not output_dir:
        errors.append(f"[{domain}] 未配置 output_dir（输出路径）。")
    else:
        ok, msg = _check_output_dir_writable(output_dir)
        if not ok:
            errors.append(msg)

    # 2. 输入路径（用例/Excel）：若已配置则必须存在
    input_excel_raw = section.get("input_excel", "").strip()
    if input_excel_raw:
        input_path = _resolve_path(input_excel_raw, base_dir)
        ok, msg = _check_path_exists(input_path, f"[{domain}] 输入用例路径")
        if not ok:
            errors.append(msg)

    # 3. LR_REAR 额外校验：DID/CIN/IO 若配置了则存在
    if domain == "LR_REAR":
        if config.has_section("DID_CONFIG"):
            did_excel = (config.get("DID_CONFIG", "input_excel", fallback="") or "").strip()
            if did_excel:
                p = _resolve_path(did_excel, base_dir)
                ok, msg = _check_path_exists(p, "DID_Config 配置表")
                if not ok:
                    errors.append(msg)
        if config.has_section("IOMAPPING"):
            io_inputs = (config.get("IOMAPPING", "inputs", fallback="") or "").strip()
            if io_inputs:
                # 可能为多个路径用 | 或 ; 分隔，取第一个
                first = io_inputs.replace(";", "|").split("|")[0].strip()
                if first:
                    p = _resolve_path(first, base_dir)
                    ok, msg = _check_path_exists(p, "IO_Mapping 配置表")
                    if not ok:
                        errors.append(msg)
        didinfo_raw = section.get("didinfo_inputs", "").strip()
        if didinfo_raw:
            first = didinfo_raw.split("|")[0].strip() if "|" in didinfo_raw else didinfo_raw
            if first:
                p = _resolve_path(first, base_dir)
                ok, msg = _check_path_exists(p, "ResetDid_Value 配置表")
                if not ok:
                    errors.append(msg)
        cin_excel = section.get("cin_input_excel", "").strip()
        if cin_excel:
            p = _resolve_path(cin_excel, base_dir)
            ok, msg = _check_path_exists(p, "关键字集 Clib 配置表")
            if not ok:
                errors.append(msg)

    # 4. DTC 域：DTC 专用 IO/DID 节（若存在）
    if domain == "DTC":
        if config.has_section("DTC_IOMAPPING"):
            io_inputs = (config.get("DTC_IOMAPPING", "inputs", fallback="") or "").strip()
            if io_inputs:
                first = io_inputs.replace(";", "|").split("|")[0].strip()
                if first:
                    p = _resolve_path(first, base_dir)
                    ok, msg = _check_path_exists(p, "DTC IO_Mapping 配置表")
                    if not ok:
                        errors.append(msg)
        if config.has_section("DTC_CONFIG_ENUM"):
            didcfg = (config.get("DTC_CONFIG_ENUM", "inputs", fallback="") or "").strip()
            if didcfg:
                first = didcfg.replace(";", "|").split("|")[0].strip()
                if first:
                    p = _resolve_path(first, base_dir)
                    ok, msg = _check_path_exists(p, "DTC DID_Config 配置表")
                    if not ok:
                        errors.append(msg)

    return (len(errors) == 0, errors)
