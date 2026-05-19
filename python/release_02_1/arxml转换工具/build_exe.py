"""
独立打包脚本：用 PyInstaller 将 arxml_converter.py 打成单文件 exe。
本机若没有 PyInstaller，首次运行会自动通过 pip 安装（需联网）。

用法示例：
  python build_exe.py
  python build_exe.py -n arxml转换工具
  python build_exe.py -n "客户项目_ARXML工具"
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "arxml_converter.py"
DEFAULT_EXE_BASENAME = "arxml转换工具"


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
        return
    except ImportError:
        pass

    print("正在安装 PyInstaller（首次打包需要）…")
    pip = subprocess.run(
        [sys.executable, "-m", "pip", "install", "pyinstaller"],
        cwd=str(ROOT),
    )
    if pip.returncode != 0:
        print(
            "自动安装 PyInstaller 失败，请检查网络或手动执行: pip install pyinstaller",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "安装后仍无法加载 PyInstaller，请关闭终端重新打开后再执行本脚本。",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="打包 arxml_converter.py 为独立 exe（单文件、无控制台窗口）"
    )
    parser.add_argument(
        "-n",
        "--name",
        default=DEFAULT_EXE_BASENAME,
        metavar="名称",
        help=f"生成的 exe 主文件名（不要带 .exe），默认: {DEFAULT_EXE_BASENAME}",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="打包前删除 build/ 与 dist/ 目录，避免旧产物干扰",
    )
    parser.add_argument(
        "--noupx",
        action="store_true",
        help="传入 PyInstaller --noupx（部分环境可减少误报）",
    )
    args = parser.parse_args()

    if not ENTRY.is_file():
        print(f"未找到入口脚本: {ENTRY}", file=sys.stderr)
        sys.exit(1)

    ensure_pyinstaller()

    exe_name = args.name.strip()
    if not exe_name:
        print("exe 名称不能为空", file=sys.stderr)
        sys.exit(1)
    if exe_name.lower().endswith(".exe"):
        exe_name = exe_name[:-4]

    out_exe = ROOT / f"{exe_name}.exe"

    if args.clean:
        for folder in (ROOT / "build", ROOT / "dist"):
            if folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)
        if out_exe.is_file():
            out_exe.unlink()

    cmd: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--distpath",
        str(ROOT),
        "--name",
        exe_name,
        str(ENTRY),
    ]
    if args.noupx:
        cmd.append("--noupx")

    print("执行:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        sys.exit(result.returncode)

    if out_exe.is_file():
        print(f"完成: {out_exe}")
    else:
        print("PyInstaller 已结束，但未在项目根目录找到预期的 exe，请检查上方日志。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
