#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交互服务层（GuiService）

目标：收纳 Tkinter 弹窗和文件/文件夹解析逻辑。
职责：封装 tk_lock，提供 select_path(type)、parse_file_structure。
"""

from __future__ import annotations

import gc
import importlib
import importlib.util
import os
import re
import threading
import traceback
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Literal, Optional

from infra.excel.workbook import ExcelService
from infra.filesystem import resolve_runtime_path

tk = None  # type: ignore[assignment]
filedialog = None  # type: ignore[assignment]
if importlib.util.find_spec("tkinter") is not None:
    tkinter_module = importlib.import_module("tkinter")
    tk = tkinter_module
    filedialog = importlib.import_module("tkinter.filedialog")

# 线程锁：无 GUI 环境仍可通过 try/except 导入本模块
tk_lock = threading.Lock()


class GuiService:
    """
    GUI 交互服务：弹窗选路径、解析文件结构。
    使用 tk_lock 保证同一时间只有一个 Tk 弹窗，防止 Tcl 崩溃。
    """

    @staticmethod
    def config_filetypes() -> List[tuple[str, str]]:
        """配置文件选择器：仅 INI。"""
        return [
            ("INI 配置", "*.ini"),
            ("所有文件", "*.*"),
        ]

    @staticmethod
    def select_path(
        file_type: Literal["file", "folder"] = "file",
    ) -> Optional[str]:
        """弹出系统选择文件/文件夹窗口（线程安全 + 置顶）。
        参数：file_type — "file" 选文件（Excel），"folder" 选文件夹。
        返回：选中路径；取消或异常返回 None。
        """
        if tk is None or filedialog is None:
            print("当前环境无 tkinter，无法弹出选择框。")
            return None
        with tk_lock:
            root = None
            try:
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                root.update_idletasks()

                if file_type == "folder":
                    file_path = filedialog.askdirectory(parent=root, title="选择文件夹")
                else:
                    file_path = filedialog.askopenfilename(
                        parent=root,
                        title="选择 Excel 文件",
                        filetypes=[("Excel files", "*.xlsx;*.xlsm"), ("All files", "*.*")],
                    )
                return file_path or None
            except Exception as error:
                print(f"弹出选择框出错: {error}\n{traceback.format_exc()}")
                return None
            finally:
                if root:
                    try:
                        root.quit()
                    except Exception:
                        pass
                    try:
                        root.destroy()
                    except Exception:
                        pass
                gc.collect()

    @staticmethod
    def ask_saveas_filename(
        title: str = "保存配置文件",
        defaultextension: str = ".ini",
        initialfile: Optional[str] = None,
    ) -> Optional[str]:
        """弹出“另存为”对话框，返回用户选择的保存路径。
        参数：title — 窗口标题；defaultextension — 默认扩展名；initialfile — 初始文件名。
        返回：选中路径；取消或异常返回 None。
        """
        if tk is None or filedialog is None:
            print("当前环境无 tkinter，无法弹出另存为对话框。")
            return None
        with tk_lock:
            root = None
            try:
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                root.update_idletasks()
                file_path = filedialog.asksaveasfilename(
                    parent=root,
                    title=title,
                    defaultextension=defaultextension,
                    filetypes=GuiService.config_filetypes(),
                    initialfile=initialfile,
                )
                return file_path or None
            except Exception as error:
                print(f"另存为弹窗出错: {error}\n{traceback.format_exc()}")
                return None
            finally:
                if root:
                    try:
                        root.quit()
                    except Exception:
                        pass
                    try:
                        root.destroy()
                    except Exception:
                        pass
                gc.collect()

    @staticmethod
    def ask_open_config_filename(
        title: str = "选择要导入的配置文件",
        filetypes: Optional[List[tuple]] = None,
    ) -> Optional[str]:
        """弹出“打开文件”对话框，用于选择配置文件（.ini）。
        参数：title — 窗口标题；filetypes — 可选，文件类型列表，默认仅 .ini。
        返回：选中路径；取消或异常返回 None。
        """
        if tk is None or filedialog is None:
            print("当前环境无 tkinter，无法弹出打开文件对话框。")
            return None
        if filetypes is None:
            filetypes = GuiService.config_filetypes()
        with tk_lock:
            root = None
            try:
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                root.update_idletasks()
                file_path = filedialog.askopenfilename(
                    parent=root,
                    title=title,
                    filetypes=filetypes,
                )
                return file_path or None
            except Exception as error:
                print(f"打开文件弹窗出错: {error}\n{traceback.format_exc()}")
                return None
            finally:
                if root:
                    try:
                        root.quit()
                    except Exception:
                        pass
                    try:
                        root.destroy()
                    except Exception:
                        pass
                gc.collect()

    @staticmethod
    def parse_excel_sheets(file_path: str) -> Dict[str, Any]:
        """解析 Excel 文件的 sheet 名称列表。
        参数：file_path — Excel 文件路径。
        返回：{"type": "excel", "sheets": [...]} 或 {"type": "excel", "error": str}。
        """
        if os.path.basename(file_path).startswith("~$"):
            return {"type": "excel", "sheets": []}
        try:
            wb = ExcelService.open_workbook(file_path, read_only=True, data_only=True)
            sheets = list(wb.sheetnames)
            wb.close()
            return {"type": "excel", "sheets": sheets}
        except Exception as error:
            return {"type": "excel", "error": str(error)}

    @staticmethod
    def parse_can_testcases(file_path: str) -> Dict[str, Any]:
        """解析 CAN 文件中的 testcase 名称列表。
        参数：file_path — .can 文件路径。
        返回：{"type": "can", "testcases": [...]} 或 {"type": "can", "error": str}。
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as can_source_file:
                content = can_source_file.read()
            pattern = re.compile(r"testcase\s+(\w+)\s*\(", re.IGNORECASE)
            names = pattern.findall(content)
            return {"type": "can", "testcases": list(dict.fromkeys(names))}
        except Exception as error:
            return {"type": "can", "error": str(error)}

    @staticmethod
    def parse_xml_structure(file_path: str) -> Dict[str, Any]:
        """解析 XML 文件中的 testgroup 与 capltestcase 结构。
        参数：file_path — XML 文件路径。
        返回：{"type": "xml", "testgroups": [...], "capltestcases": [...]} 或 {"type": "xml", "error": str}。
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            result = {"type": "xml", "testgroups": [], "capltestcases": []}
            for elem in root.iter():
                if elem.tag.endswith("testgroup"):
                    title = elem.get("title") or elem.get("ident") or ""
                    if title:
                        result["testgroups"].append(title)
                elif elem.tag.endswith("capltestcase"):
                    name = elem.get("name") or ""
                    if name:
                        result["capltestcases"].append(name)
            return result
        except Exception as error:
            return {"type": "xml", "error": str(error)}

    @classmethod
    def parse_file_structure_single(cls, file_path: str) -> Dict[str, Any]:
        """解析单个文件的结构（Excel 的 sheet / CAN 的 testcase / XML 的 testgroup）。
        参数：file_path — 文件路径。
        返回：按类型返回 type + sheets|testcases|testgroups 或 error。
        """
        path_lower = file_path.lower()
        if path_lower.endswith((".xlsx", ".xlsm")):
            return cls.parse_excel_sheets(file_path)
        if path_lower.endswith(".can"):
            return cls.parse_can_testcases(file_path)
        if path_lower.endswith(".xml"):
            return cls.parse_xml_structure(file_path)
        return {"type": "unknown", "error": "不支持的文件格式，仅支持 Excel(.xlsx/.xlsm)、CAN(.can)、XML(.xml)"}

    @classmethod
    def parse_file_structure(cls, file_path: str, base_dir: str | None = None) -> Dict[str, Any]:
        """解析文件或文件夹下的 Excel/CAN/XML 结构（sheet、testcase、testgroup 等）。
        参数：path — 文件或文件夹路径；文件夹时遍历其下 Excel/CAN/XML。
             base_dir — 项目根目录；当 path 为相对路径时用于拼接解析。
        返回：{"success": True, "data": [...]} 或 {"success": False, "message": str}。
        """
        if not file_path or not file_path.strip():
            return {"success": False, "message": "未提供路径"}
        raw_path = file_path.strip()
        resolved_path = resolve_runtime_path(base_dir, raw_path)
        if not os.path.exists(resolved_path):
            return {
                "success": False,
                "message": f"路径不存在: {raw_path}（解析后: {resolved_path}）",
            }

        results: List[Dict[str, Any]] = []
        try:
            if os.path.isfile(resolved_path):
                item = cls.parse_file_structure_single(resolved_path)
                item["filename"] = os.path.basename(resolved_path)
                results.append(item)
            else:
                for root_dir, _, files in os.walk(resolved_path):
                    for filename in files:
                        if filename.startswith("~$"):
                            continue
                        file_path = os.path.join(root_dir, filename)
                        file_name_lower = filename.lower()
                        if file_name_lower.endswith((".xlsx", ".xlsm", ".can", ".xml")):
                            item = cls.parse_file_structure_single(file_path)
                            item["filename"] = filename
                            item["relpath"] = os.path.relpath(file_path, resolved_path)
                            results.append(item)
            return {"success": True, "data": results}
        except Exception as error:
            return {"success": False, "message": str(error)}
