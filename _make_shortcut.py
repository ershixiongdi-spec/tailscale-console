# -*- coding: utf-8 -*-
"""在桌面创建「Tailscale 控制台」快捷方式。

优先指向打包好的 exe；exe 不存在时退回 pythonw + app.py（不留控制台黑框）。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXE = ROOT / "dist" / "TailscaleConsole.exe"
PYW = Path(r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe")
ICON = ROOT / "web" / "app.ico"


def desktop_dir() -> Path:
    try:
        import win32com.shell.shell as shell
        import win32con
        return Path(shell.SHGetFolderPath(0, win32con.CSIDL_DESKTOP, None, 0))
    except Exception:
        return Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop"


def main() -> int:
    if not desktop_dir().is_dir():
        print("找不到桌面目录:", desktop_dir())
        return 1

    if EXE.is_file():
        target, args, workdir = str(EXE), "", str(EXE.parent)
    elif PYW.is_file():
        target, args, workdir = str(PYW), f'"{ROOT / "app.py"}"', str(ROOT)
    else:
        print("既没有 exe 也没有 pythonw，无法创建快捷方式")
        return 1

    lnk_path = desktop_dir() / "Tailscale 控制台.lnk"
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortCut(str(lnk_path))
    lnk.TargetPath = target
    lnk.Arguments = args
    lnk.WorkingDirectory = workdir
    lnk.Description = "Tailscale 设备与连接管理面板"
    if ICON.is_file():
        lnk.IconLocation = f"{ICON},0"
    lnk.Save()
    print("快捷方式 ->", lnk_path)
    print("指向     ->", target, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
