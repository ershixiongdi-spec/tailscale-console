# Windows 重新打包说明（给师哥）

## 目标
在 Windows 旧电脑上用最新代码（含 Stopped 修复 + 启动客户端功能）重新打包 `TailscaleConsole.exe`，然后发新 release v1.2.1。

## 前置条件
- Windows 10/11 旧电脑
- 能联网（下载依赖约 100MB）
- 已装 Python 3.9+（如果没有，从 https://www.python.org/downloads/windows/ 下载安装，**勾选 "Add Python to PATH"**）

## 步骤

### 1. 把仓库拷到 Windows 电脑

两个办法选一个：

**办法 A（U盘拷，推荐）：**
1. 在 Mac 上把仓库打包成 zip（下面会自动生成）
2. U盘拷到 Windows 电脑
3. 解压到任意目录（路径不要有中文，比如 `C:\tailscale-console`）

**办法 B（Windows 上直接 git clone，需装 Git）：**
```cmd
git clone https://github.com/ershixiongdi-spec/tailscale-console.git
cd tailscale-console
```

### 2. 双击 build_windows.bat

```
双击 build_windows.bat
```

脚本会自动：
1. 检测 Python
2. 建 .venv 虚拟环境
3. 装 pyinstaller + pywebview + pillow（首次约 2-3 分钟）
4. 打包 → 产物在 `dist\TailscaleConsole.exe`（约 17MB）

**看到 `Build complete!` 就成功了。**

### 3. 验证 exe 能跑

双击 `dist\TailscaleConsole.exe`，应弹出窗口显示登录页或主界面。
首次可能弹 SmartScreen → 点"更多信息"→"仍要运行"。

### 4. 把 exe 传回 Mac（或直接在 Windows 上传）

**如果 Windows 能联网且装了 gh CLI（推荐）：**
```cmd
gh release create v1.2.1 dist\TailscaleConsole.exe ^
  --title "v1.2.1 — Mac Stopped 修复 + 启动客户端功能" ^
  --notes "修复 macOS Stopped 状态误判未登录；新增启动客户端按钮；build_mac.sh 自动安装 Tailscale CLI"
```

**如果 Windows 没有 gh：**
把 `dist\TailscaleConsole.exe` 用 U盘/微信/邮箱传回 Mac，我在 Mac 上用 gh CLI 上传发 release。

## 故障排查

| 问题 | 解法 |
|---|---|
| `Python not found` | 装 Python 时勾 "Add Python to PATH"，或用 `py -3` 启动器 |
| `pip install 超时` | 换源：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller pywebview pillow` |
| `Build failed` | 看终端里 PyInstaller 的报错，通常是依赖没装全或网络中断 |
| 双击 exe 闪退 | 右键 → 用 PowerShell 运行，看报错；通常是缺 Tailscale 客户端 |

## 关于 v1.2.1 release

我在 Mac 上会先把 tag 和 release 草稿建好（不含 exe），你在 Windows 打包出 exe 后上传到这个 release 即可。
