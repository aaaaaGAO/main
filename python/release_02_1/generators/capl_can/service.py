#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN 生成调度服务（重构骨架版）。
"""

from __future__ import annotations

import logging
import os
from glob import glob
from dataclasses import dataclass
from typing import Any

from core.base_task import BaseGeneratorTask
from core.case_filter import CaseFilter
from core.error_module import ErrorModuleResolver
from core.mapping_context import MappingContext
from utils.sheet_filter import parse_selected_sheets

from .excel_repo import CANExcelRepository
from .logging import log_progress_or_info
from .models import CANTestCase
from .renderer import CANFileRenderer
from .runtime import CANEntrypointSupport
from .runtime_io import (
    build_ungenerated_reason as io_build_ungenerated_reason,
    create_clib_validator as io_create_clib_validator,
    load_keyword_specs as io_load_keyword_specs,
    sanitize_filename_part as io_sanitize_filename_part,
    write_can_text as io_write_can_text,
    write_sheet_can_log as io_write_sheet_can_log,
)
from .translator import CANStepTranslator


@dataclass(slots=True)
class TaskLogBuffer:
    infos: list[str]
    errors: list[str]

    def add_info(self, msg: str) -> None:
        self.infos.append(msg)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)


class CANGeneratorService(BaseGeneratorTask):
    """
    总调度：组织 ExcelRepository -> Translator -> Renderer 流程。

    说明：
    - 当前是“最小可运行骨架”，保留 TODO 扩展点，便于从旧脚本逐段迁移。
    - 入口已迁入 generators.capl_can.entrypoint。
    """

    def __init__(
        self,
        base_dir: str | None = None,
        *,
        input_path: str | None = None,
        output_dir: str | None = None,
        keyword_specs: dict[str, dict[str, object]] | None = None,
    ) -> None:
        """参数: base_dir — 工程根目录；input_path — 输入 Excel 路径；output_dir — 输出目录；keyword_specs — 关键字规格字典。"""
        super().__init__(base_dir=base_dir, reference_file=__file__)
        self.input_path = input_path or ""
        self.output_dir = output_dir or ""
        self.keyword_specs = keyword_specs or {}
        self._io_ctx: Any = None
        self._enum_ctx: Any = None
        self.log_buffer = TaskLogBuffer(infos=[], errors=[])

    @property
    def task_name(self) -> str:
        return "CAN 生成（重构骨架）"

    def setup_logging(self) -> logging.Logger:
        """创建并配置 CAN 生成器 logger（StreamHandler）。返回: Logger。"""
        logger = logging.getLogger("can_generator_service")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        return logger

    def extract_data(self) -> list[CANTestCase]:
        """从配置的 input_excel 加载用例并做等级/平台/车型筛选。返回: CANTestCase 列表。"""
        self._ensure_runtime_paths()
        ctx = MappingContext.from_config(
            self.config, base_dir=self.base_dir, config_path=self.config_path
        )
        self._io_ctx = ctx.io_mapping
        self._enum_ctx = ctx.config_enum
        repo = CANExcelRepository(self.base_dir, self.config)
        sheet_cases, stats = repo.load_cases(self.input_path)
        cases = [case for group in sheet_cases.values() for case in group]
        self.log_buffer.add_info(f"读取完成：{len(cases)} 条用例")
        self.log_buffer.add_info(f"过滤统计：{stats}")
        return cases

    def transform(self, data: list[CANTestCase]) -> list[CANTestCase]:
        """对用例步骤做关键字/IO/枚举翻译，填充 steps 与 error_records。参数: data — 用例列表。返回: 同一列表（原地修改）。"""
        translator = CANStepTranslator(
            io_mapping_ctx=self._io_ctx,
            config_enum_ctx=self._enum_ctx,
            keyword_specs=self.keyword_specs,
        )
        for case in data:
            for raw_step in case.raw_steps:
                res = translator.translate(raw_step)
                case.steps.extend(res.code_lines)
                case.error_records.extend(res.errors)
            # SOA REQ / CHECK / CHECKREQ 顺序调整与 _Prepare 后缀由 renderer 渲染阶段统一处理
        self.log_buffer.add_info("步骤翻译完成")
        return data

    def load(self, content: list[CANTestCase]) -> None:
        """将翻译后的用例渲染为 .can 文件并写入 output_dir，同时生成 Master.can。参数: content — 用例列表。无返回值。"""
        renderer = CANFileRenderer()
        os.makedirs(self.output_dir, exist_ok=True)

        for case in content:
            filename = f"{case.case_id}.can"
            case.target_path = os.path.join(self.output_dir, filename)
            text = renderer.render_single_file(case)
            self._write_gbk(case.target_path, text)

        master_path = os.path.join(self.output_dir, "Master.can")
        master_text = renderer.render_master(content)
        self._write_gbk(master_path, master_text)
        self.log_buffer.add_info(f"生成完成：{len(content)} 个 .can + Master.can")

        if self.logger:
            for msg in self.log_buffer.infos:
                self.logger.info(msg)
            for msg in self.log_buffer.errors:
                self.logger.error(msg)

    def _ensure_runtime_paths(self) -> None:
        if not self.input_path:
            self.input_path = self.get_config_value("LR_REAR", "input_excel", fallback="")
        if not self.output_dir:
            self.output_dir = self.get_config_value("PATH", "output_dir_can", fallback="")
            if not self.output_dir:
                self.output_dir = self.get_config_value("LR_REAR", "output_dir", fallback="")
        if not self.input_path:
            raise ValueError("未配置 input_excel（可传参或配置 [LR_REAR] input_excel）")
        if not self.output_dir:
            raise ValueError("未配置 output_dir（可传参或配置 [PATH]/[LR_REAR]）")

    @staticmethod
    def _write_gbk(path: str, content: str) -> None:
        """以 gbk、\\r\\n 写入 CAPL 文件。参数: path — 文件路径；content — 文本内容。无返回值。"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="gbk", newline="\r\n", errors="replace") as f:
            f.write(content)

    def run_legacy_pipeline(
        self,
        gconfig,
        *,
        base_dir: str,
        domain: str = "LR_REAR",
        run_dirs=None,
        io_mapping_ctx=None,
        config_enum_ctx=None,
        main_log_path: str | None = None,
    ) -> None:
        """
        接管 CAN 生成主编排流程（入口在 entrypoint.main）。

        不再依赖 CANLegacyHooks；路径、写文件、日志、关键字与 Clib 校验均在内部通过
        runtime_io 与 CANEntrypointSupport 完成。
        """
        if run_dirs is None:
            from core.log_run_context import ensure_run_log_dirs

            run_dirs = ensure_run_log_dirs(base_dir)

        if main_log_path is None:
            main_log_path = os.path.join(run_dirs.gen_dir, "generate_can_from_excel.log")

        rt = CANEntrypointSupport.build_runtime_paths(gconfig, domain)

        can_log_root = os.path.join(run_dirs.gen_dir, "can")
        os.makedirs(can_log_root, exist_ok=True)

        allowed_levels = None
        allowed_platforms = None
        allowed_models = None
        allowed_levels = CaseFilter.parse_levels(
            gconfig.get_first(
                [
                    (domain, "Case_Levels"),
                    (domain, "case_levels"),
                    ("FILTER", "Case_Levels"),
                    ("FILTER", "case_levels"),
                    ("LR_REAR", "Case_Levels"),
                    ("LR_REAR", "case_levels"),
                ],
                fallback=None,
            )
        )
        allowed_platforms = CaseFilter.parse_platforms_or_models(
            gconfig.get_first(
                [
                    (domain, "Case_Platforms"),
                    (domain, "case_platforms"),
                    ("FILTER", "Case_Platforms"),
                    ("FILTER", "case_platforms"),
                    ("LR_REAR", "Case_Platforms"),
                    ("LR_REAR", "case_platforms"),
                ],
                fallback=None,
            )
        )
        allowed_models = CaseFilter.parse_platforms_or_models(
            gconfig.get_first(
                [
                    (domain, "Case_Models"),
                    (domain, "case_models"),
                    ("FILTER", "Case_Models"),
                    ("FILTER", "case_models"),
                    ("LR_REAR", "Case_Models"),
                    ("LR_REAR", "case_models"),
                ],
                fallback=None,
            )
        )
        case_target_versions_value = (
            gconfig.get_first(
                [
                    (domain, "Case_Target_Versions"),
                    (domain, "case_target_versions"),
                    ("FILTER", "Case_Target_Versions"),
                    ("FILTER", "case_target_versions"),
                    ("LR_REAR", "Case_Target_Versions"),
                    ("LR_REAR", "case_target_versions"),
                ],
                fallback="",
            )
            or ""
        )
        try:
            from services.filter_service import parse_shaixuan_config
            fopts = parse_shaixuan_config(base_dir)
            all_target_versions = fopts.get("target_versions") or []
        except Exception:
            all_target_versions = []
        allowed_target_versions = CaseFilter.parse_target_versions(
            case_target_versions_value.strip() or None, all_target_versions
        )

        selected_sheets_str = gconfig.get_first(
            [
                (domain, "selected_sheets"),
                ("LR_REAR", "selected_sheets"),
            ]
        ).strip()
        selected_filter = parse_selected_sheets(selected_sheets_str)

        keyword_specs = io_load_keyword_specs(rt["mapping_excel_path"], rt["sheet_names"])
        if not keyword_specs:
            raise ValueError(f"未加载到关键字映射，请检查配置：{rt['mapping_excel_path']}")

        cin_excel_path = CANEntrypointSupport.resolve_cin_excel_path(
            gconfig, base_dir, domain=domain
        )
        clib_names_set = CANEntrypointSupport.load_clib_names_from_excel(
            cin_excel_path
        ) if cin_excel_path else set()
        clib_validator = io_create_clib_validator(clib_names_set)
        translator = CANStepTranslator(
            io_mapping_ctx=io_mapping_ctx,
            config_enum_ctx=config_enum_ctx,
            keyword_specs=keyword_specs,
            clib_validator=clib_validator,
        )
        renderer = CANFileRenderer(include_files=[])

        generated_can_files: list[str] = []
        excel_can_map: dict[str, list[str]] = {}
        excel_stats_map: dict[str, dict] = {}
        logger = logging.getLogger("can_generator")

        for excel_path in rt["excel_files"]:
            excel_name = os.path.basename(excel_path)
            log_progress_or_info(logger, f"解析 Excel 文件: {excel_name}")
            log_progress_or_info(logger, f"处理Excel={excel_name}")

            repo = CANExcelRepository(
                base_dir=base_dir,
                allowed_levels=allowed_levels,
                allowed_platforms=allowed_platforms,
                allowed_models=allowed_models,
                allowed_target_versions=allowed_target_versions,
                selected_filter=selected_filter,
            )
            sheet_cases_map, stats = repo.load_cases(excel_path)
            excel_stats_map[excel_path] = stats
            if not sheet_cases_map:
                reason = io_build_ungenerated_reason(stats)
                logger.info(f"  警告: 文件 '{excel_name}' 中未找到任何测试用例（{reason}）")
                continue

            skip_events_map = getattr(repo, "skip_events_map", {})

            for (fp, sheet_name), cases in sheet_cases_map.items():
                events: list[tuple[int | None, int, str, dict]] = []
                for se in skip_events_map.get((fp, sheet_name), []) or []:
                    events.append((se.get("excel_row"), 0, "skip", se))

                for case in cases:
                    for raw_step in case.raw_steps:
                        res = translator.translate(raw_step)
                        case.steps.extend(res.code_lines)
                        case.error_records.extend(res.errors)

                    # SOA REQ / CHECK / CHECKREQ 相关顺序调整与 _Prepare 后缀由 renderer 渲染阶段统一处理
                    for err in case.error_records:
                        row_for_sort = (
                            err.excel_row
                            if err.excel_row is not None
                            else getattr(case, "excel_row", 0)
                        )
                        payload = {
                            "case_id": case.case_id,
                            "excel_row": row_for_sort,
                            "raw_step": err.raw_step,
                            "message": err.message,
                        }
                        events.append((row_for_sort, 1, "error", payload))

                events.sort(key=lambda e: ((e[0] if e[0] is not None else 10**9), e[1]))
                log_progress_or_info(logger, f"  处理Sheet={sheet_name}")
                for excel_row, _prio, kind, payload in events:
                    if kind == "skip":
                        logger.info(
                            f"[跳过] 用例ID={payload['case_id']}, 功能模块={payload['group']}, 用例类型='{payload['case_type']}'（{payload['reason']}）"
                        )
                    elif kind == "error":
                        err_mod = ErrorModuleResolver.resolve(payload["message"])
                        logger.error(
                            f"错误模块【{err_mod}】 用例ID={payload['case_id']} 行号：{excel_row}  用例步骤：{payload['raw_step']}  原因：{payload['message']}"
                        )

                excel_name = os.path.basename(fp)
                excel_basename = os.path.splitext(excel_name)[0]
                can_filename = (
                    f"generated_from_cases_{io_sanitize_filename_part(excel_basename)}_"
                    f"{io_sanitize_filename_part(sheet_name)}.can"
                )
                log_progress_or_info(logger, f"生成文件: {can_filename} (用例数={len(cases)})")
                for h in logger.handlers:
                    try:
                        h.flush()
                    except Exception:
                        pass

                sheet_log_name = (
                    f"{io_sanitize_filename_part(excel_basename)}_"
                    f"{io_sanitize_filename_part(sheet_name)}.log"
                )
                sheet_log_path = os.path.join(can_log_root, sheet_log_name)
                try:
                    io_write_sheet_can_log(
                        sheet_log_path,
                        excel_name=excel_name,
                        sheet_name=sheet_name,
                        cases=cases,
                        can_filename=can_filename,
                        global_log_path=main_log_path,
                    )
                except Exception:
                    pass

                if cases:
                    can_filepath = os.path.join(rt["testcases_dir"], can_filename)
                    can_content = renderer.render_sheet_file(cases)
                    io_write_can_text(can_filepath, can_content)
                    generated_can_files.append(can_filename)
                    excel_can_map.setdefault(fp, []).append(can_filename)

        if not generated_can_files:
            logger.info("没有生成任何.can文件")
            if selected_filter:
                expected = ", ".join(sorted(selected_filter.keys()))
                logger.info(
                    f" 提示: 已配置 selected_sheets 时，只有这些文件名会被处理。请确认它们在 input_excel 目录下存在: %s",
                    expected,
                )
            log_progress_or_info(logger, "未生成 .can 的 Excel 汇总")
            for fp in rt["excel_files"]:
                excel_name_only = os.path.basename(fp)
                stats = excel_stats_map.get(fp, {})
                reason = io_build_ungenerated_reason(stats)
                log_progress_or_info(
                    logger, f"  Excel={excel_name_only} → 未生成 .can，原因：{reason}"
                )
            return

        master_lines = [
            "/*@!Encoding:936*/",
            "/*@!Encoding:936*/",
            "includes",
            "{",
            '  #include "TestMoudleControl\\TestMoudleControl_Swc.can"',
        ]
        secoc_qualifier = (rt.get("secoc_qualifier") or "").strip()
        if secoc_qualifier:
            master_lines.append(
                f'  #include "..\\ILNode\\SecOc\\CAN\\{secoc_qualifier}.cin"'
            )
        # 是否包含 .cin 由「是否选择了关键字集 Clib 配置表」决定
        if rt.get("has_keyword_clib") and rt.get("cin_output_filename"):
            master_lines.append(f'  #include "{rt["cin_output_filename"]}"')
        for can_filename in sorted(generated_can_files):
            master_lines.append(f'  #include "Testcases\\{can_filename}"')
        master_lines.append("}")
        master_dir = os.path.dirname(rt["master_output_path"])
        current_master_name = os.path.basename(rt["master_output_path"])
        for stale_path in glob(os.path.join(master_dir, "*.can")):
            if os.path.basename(stale_path).lower() == current_master_name.lower():
                continue
            try:
                os.remove(stale_path)
            except Exception:
                pass
        io_write_can_text(rt["master_output_path"], "\n".join(master_lines))

        log_progress_or_info(logger, f"Master .can 文件已生成: {rt['master_output_path']}")
        log_progress_or_info(
            logger,
            f"所有文件生成完成！共生成 {len(generated_can_files)} 个小文件和 1 个Master文件",
        )

        if len(rt["excel_files"]) > 1:
            log_progress_or_info(logger, "目录模式 CAN 生成汇总开始")
            for fp in rt["excel_files"]:
                excel_name_only = os.path.basename(fp)
                can_list = excel_can_map.get(fp, [])
                if can_list:
                    log_progress_or_info(
                        logger,
                        f"  Excel={excel_name_only} → 生成 {len(can_list)} 个 .can：{', '.join(can_list)}",
                    )
            ungenerated = [fp for fp in rt["excel_files"] if not excel_can_map.get(fp)]
            if ungenerated:
                log_progress_or_info(logger, "未生成 .can 的 Excel 汇总")
                for fp in ungenerated:
                    excel_name_only = os.path.basename(fp)
                    stats = excel_stats_map.get(fp, {})
                    reason = io_build_ungenerated_reason(stats)
                    log_progress_or_info(
                        logger, f"  Excel={excel_name_only} → 未生成 .can，原因：{reason}"
                    )
            log_progress_or_info(logger, "目录模式 CAN 生成汇总结束")
        elif len(rt["excel_files"]) == 1:
            fp = rt["excel_files"][0]
            excel_name_only = os.path.basename(fp)
            can_list = excel_can_map.get(fp, [])
            if can_list:
                log_progress_or_info(
                    logger,
                    f"  Excel={excel_name_only} → 生成 {len(can_list)} 个 .can：{', '.join(can_list)}",
                )
            else:
                stats = excel_stats_map.get(fp, {})
                reason = io_build_ungenerated_reason(stats)
                log_progress_or_info(
                    logger, f"  Excel={excel_name_only} → 未生成 .can，原因：{reason}"
                )


def main(base_dir: str | None = None) -> None:
    service = CANGeneratorService(base_dir=base_dir)
    service.run()


if __name__ == "__main__":
    main()
