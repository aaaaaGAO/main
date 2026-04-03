#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services 包：应用服务层（封装具体业务逻辑）

本包不直接导出符号，作为命名空间聚合以下子模块，供 web、命令行入口等调用：

- config_service : 处理主配置文件 / 固定配置文件的读写与格式化；
                   典型接口：按 base_dir 读配置、解析路径与 sheet 等。
- gui_service    : 处理 Tk 弹窗与用户交互（预留）。
- task_service   : 调度底层各类生成任务（如 CAN/CIN/XML/DID 等），统一入口与参数传递（预留）。

调用方通过 `from services.xxx import ...` 使用具体服务类或函数。
"""

