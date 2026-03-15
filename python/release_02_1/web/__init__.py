#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web 包：Web 层（Flask 应用 + 路由）

本包提供 Flask 应用的创建与蓝图注册，供 WSGI 服务器（如 gunicorn）或直接 app.run() 使用。

子包与入口说明：
- routes.common  : 通用路由（心跳、健康检查、基础工具接口），前缀 /api。
- routes.lr_rear : LR_REAR 业务相关路由（预留），前缀 /api/lr。
- routes.central : 中央域相关路由（预留），前缀 /api/central。
- routes.dtc     : DTC 相关路由，前缀 /api/dtc。

主要对外接口：
- create_app() -> Flask
  无参数。创建并配置 Flask 实例，注册上述蓝图，并设置 app.config["BASE_DIR"] 为项目根目录。
  项目根目录由路径解析动态确定：打包时为 exe 所在目录；开发时从当前包所在目录向上查找
  含 Configuration.txt 的目录（目录名可任意，不依赖 release_02_1 等固定名称）。返回配置好的 Flask 应用。
"""

from __future__ import annotations

import os

from flask import Flask
from infra.filesystem.pathing import get_project_root

from .routes.common import common_bp
from .routes.lr_rear import lr_rear_bp
from .routes.central import central_bp
from .routes.dtc import dtc_bp


def _project_root() -> str:
    """获取项目根目录（Configuration.txt、filter_options.txt、FixedConfig.txt 所在目录），统一使用 infra.filesystem.pathing.get_project_root。
    参数：无。
    返回：根目录绝对路径。
    """
    return get_project_root(__file__)


def create_app() -> Flask:
    """创建并配置 Flask 应用实例，注册 common/lr_rear/central/dtc 四个蓝图并设置 BASE_DIR。
    参数：无。
    返回：配置好的 Flask 应用。蓝图前缀：/api、/api/lr、/api/central、/api/dtc。
    """
    app = Flask(__name__)
    app.config["BASE_DIR"] = _project_root()

    # 注册路由蓝图
    app.register_blueprint(common_bp, url_prefix="/api")
    app.register_blueprint(lr_rear_bp, url_prefix="/api/lr")
    app.register_blueprint(central_bp, url_prefix="/api/central")
    app.register_blueprint(dtc_bp, url_prefix="/api/dtc")

    return app

