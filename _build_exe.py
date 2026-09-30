# -*- coding: utf-8 -*-
"""把控制台打包成单文件 exe（Windows）。

产物：dist/Tailscale控制台.exe
用法：python _build_exe.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 注意：exe 文件名保持纯 ASCII。中文名交给桌面快捷方式去显示，
#       避免 PyInstaller bootloader 处理非 ASCII 文件名时出岔子。
NAME = "TailscaleConsole"

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--clean",
    "--onefile",
    "--windowed",                      # 不弹控制台窗口
    f"--name={NAME}",
    f"--icon={ROOT / 'web' / 'app.ico'}",
    f"--add-data={ROOT / 'web'};web",  # 前端资源打进去
    # pywebview 的后端要显式带上
    "--hidden-import=webview.platforms.edgechromium",
    "--hidden-import=clr_loader",
    "--hidden-import=pythonnet",
    "--collect-submodules=webview",
    str(ROOT / "app.py"),
]

print("run:", " ".join(cmd))
res = subprocess.run(cmd, cwd=str(ROOT))
print("pyinstaller exit =", res.returncode)

exe = ROOT / "dist" / f"{NAME}.exe"
if exe.is_file():
    print(f"OK -> {exe}  ({exe.stat().st_size / 1048576:.1f} MB)")
else:
    print("未生成 exe，检查上面的日志")
sys.exit(res.returncode)
