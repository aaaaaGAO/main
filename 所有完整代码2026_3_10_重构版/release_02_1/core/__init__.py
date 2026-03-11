#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心业务层 (Core Domain)

本包不直接导出符号，作为命名空间聚合以下子包/模块，供 services、generators 引用：

- base_task        : BaseGeneratorTask — 生成任务模板方法基类，定义 run/步骤迭代等流程。
- error_module     : ErrorModuleResolver — 根据配置或上下文解析“错误模块”名称。
- mapping_context  : MappingContext — 统一加载 io_mapping 与 config_enum，供翻译与解析使用。
- case_filter      : CaseFilter — 等级/平台/车型/自动测试筛选；FilterStats — 筛选计数统计。
                      构造参数：allowed_levels, allowed_platforms, allowed_models（均为可选集合）。
- excel_header     : TestCaseHeaderResolver — 根据表头名解析列索引，定位用例表列。
- keyword_error    : KeywordErrorDescriber / describe_keyword_error — 关键字错误的可读描述。
"""
