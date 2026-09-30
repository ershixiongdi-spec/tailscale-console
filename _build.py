# -*- coding: utf-8 -*-
"""跨平台打包脚本（替代原来的 _build_exe.py）。

产物：
  Windows -> dist/TailscaleConsole.exe
  macOS   -> dist/TailscaleConsole.app
  Linux   -> dist/TailscaleConsole

用法：python3 _build.py
前置：已安装 pyinstaller、pywebview、pillow（见 build_mac.sh / README）
"""
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
# ★ 产物名保持纯 ASCII：中文名交给快捷方式 / .app 重命名去显示，
#   避免 PyInstaller bootloader 处理非 ASCII 时出岔子。
NAME = "TailscaleConsole"
SYSTEM = platform.system()

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--clean",
    "--onefile",
    "--windowed",                 # Windows 不弹控制台；macOS 生成 .app 包
    f"--name={NAME}",
]

# 图标与 --add-data 分隔符都跟平台有关
if SYSTEM == "Windows":
    icon, sep = WEB / "app.ico", ";"
elif SYSTEM == "Darwin":
    icon, sep = WEB / "app.icns", ":"
    cmd.append("--osx-bundle-identifier=com.local.tailscale-console")
else:
    icon, sep = WEB / "app.png", ":"

if icon.is_file():
    cmd.append(f"--icon={icon}")
else:
    print(f"警告：没找到图标 {icon}，产物将使用默认图标")

cmd.append(f"--add-data={WEB}{sep}web")   # 把前端资源打进去

# pywebview 的后端按平台显式带上，否则打包后找不到渲染内核
for mod in {
    "Windows": ["webview.platforms.edgechromium", "clr_loader", "pythonnet"],
    "Darwin": ["webview.platforms.cocoa"],
}.get(SYSTEM, ["webview.platforms.qt", "webview.platforms.gtk"]):
    cmd.append(f"--hidden-import={mod}")
cmd.append("--collect-submodules=webview")

cmd.append(str(ROOT / "app.py"))

print("system   :", SYSTEM)
print("python   :", sys.executable)
print("command  :", " ".join(str(c) for c in cmd))
print("-" * 60)

res = subprocess.run(cmd, cwd=str(ROOT))

# 产物定位
if SYSTEM == "Darwin":
    target = ROOT / "dist" / f"{NAME}.app"
elif SYSTEM == "Windows":
    target = ROOT / "dist" / f"{NAME}.exe"
else:
    target = ROOT / "dist" / NAME


def dirsize(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


print("-" * 60)
if target.exists():
    size = dirsize(target) if target.is_dir() else target.stat().st_size
    print(f"OK -> {target}  ({size / 1048576:.1f} MB)")
else:
    print("未生成产物，检查上面的 PyInstaller 日志")
sys.exit(res.returncode)
