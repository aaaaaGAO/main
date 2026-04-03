#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils 包：全项目共享工具命名空间

本包聚合各工具子模块，供 core、generators、services 等引用。与 infra 层部分能力重叠时，
新代码建议优先使用 infra（config、logger、filesystem、excel）以保持分层一致。

常见子模块与用途说明：
- path_utils : 路径解析、base_dir 检测、子目录智能查找（部分能力已迁移至 infra.filesystem）。
- logger     : 统一日志（PROGRESS_LEVEL、过滤器、TeeToLogger、Formatter）；infra.logger 为统一入口。
- config     : 配置单例或读写（主配置文件 + 固定配置文件）；infra.config 提供底层 I/O。
- excel_io   : Excel 读写封装（ExcelService 等）。

具体导出与参数以各子模块 __init__.py 或模块内 docstring 为准。
"""
