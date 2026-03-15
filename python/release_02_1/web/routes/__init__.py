#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web.routes 包：按领域拆分的路由模块

本包不直接导出符号；各子模块定义 Blueprint，由 web 包的 create_app() 注册到 Flask 应用。

子模块与路由前缀说明：
- common   : 健康检查、心跳等基础接口，前缀 /api。
- lr_rear  : 左右后域用例生成相关路由，前缀 /api/lr。
- central  : 中央域生成路由，前缀 /api/central。
- dtc      : DTC 生成路由，前缀 /api/dtc。

调用方通过 `from web import create_app` 获取应用，无需直接 import 本包内 Blueprint。
"""

