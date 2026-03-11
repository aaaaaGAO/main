#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import PyInstaller.__main__
import os
import sys
import shutil

base_dir = os.path.dirname(os.path.abspath(__file__))

# EXE 文件名与 Web 右上角一致，来自 app.py（只改 app.py 里 TOOL_DISPLAY_NAME 即可）
from app import TOOL_DISPLAY_NAME
exe_name = TOOL_DISPLAY_NAME
main_script = 'app.py'

# 构建参数
args = [
    main_script,
    f'--name={exe_name}',
    '--onefile',         # 打包成单个 EXE 文件（直接生成在当前目录）
    #'--noconsole',       # 不显示控制台窗口（避免误关闭）
    '--distpath=.',      # 直接生成在当前目录
    '--workpath=build',
    '--specpath=build',
    '--clean',           # 打包前清理临时文件
    #'--windowed',        # Windows GUI 模式（与 --noconsole 配合）
]

# 1. 包含模板与静态资源 (打包进 EXE 内部)
templates_path = os.path.join(base_dir, 'templates')
if os.path.exists(templates_path):
    args.append(f'--add-data={os.path.normpath(templates_path)};templates')
static_path = os.path.join(base_dir, 'static')
if os.path.exists(static_path):
    args.append(f'--add-data={os.path.normpath(static_path)};static')

# 2. 隐藏导入 (确保动态加载的模块被包含)
hidden_imports = [
    # Flask 相关
    'flask', 'werkzeug', 'jinja2', 'werkzeug.exceptions',
    # GUI 相关
    'tkinter', 'tkinter.filedialog',
    # Excel 处理
    'openpyxl', 'openpyxl.cell', 'openpyxl.worksheet',
    # 底层生成模块（必须全部包含）
    'generate_can_from_excel', 
    'generate_cin_from_excel',
    'generate_xml_from_can', 
    'generate_didinfo_from_excel',
    'generate_did_config',
    'generators.capl_didconfig',
    'generators.capl_didconfig.service',
    'generate_uart_from_config',  # 之前遗漏了这个
    # 领域层（原根目录模块已迁入 core）
    'core.translator.io_mapping',
    'core.parser.step_parser',
    'core.common.name_sanitize',
    'core.common.sanitizer',
    'core.translator.config_enum',
    'core.caseid_log_dedup',
    'core.log_run_context',
    'core.parse_table_loggers',
    # 可选依赖（如果安装了）
    'pypinyin',  # 中文转拼音，用于 .can 文件名中的拼音化
    'pypinyin.lazy_pinyin',  # pypinyin 的子模块
    # 串口库（可选）
    'serial', 'serial.tools', 'serial.tools.list_ports',
    # 标准库（确保被包含）
    'configparser',
    'logging', 'logging.handlers',
    'dataclasses',
    'collections', 'collections.defaultdict',
    'typing', 'typing.Optional', 'typing.Callable',
    'unicodedata',  # io_mapping 使用
    # infra 层（新架构入口，避免打包漏模块）
    'infra',
    'infra.config',
    'infra.filesystem',
    'infra.excel',
    'infra.logger',
]
for imp in hidden_imports:
    args.append(f'--hidden-import={imp}')

# 3. 收集 openpyxl 的所有数据文件 (避免打包后读取 Excel 报错)
args.append('--collect-all=openpyxl')

# 4. 收集 pypinyin 的数据文件（如果存在）
args.append('--collect-all=pypinyin')

# --- 执行删除旧文件逻辑 ---
# --onefile 模式会直接生成单个 EXE 文件在当前目录
exe_file = os.path.join(base_dir, f"{exe_name}.exe")

# 删除旧的 EXE 文件（如果存在）
if os.path.exists(exe_file):
    try:
        print(f"正在删除旧的 EXE 文件: {exe_file}")
        os.remove(exe_file)
        print("删除成功")
    except PermissionError:
        print(f"错误: 无法删除 {exe_file}，请先关闭正在运行的程序。")
        sys.exit(1)
    except Exception as e:
        print(f"警告: 删除旧 EXE 文件时出错: {e}，继续打包...")

print("\n开始打包...")
try:
    PyInstaller.__main__.run(args)
    print(f"\n✅ 打包完成！")
    print(f"   EXE 文件位置: {exe_file}")
    
    # 检查外部必需文件/文件夹是否存在
    print("\n--- 运行前检查 ---")
    print(f"提示: --onefile 模式会直接生成单个 EXE 文件在当前目录。")
    print(f"      EXE 文件会读取同级目录下的配置文件（如 Configuration.txt、FixedConfig.txt 等）。")
    print()
    if not os.path.exists(os.path.join(base_dir, "input")):
        print("提示: 请确保 EXE 同级目录下手动创建了 'input' 文件夹。")
    if not os.path.exists(os.path.join(base_dir, "Configuration.txt")):
        print("提示: 请确保 EXE 同级目录下存在 'Configuration.txt'。")

except Exception as e:
    print(f"❌ 打包失败: {e}")
    sys.exit(1)