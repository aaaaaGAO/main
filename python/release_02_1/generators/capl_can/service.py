#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAN 生成调度服务（重构骨架版）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from core.base_task import BaseGeneratorTask
from core.log_run_context import ensure_run_log_dirs
from core.mapping_context import MappingContext
from services.config_constants import (
    DEFAULT_DOMAIN_LR_REAR,
    OPTION_INPUT_EXCEL,
    OPTION_OUTPUT_DIR,
    SECTION_LR_REAR,
    SECTION_PATH,
)

from .excel_repo import CANExcelRepository
from .generated_from_cases_bundle import (
    log_excel_generation_summaries,
    log_no_can_generated_summary,
    process_excel_for_generated_case_cans,
    write_master_can_aggregate_file,
)
from .logging import log_progress_or_info
from .models import CANTestCase
from .renderer import CANFileRenderer
from .runtime import CANEntrypointSupport
from .generated_cases_context import build_generated_cases_run_context
from .translator import CANStepTranslator


@dataclass(slots=True)
class TaskLogBuffer:
    """`CANGeneratorService` 在 extract/transform 阶段暂存人可读信息/错误，供 `load` 中写入 logger。"""

    infos: list[str]
    errors: list[str]

    def add_info(self, message: str) -> None:
        """追加一条信息字符串。参数：message — 文本。返回：无。"""
        self.infos.append(message)

    def add_error(self, message: str) -> None:
        """追加一条错误字符串。参数：message — 文本。返回：无。"""
        self.errors.append(message)


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
        self.io_mapping_context: Any = None
        self.config_enum_context: Any = None
        self.log_buffer = TaskLogBuffer(infos=[], errors=[])

    @property
    def task_name(self) -> str:
        """`BaseGeneratorTask` 展示用任务名。返回：固定中文字符串。"""
        return "CAN 生成（重构骨架）"

    def setup_logging(self) -> logging.Logger:
        """创建并配置 CAN 生成器 logger（StreamHandler）。返回: Logger。"""
        logger = logging.getLogger("can_generator_service")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
        return logger

    def extract_data(self) -> list[CANTestCase]:
        """从配置的 input_excel 加载用例并做等级/平台/车型筛选。返回: CANTestCase 列表。"""
        self.ensure_runtime_paths()
        mapping_context = MappingContext.from_config(
            self.config, base_dir=self.base_dir, config_path=self.config_path
        )
        self.io_mapping_context = mapping_context.io_mapping
        self.config_enum_context = mapping_context.config_enum
        repository = CANExcelRepository(self.base_dir, self.config)
        sheet_cases, repository_stats = repository.load_cases(self.input_path)
        cases = [case for group in sheet_cases.values() for case in group]
        self.log_buffer.add_info(f"读取完成：{len(cases)} 条用例")
        self.log_buffer.add_info(f"过滤统计：{repository_stats}")
        return cases

    def transform(self, payload_data: list[CANTestCase]) -> list[CANTestCase]:
        """对用例步骤做关键字/IO/枚举翻译，填充 steps 与 error_records。参数: data — 用例列表。返回: 同一列表（原地修改）。"""
        translator = CANStepTranslator(
            io_mapping_ctx=self.io_mapping_context,
            config_enum_ctx=self.config_enum_context,
            keyword_specs=self.keyword_specs,
        )
        for case in payload_data:
            for raw_step in case.raw_steps:
                translate_result = translator.translate(raw_step)
                case.steps.extend(translate_result.code_lines)
                case.error_records.extend(translate_result.errors)
            # SOA REQ / CHECK / CHECKREQ 顺序调整与 _Prepare 后缀由 renderer 渲染阶段统一处理
        self.log_buffer.add_info("步骤翻译完成")
        return payload_data

    def load(self, content: list[CANTestCase]) -> None:
        """将翻译后的用例渲染为 .can 文件并写入 output_dir，同时生成 Master.can。参数: content — 用例列表。无返回值。"""
        renderer = CANFileRenderer()
        os.makedirs(self.output_dir, exist_ok=True)

        for case in content:
            filename = f"{case.case_id}.can"
            case.target_path = os.path.join(self.output_dir, filename)
            text = renderer.render_single_file(case)
            self.write_gbk_file(case.target_path, text)

        master_path = os.path.join(self.output_dir, "Master.can")
        master_text = renderer.render_master(content)
        self.write_gbk_file(master_path, master_text)
        self.log_buffer.add_info(f"生成完成：{len(content)} 个 .can + Master.can")

        if self.logger:
            for info_message in self.log_buffer.infos:
                self.logger.info(info_message)
            for error_message in self.log_buffer.errors:
                self.logger.error(error_message)

    def ensure_runtime_paths(self) -> None:
        """
        在 CLI/BaseTask 路径下从 INI 补全 `input_path` 与 `output_dir`；缺任一则抛 `ValueError`。

        参数：无。返回：无。
        """
        if not self.input_path:
            self.input_path = self.get_config_value(SECTION_LR_REAR, OPTION_INPUT_EXCEL, fallback="")
        if not self.output_dir:
            self.output_dir = self.get_config_value(SECTION_PATH, "output_dir_can", fallback="")
            if not self.output_dir:
                self.output_dir = self.get_config_value(SECTION_LR_REAR, OPTION_OUTPUT_DIR, fallback="")
        if not self.input_path:
            raise ValueError(f"未配置 {OPTION_INPUT_EXCEL}（可传参或配置 [{SECTION_LR_REAR}] {OPTION_INPUT_EXCEL}）")
        if not self.output_dir:
            raise ValueError(f"未配置 {OPTION_OUTPUT_DIR}（可传参或配置 [{SECTION_PATH}]/[{SECTION_LR_REAR}]）")

    @staticmethod
    def write_gbk_file(file_path: str, content: str) -> None:
        """以 gbk、\\r\\n 写入 CAPL 文件。参数: path — 文件路径；content — 文本内容。无返回值。"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="gbk", newline="\r\n", errors="replace") as file_obj:
            file_obj.write(content)

    def run_pipeline(
        self,
        gconfig,
        *,
        base_dir: str,
        domain: str = DEFAULT_DOMAIN_LR_REAR,
        run_dirs=None,
        io_mapping_ctx=None,
        config_enum_ctx=None,
        main_log_path: str | None = None,
        workbook_cache: dict[str, object] | None = None,
    ) -> None:
        """
        接管 CAN 生成主编排流程（入口在 entrypoint.run_generation）。

        路径、写文件、日志、关键字与 Clib 校验均在内部通过
        runtime_io 与 CANEntrypointSupport 完成。
        """
        if run_dirs is None:
            run_dirs = ensure_run_log_dirs(base_dir)

        if main_log_path is None:
            main_log_path = os.path.join(run_dirs.gen_dir, "generate_can_from_excel.log")

        runtime_paths = CANEntrypointSupport.build_runtime_paths(gconfig, domain)

        can_log_root = os.path.join(run_dirs.gen_dir, "can")
        os.makedirs(can_log_root, exist_ok=True)

        ctx = build_generated_cases_run_context(
            gconfig=gconfig,
            base_dir=base_dir,
            domain=domain,
            runtime_paths=runtime_paths,
            io_mapping_ctx=io_mapping_ctx,
            config_enum_ctx=config_enum_ctx,
        )

        generated_can_files: list[str] = []
        excel_can_map: dict[str, list[str]] = {}
        excel_stats_map: dict[str, dict] = {}
        logger = logging.getLogger("can_generator")

        for excel_path in runtime_paths["excel_files"]:
            process_excel_for_generated_case_cans(
                excel_path=excel_path,
                base_dir=base_dir,
                allowed_levels=ctx.allowed_levels,
                allowed_platforms=ctx.allowed_platforms,
                allowed_models=ctx.allowed_models,
                allowed_target_versions=ctx.allowed_target_versions,
                selected_filter=ctx.selected_filter,
                translator=ctx.translator,
                renderer=ctx.renderer,
                testcases_dir=runtime_paths["testcases_dir"],
                can_log_root=can_log_root,
                main_log_path=main_log_path,
                logger=logger,
                generated_can_files=generated_can_files,
                excel_can_map=excel_can_map,
                excel_stats_map=excel_stats_map,
                workbook_cache=workbook_cache,
            )

        if not generated_can_files:
            log_no_can_generated_summary(
                logger,
                selected_filter=ctx.selected_filter,
                excel_files=runtime_paths["excel_files"],
                excel_stats_map=excel_stats_map,
            )
            return

        write_master_can_aggregate_file(
            master_output_path=runtime_paths["master_output_path"],
            generated_can_files=generated_can_files,
            secoc_qualifier=str(runtime_paths.get("secoc_qualifier") or ""),
            has_keyword_clib=bool(runtime_paths.get("has_keyword_clib")),
            cin_output_filename=runtime_paths.get("cin_output_filename"),
        )

        log_progress_or_info(logger, f"Master .can 文件已生成: {runtime_paths['master_output_path']}")
        log_progress_or_info(
            logger,
            f"所有文件生成完成！共生成 {len(generated_can_files)} 个小文件和 1 个Master文件",
        )

        log_excel_generation_summaries(
            logger,
            excel_files=runtime_paths["excel_files"],
            excel_can_map=excel_can_map,
            excel_stats_map=excel_stats_map,
            selected_filter=ctx.selected_filter,
        )


def run_cli(base_dir: str | None = None) -> None:
    """
    命令行 / ``python -m`` 调试用：构造 `CANGeneratorService` 并执行 `BaseGeneratorTask.run()` 主流程。

    参数：base_dir — 工程根，``None`` 时由基类从 `__file__` 推断。返回：无。
    """
    service = CANGeneratorService(base_dir=base_dir)
    service.run()


if __name__ == "__main__":
    run_cli()
