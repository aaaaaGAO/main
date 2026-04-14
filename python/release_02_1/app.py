#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask 应用入口（骨架版）

重构后 app.py 仅保留：
- 注册蓝图（由 web.create_app 完成）
- 首页渲染
- 模板路径（兼容 PyInstaller 打包）
- 全局错误处理
- 心跳监控线程与启动逻辑（端口探测、自动打开浏览器）

所有业务接口已迁移至：
- web.routes.common  -> /api/healthz, /api/heartbeat, /api/load_config, /api/select_file, /api/parse_file_structure, /api/get_filter_options
- web.routes.lr_rear  -> /api/lr/generate/can, /api/lr/config
- web.routes.central  -> /api/central/generate
- web.routes.dtc      -> /api/dtc/generate

底层逻辑由 ConfigManager / GuiService / TaskOrchestrator 提供。
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading    
import time
import webbrowser

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from infra.filesystem import get_base_dir
from web import create_app

# 工具显示名（Web 右上角 + build_exe 打包时的 EXE 文件名，只改此处即可）
TOOL_DISPLAY_NAME = "测试用例生成工具_2026.4.14"

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
AUTO_EXIT_ON_NO_HEARTBEAT = False  # 长时间无心跳是否自动退出（默认关闭）
last_heartbeat_time = time.time()


def get_app_path() -> str:
    """获取程序运行根目录（打包后为 EXE 所在目录），供工作目录切换与配置查找使用。
    参数：无。
    返回：项目根目录绝对路径。
    """
    return get_base_dir(__file__)


def get_resource_path(relative_path: str) -> str:
    """获取资源路径（打包后从 MEIPASS 读取 templates/static 等）。
    参数：relative_path — 资源子路径，如 'templates'、'static'。
    返回：模板/静态资源目录的绝对路径。
    """
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def find_available_port(start_port: int = 5001) -> int:
    """查找本地可用端口（从 start_port 起递增至 6000 前找到未占用端口）。
    参数：start_port — 起始探测端口号，默认 5001。
    返回：第一个可绑定的端口号；若 5001~5999 均被占用则返回 start_port。
    """
    port = start_port
    while port < 6000:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    return start_port


def auto_suicide_monitor() -> None:
    """心跳监控线程：无心跳超时则退出（由 AUTO_EXIT_ON_NO_HEARTBEAT 控制）。
    参数：无。
    返回：无返回值（常驻循环）。
    """
    global last_heartbeat_time
    while True:
        time.sleep(10)
        if not AUTO_EXIT_ON_NO_HEARTBEAT:
            continue
        if time.time() - last_heartbeat_time > 60:
            print("检测到长时间无心跳，退出进程。")
            os._exit(0)


# ---------------------------------------------------------------------------
# 根路由与全局错误处理（模块级函数，在 make_app 中注册到 app）
# ---------------------------------------------------------------------------
def index():
    """首页：渲染 index.html。"""
    return render_template("index.html", app_name=TOOL_DISPLAY_NAME)


def handle_500(e):
    """统一处理 HTTP 500：将异常信息返回为 JSON。参数 e: 触发的异常对象。"""
    return jsonify(success=False, message=str(e) if e else "Internal Server Error"), 500


def handle_exception(e):
    """全局异常处理：HTTPException 原样返回，其余转 500。参数 e: 触发的异常对象。"""
    if isinstance(e, HTTPException):
        return e
    return handle_500(e)


# ---------------------------------------------------------------------------
# 应用工厂：创建 app 并挂载仅属于 app 的路由与配置
# ---------------------------------------------------------------------------
def make_app() -> Flask:
    """创建并配置 Flask 应用实例：注册蓝图、模板/静态路径、根路由与全局错误处理。
    参数：无。
    返回：配置好的 Flask 应用，供 run 或 WSGI 使用。
    """
    # 1. 调用 web/__init__.py 里的 create_app()
    # 它会自动注册所有的蓝图（lr_rear, central, dtc, common）
    app = create_app()

    # 2. 兼容 PyInstaller：配置模板与静态资源目录路径
    app.template_folder = get_resource_path("templates")
    app.static_folder = get_resource_path("static")

    # 3. 根路由与全局错误处理
    app.add_url_rule("/", view_func=index)
    app.register_error_handler(500, handle_500)
    app.register_error_handler(Exception, handle_exception)

    return app


# ---------------------------------------------------------------------------
# 实例化并添加全局拦截
# ---------------------------------------------------------------------------
app = make_app()


@app.before_request
def track_heartbeat():
    global last_heartbeat_time
    if request.path == "/api/heartbeat" and request.method == "POST":
        last_heartbeat_time = time.time()


def open_browser_after_delay(url: str) -> None:
    """延迟打开浏览器（在独立线程中调用，避免阻塞服务启动）。"""
    time.sleep(1.5)
    webbrowser.open(url)


def start_app() -> None:
    """启动 Web 服务：切换工作目录、启动心跳监控线程、探测可用端口、延迟打开浏览器并运行 Flask。
    参数：无。
    返回：无返回值。依赖 get_app_path、find_available_port、make_app 及全局 app。
    """
    try:
        os.chdir(get_app_path())
    except Exception as error:
        print(f"切换工作目录失败: {error}")

    threading.Thread(target=auto_suicide_monitor, daemon=True).start()
    
    port = find_available_port(5001)
    url = f"http://127.0.0.1:{port}"
    
    print(f"正在启动服务: {url}")
    
    threading.Thread(
        target=open_browser_after_delay,
        args=(url,),
        daemon=True,
    ).start()

    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    try:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    except Exception as error:
        print(f"程序异常: {error}")
    finally:
        os._exit(0)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    start_app()
