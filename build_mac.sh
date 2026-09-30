#!/bin/bash
# ============================================================
# macOS 一键构建：产出 dist/TailscaleConsole.app
#
# 用法：
#   ./build_mac.sh            只构建
#   ./build_mac.sh --install  构建后拷贝到 /Applications
#
# 说明：必须在 macOS 上执行。PyInstaller 不支持交叉编译，
#       .app 无法在 Windows / Linux 上打出来。
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
echo "==> Python: $($PY -V 2>&1)"

# 1) 虚拟环境（隔离，不污染系统 Python）
if [ ! -d .venv ]; then
  echo "==> 创建虚拟环境 .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2) 依赖
#    pywebview 在 macOS 上会自动带 pyobjc（Cocoa 后端）
echo "==> 安装依赖"
python -m pip install --upgrade pip wheel
python -m pip install pywebview pillow pyinstaller

# 3) 图标（生成 app.ico / app.icns / app.png）
echo "==> 生成图标"
python _make_icon.py

# 4) 打包
echo "==> 打包（约 1-3 分钟）"
python _build.py

APP="dist/TailscaleConsole.app"
if [ ! -d "$APP" ]; then
  echo "!! 未找到 $APP，构建失败"
  exit 1
fi

# 5) ad-hoc 签名 + 清除隔离属性
#    未签名的 .app 会被 Gatekeeper 拦（"来自身份不明的开发者"）。
#    这里用本地 ad-hoc 签名（-）让系统把它当作本机产物，能显著减少拦截。
echo "==> 签名并清除隔离属性"
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "   (跳过签名)"
xattr -cr "$APP" 2>/dev/null || true

echo
echo "==> 构建完成：$PWD/$APP"
echo "    双击即可运行。若仍提示无法打开：系统设置 → 隐私与安全性 → 仍要打开。"

# 6) 可选：装到 /Applications
if [ "${1:-}" = "--install" ]; then
  DEST="/Applications/Tailscale 控制台.app"
  echo "==> 安装到 $DEST"
  rm -rf "$DEST"
  cp -R "$APP" "$DEST"
  xattr -cr "$DEST" 2>/dev/null || true
  echo "    已安装。可在 Launchpad / 访达的应用程序里找到。"
fi
