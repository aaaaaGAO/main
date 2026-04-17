#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XML 生成调度 service。不再依赖 XMLLegacyHooks，通过 .runtime 委托根脚本实现。"""

from __future__ import annotations

import os
import sys
import traceback

from core.common.generation_summary import build_ungenerated_reason
from services.config_constants import DEFAULT_DOMAIN_LR_REAR

from . import runtime as xml_generator_runtime


class XMLGeneratorService:
    """接管 XML 旧版主编排流程的 service。"""

    @staticmethod
    def build_ungenerated_reason(stats: dict) -> str:
        return build_ungenerated_reason(stats, generated_label="XML文件")

    def run_legacy_pipeline(
        self,
        *,
        config_path: str | None = None,
        base_dir: str | None = None,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
    ):
        resolved_base_dir = xml_generator_runtime.resolve_base_dir(base_dir)
        runtime = xml_generator_runtime.load_runtime_config(config_path, resolved_base_dir, domain)
        excel_path = runtime["excel_path"]
        output_xml_path = runtime["output_xml_path"]
        allowed_levels = runtime["allowed_levels"]
        allowed_platforms = runtime["allowed_platforms"]
        allowed_models = runtime["allowed_models"]
        allowed_target_versions = runtime.get("allowed_target_versions")
        selected_filter = runtime["selected_filter"]
        logger, old_stdout, old_stderr = xml_generator_runtime.init_runtime_logging(resolved_base_dir)
        progress_level = xml_generator_runtime.get_progress_level()

        try:
            try:
                excel_files = xml_generator_runtime.find_excel_files(excel_path)
                if not excel_files:
                    print(f"警告: 在路径 '{excel_path}' 中未找到任何 Excel 文件")
                    return
                if selected_filter is not None:
                    excel_files = [
                        excel_file
                        for excel_file in excel_files
                        if os.path.basename(excel_file).lower() in selected_filter
                    ]
                    if not excel_files:
                        expected = ", ".join(sorted(selected_filter.keys()))
                        print(
                            f"警告: 勾选的 sheet 对应的 Excel 在路径中未找到，请确认所选 sheet 属于当前输入路径下的文件。"
                            f" 当前输入路径: {excel_path}；勾选期望的文件名（任选其一需存在）: {expected}"
                        )
                        return
            except Exception as error:
                print(f"错误: 无法查找 Excel 文件: {error}")
                traceback.print_exc()
                return

            excel_files_dict = {}
            seen_case_ids = {}
            excel_stats_map = {}
            ungenerated_files = []

            try:
                for excel_index, excel_file in enumerate(excel_files):
                    if logger and excel_index > 0:
                        logger.info("")
                    if logger:
                        logger.log(
                            progress_level,
                            f"解析 Excel 文件: {os.path.basename(excel_file)}",
                        )
                    else:
                        print(f"\n解析 Excel 文件: {os.path.basename(excel_file)}")

                    try:
                        excel_label = os.path.relpath(excel_file, start=resolved_base_dir)
                    except Exception:
                        excel_label = os.path.basename(excel_file)

                    sheet_testcases_dict, stats = xml_generator_runtime.parse_testcases_from_excel(
                        excel_file,
                        allowed_levels=allowed_levels,
                        allowed_platforms=allowed_platforms,
                        allowed_models=allowed_models,
                        allowed_target_versions=allowed_target_versions,
                        seen_case_ids=seen_case_ids,
                        excel_label=excel_label,
                        allowed_sheet_names=None,
                        selected_filter=selected_filter,
                    )
                    excel_stats_map[excel_file] = stats

                    if sheet_testcases_dict:
                        sheet_groups = xml_generator_runtime.group_testcases_by_sheet_and_group(sheet_testcases_dict)
                        excel_files_dict[excel_file] = sheet_groups
                    else:
                        print(f"  警告: 文件 '{os.path.basename(excel_file)}' 中未找到任何测试用例")
                    try:
                        print("")
                    except Exception:
                        pass
            except Exception as error:
                print(f"错误: 无法解析 Excel 文件: {error}")
                traceback.print_exc()
                return

            if not excel_files_dict:
                print("警告: 未找到任何测试用例")
                return

            print("\n生成 XML 文件...")
            try:
                xml_content = xml_generator_runtime.generate_xml_content(excel_files_dict)
                xml_content = xml_content.replace("\r\n", "\n").replace("\n", "\r\n")
                with open(output_xml_path, "w", encoding="utf-8") as output_file:
                    output_file.write(xml_content)
                print("文件已使用 UTF-8 编码保存")
                print(f"XML 文件已生成: {output_xml_path}")
                print("=" * 60)
                print(f"\n所有文件生成完成！XML 文件已生成: {output_xml_path}")
                if logger:
                    logger.log(
                        progress_level,
                        f"所有文件生成完成！XML 文件已生成: {output_xml_path}",
                    )

                if os.path.isdir(excel_path):
                    print("\n[主程序] 目录模式 XML 生成汇总：")
                    if logger:
                        logger.log(progress_level, "目录模式 XML 生成汇总开始")

                    for excel_file in excel_files:
                        excel_name_only = os.path.basename(excel_file)
                        if excel_file in excel_files_dict:
                            total_testcases = sum(
                                len(tcs) for tcs in excel_files_dict[excel_file].values()
                            )
                            msg = f"  Excel={excel_name_only} → 已生成 XML（包含 {total_testcases} 个测试用例）"
                        else:
                            stats = excel_stats_map.get(excel_file, {})
                            reason_str = self.build_ungenerated_reason(stats)
                            msg = f"  Excel={excel_name_only} → 未生成 XML，原因：{reason_str}"
                            ungenerated_files.append((excel_name_only, reason_str))
                        print(msg)
                        if logger:
                            logger.log(progress_level, msg)

                    print("")
                    if logger:
                        logger.log(progress_level, "目录模式 XML 生成汇总结束")

                if ungenerated_files:
                    print("\n[主程序] 未生成 XML 文件的 Excel 汇总：")
                    if logger:
                        logger.log(progress_level, "未生成 XML 文件的 Excel 汇总开始")
                    for excel_name, reason in ungenerated_files:
                        msg = f"  Excel={excel_name} → 未生成 XML，原因：{reason}"
                        print(msg)
                        if logger:
                            logger.log(progress_level, msg)
                    print("")
                    if logger:
                        logger.log(progress_level, "未生成 XML 文件的 Excel 汇总结束")
            except Exception as error:
                error_msg = f"错误: 无法生成 XML 文件: {error}"
                print(error_msg)
                if logger:
                    try:
                        logger.error("无法生成 XML 文件: %s", error, exc_info=True)
                    except UnicodeEncodeError:
                        safe_msg = str(error).encode("gbk", errors="replace").decode(
                            "gbk", errors="replace"
                        )
                        print(f"无法生成 XML 文件: {safe_msg}")
                return
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
            xml_generator_runtime.clear_run_logger()
