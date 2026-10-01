# 交接文档：在 macOS 上完成 .app 构建

> 这份文档是给 **Mac 上的 WorkBuddy 会话** 看的。
> 起因：本项目在 Windows 上开发，但 macOS 的 `.app` 无法在 Windows 上打出来
> （PyInstaller 不支持交叉编译），所以剩余工作必须在 Mac 上完成。
> 对话历史不会跨机器同步，因此把全部必要背景写在这里，**请先读完再动手**。

---

## 一、一句话目标

把 `tailscale-console`（一个封装本机 Tailscale 命令行的桌面图形控制台）
在 macOS 上打包成 `TailscaleConsole.app`，能双击打开、能看到设备列表。

**这是唯一剩余的任务。** 代码层面的跨平台改造已经在 Windows 侧做完并推送。

---

## 二、当前进度

| 项目 | 状态 |
|---|---|
| 跨平台代码改造（v1.2.0） | ✅ 已完成，已推送到 main |
| Windows 版 exe（16.6 MB） | ✅ 已发布在 v1.2.0 Release |
| `build_mac.sh` 一键构建脚本 | ✅ 已写好（未真机验证过） |
| `_build.py` 跨平台打包 | ✅ 已写好，Windows 侧验证通过 |
| 图标 `.icns` | ✅ `_make_icon.py` 会生成 |
| **macOS 上实际构建 .app** | ⏸ **待做（本任务）** |
| **macOS 上真机跑通验收** | ⏸ **待做（本任务）** |

仓库：https://github.com/ershixiongdi-spec/tailscale-console
分支：`main`　｜　许可：MIT

---

## 三、在 Mac 上执行（主流程）

```bash
cd ~
git clone https://github.com/ershixiongdi-spec/tailscale-console.git
cd tailscale-console
./build_mac.sh --install
```

脚本会自动完成：建虚拟环境 → 装依赖 → 生成图标 → PyInstaller 打包 →
ad-hoc 签名 → 清除隔离属性 → 拷进 `/Applications`。

不加 `--install` 则只构建到 `dist/TailscaleConsole.app`。

预计耗时 2–5 分钟（首次要装 pywebview + pyobjc + PyInstaller）。

---

## 四、前置条件（最容易卡在这里）

| 条件 | 检查命令 | 不满足怎么办 |
|---|---|---|
| Python 3.9+ | `python3 -V` | `brew install python@3.12`，或改用系统自带（Apple Silicon 需装 Xcode Command Line Tools：`xcode-select --install`） |
| **Tailscale 命令行** | `which tailscale` | **`brew install tailscale`** |
| 能联网装 pip 包 | `pip download --no-deps pywebview -d /tmp` | 检查代理；Homebrew 换镜像源 |

### ⚠️ 头号坑：App Store 版 Tailscale 不带命令行工具

Mac 上从 **App Store** 装的 Tailscale 是沙盒版本，**没有 `tailscale` 命令行**，
程序会提示"未找到 tailscale 命令行"。必须额外执行：

```bash
brew install tailscale
```

代码里 `tailscale_cli.py` 的探测顺序是：
`/usr/local/bin/tailscale` → `/opt/homebrew/bin/tailscale` →
`/Applications/Tailscale.app/Contents/MacOS/Tailscale`（并尝试其内嵌 CLI）

---

## 五、已知坑与对策（Windows 侧已踩过，别重复踩）

1. **PyInstaller 不能交叉编译** —— `.app` 只能在 macOS 上构建，不要试图在别的系统生成。
2. **Gatekeeper 拦截** —— 未签名的 `.app` 会报"来自身份不明的开发者"。
   脚本已做 `codesign --force --deep --sign -` + `xattr -cr`。
   若仍被拦：系统设置 → 隐私与安全性 → 点「仍要打开」。
3. **换行符** —— 仓库有 `.gitattributes`，`.sh` 强制 LF。
   若报 `bad interpreter: /bin/bash^M`，说明换行符被污染，执行 `sed -i '' 's/\r$//' build_mac.sh`。
4. **架构** —— Apple Silicon 构建出 arm64，Intel 构建出 x86_64，
   两者不通用。若要将 .app 拷到另一台不同芯片的 Mac，需在对应机器上重新构建。
5. **`--windowed` 在 macOS 上产出 .app**，不是裸二进制，产物路径是 `dist/TailscaleConsole.app`。
6. **产物名保持纯 ASCII**（`TailscaleConsole`）。中文名交给 `/Applications` 下的重命名去显示，
   PyInstaller bootloader 处理非 ASCII 容易出问题。

---

## 六、验收清单

- [ ] `dist/TailscaleConsole.app` 存在，大小合理（预期 20–40 MB）
- [ ] 双击能打开图形窗口（不是闪退、不是报错弹窗）
- [ ] 登录页正常显示，能看到本机 Tailscale 账号或"打开浏览器认证"提示
- [ ] 进入后**设备列表有内容**（说明 CLI 探测成功）
- [ ] 点一下某台设备的 Ping，能返回延迟
- [ ] 网络诊断页能跑出中继延迟列表
- [ ] `/Applications/Tailscale 控制台.app` 可从 Launchpad 启动

---

## 七、报错速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `python3: command not found` | 没装 Python | `xcode-select --install` 或 `brew install python@3.12` |
| 程序内提示"未找到 tailscale 命令行" | 装的是 App Store 版 | `brew install tailscale` 后重开程序 |
| `ModuleNotFoundError: webview` | 依赖装进了别的 Python | 确认用了 `.venv/bin/activate`（脚本已处理） |
| PyInstaller 报 `RecursionError` | 依赖树太深 | 在 `TailscaleConsole.spec` 里加 `import sys; sys.setrecursionlimit(5000)`，或运行时加 `--noconsole` 无关 |
| 打包成功但打开闪退 | 前端资源没打进去 | 检查 `_build.py` 的 `--add-data`，macOS 分隔符必须是 `:`（已处理） |
| 窗口白屏 | pyobjc 后端缺失 | `pip install pyobjc-framework-Cocoa pyobjc-framework-WebKit` |
| `操作不被允许` / 权限 |  quarantine 属性 | `xattr -cr dist/TailscaleConsole.app` |

---

## 八、项目结构（速览）

```
app.py              后端：本地 HTTP 服务（127.0.0.1）+ pywebview 窗口 + 全部 API
tailscale_cli.py    封装 tailscale.exe / tailscale 命令行调用（跨平台探测）
web/                前端：index.html / style.css / app.js
_build.py           跨平台打包（自动选平台参数）
build_mac.sh        macOS 一键构建入口
_make_icon.py       生成 app.ico / app.icns / app.png
_verify_ui.py       Playwright 渲染自检（可选，需 Chrome）
README.md           完整使用说明
```

配置与日志目录：`~/.tailscale-console/`（崩溃日志在 `error.log`）

---

## 九、构建成功后

1. 把结果（成功/失败 + 报错原文）反馈给用户在 Windows 侧的会话，或直接在本仓库提 issue。
2. 若要发布：把 `.app` 打成 zip 后作为 asset 上传到 GitHub Release
   （单个文件超过 50 MB 需注意，一般 20–40 MB 无压力）。
   注意：**未经 Apple 开发者签名的 .app 分发给别人仍会被 Gatekeeper 拦**，
   分发时要在 Release 说明里写明"右键 → 打开"的绕过方法。

---

## 十、安全提示

- 代码里**没有任何硬编码密钥**。云端管理用的 API Key 由用户运行时输入，
  存在 `~/.tailscale-console/config.json`，不在仓库内。
- 仓库是**公开**的。不要往里提交 token、密钥、个人 tailnet 结构。
