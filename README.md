# Tailscale 控制台（Windows / macOS 桌面版）

把 `console.tailscale.com/admin/machines` 那套网页后台，换成一个**本机双击就开的窗口程序**。

当前版本：**v1.2.1**　｜　适配 Tailscale 客户端 **1.102.3**　｜　支持 **Windows** 与 **macOS**（Apple Silicon / Intel 均可）

- 仓库：<https://github.com/ershixiongdi-spec/tailscale-console>
- Windows 免安装版（17 MB，无需 Python）：
  <https://github.com/ershixiongdi-spec/tailscale-console/releases/download/v1.2.1/TailscaleConsole.exe>
- 许可：MIT

---

## 零、macOS 用户读这段（构建 .app）

**先说一个硬限制**：`.app` **不能在 Windows 或 Linux 上打出来**。
PyInstaller 不支持交叉编译，macOS 的应用程序包只能在 macOS 上构建。
所以仓库里只有源码 + 构建脚本，没有现成的 Mac 版可下载——需要你在 Mac 上跑一条命令自己构建（约 2～3 分钟）。

### 步骤

```bash
# 1) 拿到源码
git clone https://github.com/ershixiongdi-spec/tailscale-console.git
cd tailscale-console

# 2) 一键构建（自动建虚拟环境、装依赖、生成图标、打包）
./build_mac.sh

# 想直接装进「应用程序」文件夹，就加 --install
./build_mac.sh --install
```

产物在 `dist/TailscaleConsole.app`，双击即可运行。脚本最后会做 **ad-hoc 签名**并清掉隔离属性，尽量避开 Gatekeeper 拦截。

### 前置条件

| 项目 | 要求 | 说明 |
|---|---|---|
| Python | 3.9+（自带或 Homebrew 装的都行） | 脚本会自建 `.venv`，不污染系统环境 |
| Tailscale 命令行 | `brew install tailscale` | **App Store 版 Tailscale 不带 CLI**，程序会提示"未找到" |
| 网络 | 能访问 PyPI | 首次要下 pywebview / PyInstaller（约 100 MB） |

程序会依次在 `/usr/local/bin`、`/opt/homebrew/bin`、`/Applications/Tailscale.app/Contents/MacOS/` 里找命令行工具，找不到会明确提示。

### 如果被系统拦住

第一次打开可能提示"来自身份不明的开发者"：

- 最省事：**右键点击 .app → 打开**，弹窗里选"打开"
- 或去：系统设置 → 隐私与安全性 → 下方"仍要打开"
- 或在本机构建后执行：`xattr -cr dist/TailscaleConsole.app`（`build_mac.sh` 已经帮你做了）

### Windows 与 Mac 的差异

| 方面 | Windows | macOS |
|---|---|---|
| 窗口内核 | Edge WebView2 | 系统 WKWebView（Cocoa） |
| 配置文件位置 | `%USERPROFILE%\.tailscale-console\` | `~/.tailscale-console/` |
| 崩溃日志 | 同上目录 `error.log` | 同左 |
| 桌面快捷方式 | `_make_shortcut.py` 建 `.lnk` | 把 `.app` 拷进 `/Applications` 即可 |
| 打包命令 | `python _build.py` | `python _build.py`（同一条，脚本自动识别平台） |

---

## 一、怎么启动（Windows）

**方式 A（推荐）**：双击桌面上的 **「Tailscale 控制台」** 快捷方式。

**方式 B**：进到本文件夹，双击 `start.bat`。

**方式 C**：双击 `dist\TailscaleConsole.exe`（独立程序，不依赖 Python）。

如果窗口没出来，双击 `debug.bat`，它会保留一个黑窗口把错误打印出来。

---

## 二、登录与注销

### 登录页
程序启动后先进入登录页，样式对齐官网 `login.tailscale.com`：

- 邮箱输入框 + **Sign in** 按钮
- **Sign in with Google / Microsoft / GitHub / Apple / passkey** 五个入口
- 底部显示控制台版本、本机 Tailscale 客户端版本，以及
  **下载最新版：https://tailscale.com/download**（点击用系统浏览器打开）

### 登录校验的是什么？（重要）
校验的是**本机 Tailscale 客户端真实登录了哪个账号**——不是随手编一个邮箱就能进。

| 本机 Tailscale 状态 | 登录页表现 | 点 Sign in 的结果 |
|---|---|---|
| 已登录 | 顶部绿色提示条：本机已登录 `xxx@yyy`，自动填好邮箱 | 邮箱与账号一致 → 直接进入 |
| 已登录 | 邮箱填错了 | 明确报错，并给出「改用正确账号」一键按钮 |
| 未登录（需认证） | 橙色提示条 + 「打开浏览器认证」按钮 | 引导去浏览器完成认证，**认证成功后本页自动进入** |

也就是说：能进得来，前提是这台机器上确实用该账号登录了 Tailscale。

### 注销
右上角红色 **「注销」** 按钮，弹窗里给两个选项：

| 选项 | 影响 |
|---|---|
| **仅注销本控制台**（推荐） | 清除本地登录状态，回到登录页。Tailscale 连接、设备都不受影响，随时再登进来。 |
| **同时从 Tailscale 登出** | 本机立刻离线，节点密钥作废，**必须重新认证才能回到 tailnet**。需要二次确认。 |

---

## 三、界面上能看到什么

### 顶栏
本机在线状态、主机名、Tailscale IP、刷新、主题切换、连接/断开、**当前登录账号（头像+邮箱）**、注销。

### 底部状态栏（常驻可见）
```
软件版本 v1.1.0 | Tailscale 客户端 1.102.3 | 账号 xxx@yyy        下载最新版 https://tailscale.com/download ↗
```

### 1. 设备页
- 所有设备一览：主机名、MagicDNS 域名、Tailscale IP、操作系统、在线/离线、最后在线时间。
- 绿点/灰点区分在线离线；离线设备显示「3 天前」这类相对时间。
- 连接方式是**直连**还是**经中继**（走 DERP，标出中继区域如 HKG/SFO/TOK）。
- 搜索（主机名 / IP / 域名 / 系统）、筛选（全部 / 在线 / 离线 / 出口节点）、排序。
- 每张卡片：**Ping**（延迟直接显示成标签）、**SSH 命令**、**设为出口 / 取消出口**、**详情**（完整字段 + 原始 JSON）。

### 2. 本机设置页
- 连接 / 断开：断开只是本机退出网络，不会把设备从 tailnet 删掉。
- 出口节点：下拉选择用哪台设备上网，可勾选「同时允许访问本地局域网」。
- 常用开关：接受子网路由、接受 DNS、ShieldsUp、Tailscale SSH、本机作为出口节点、自动检查更新。
- **软件版本与更新**：控制台版本、客户端版本、客户端路径、唯一设备编号 +
  下载最新版按钮 + 管理后台入口。

### 3. 网络诊断页
一键跑 `netcheck`：UDP 能否打洞、公网 IPv4、NAT 类型、最近中继，
以及到全球各地中继服务器的延迟排行（进度条可视化）。

### 4. 云端管理页（可选）
只有在需要「远程删除设备 / 改名 / 让密钥过期」时才需要 API Key：
管理后台 → Settings → Keys → Generate access token → 复制 `tskey-api-...` → 粘进输入框保存。

Key 保存在 `%USERPROFILE%\.tailscale-console\config.json`，只存在本机。

### 5. 运行日志页
每条命令的原文和输出都在这里，出问题可以直接复制给别人看。

---

## 四、安全说明

- 服务只监听 **127.0.0.1**，局域网内其他机器访问不到。
- 每次启动生成一次性令牌并注入页面；所有写操作必须带令牌，防止别的网页偷偷调用本机接口改你的网络。
- 校验 `Host` 头，防 DNS rebinding。
- **未登录时所有业务接口一律返回 401**，只有登录页需要的元信息接口对外开放。
- 所有 `tailscale` 写操作都走**参数白名单**（见 `tailscale_cli.py` 的 `SETTABLE_FLAGS`），不存在拼接命令被注入的可能。
- 打开外部链接只允许 `<tailscale.com>` 与 `login.tailscale.com` 域名，程序不会被当成任意跳板。
- 程序**从不直接读写** Tailscale 的配置文件，一切通过官方 `tailscale.exe` 完成。

---

## 五、文件结构

```
tailscale-console/
├─ start.bat              双击启动（优先用 exe）
├─ debug.bat              排障用，出错会留窗口显示
├─ app.py                 主程序：本地 HTTP 服务 + 窗口 + 登录接口
├─ tailscale_cli.py       命令行封装（只调用官方 tailscale.exe）
├─ web/                   界面
│  ├─ index.html          登录页 + 主界面
│  ├─ style.css
│  ├─ app.js
│  └─ app.ico
├─ dist/
│  └─ TailscaleConsole.exe   打包好的独立程序
├─ _build.py              跨平台打包（Windows→exe，macOS→.app）
├─ build_mac.sh           macOS 一键构建（建 venv + 装依赖 + 打包 + 签名）
├─ _make_icon.py          生成 app.ico / app.icns / app.png
└─ _verify_ui.py          渲染自检：逐页截图 + 抓前端报错
```

配置和缓存目录：

- Windows：`%USERPROFILE%\.tailscale-console\`
- macOS / Linux：`~/.tailscale-console/`

（删掉这个文件夹 = 清空登录状态、API Key 和偏好，不影响 Tailscale 本身）

---

## 六、环境要求

| 项目 | 要求 | 当前状态 |
|---|---|---|
| Tailscale 客户端 | 已安装并登录 | ✅ `C:\Program Files\Tailscale\tailscale.exe` 1.102.3 |
| Edge WebView2 运行时 | Win10/11 一般自带 | ✅ 147.0.3912.912 |
| Python（仅源码方式需要） | 3.11+，装了 pywebview | ✅ 托管环境已配好 |
| exe 方式 | 无额外要求 | ✅ |

macOS 侧对应要求：Python 3.9+、Tailscale 命令行（`brew install tailscale`，App Store 版不带）、
系统自带 WKWebView 渲染（无需额外运行时）。详见「零、macOS 用户读这段」。

---

## 七、常见问题

**Q：登录页说「本机 Tailscale 尚未登录」怎么办？**
点橙条里的「打开浏览器认证」，在浏览器里用你的 Tailscale 账号完成认证。
认证成功后不用管它，登录页每 3 秒自动检查一次，成功了会自动进入。

**Q：邮箱输错了会怎样？**
会明确告诉你本机登录的是哪个账号，并给一个「改用正确账号」的按钮，一键换成对的。

**Q：注销会不会把我踢下线？**
选「仅注销本控制台」不会。只有选「同时从 Tailscale 登出」才会，而且会让你确认两次。

**Q：窗口是白的 / 一直转圈？**
用 `debug.bat` 启动看报错。多半是 WebView2 运行时缺失，去微软官网装
「Microsoft Edge WebView2 Runtime」即可；程序检测不到原生窗口时会自动退回 Chrome 应用窗口。

**Q：设备列表是空的？**
先确认 `tailscale status` 在命令行能出结果。如果本机 Tailscale 处于需登录状态，设备列表自然是空的。

**Q：它会不会偷偷动我的网络设置？**
不会。所有写操作都是你在界面上主动点击才触发，且页面会先弹确认框。

---

## 八、版本历史

| 版本 | 内容 |
|---|---|
| **v1.2.1** | 修复 `Stopped` 状态被误判为「未登录」（改为以账号是否存在为准）；新增「启动 Tailscale 客户端」按钮（守护进程停了可一键拉起）；`api_start_client` 改为跨平台实现 |
| v1.2.0 | 支持 macOS：跨平台找 Tailscale 命令行、浏览器退回路径跨平台、图标产出 `.icns`、新增 `build_mac.sh` 一键构建 `.app`；`_build_exe.py` 统一为跨平台 `_build.py` |
| v1.1.0 | 新增登录页（对齐官网样式）、账号显示与注销按钮、底部状态栏（版本号 + 下载链接）、软件版本卡片；接口加登录门禁 |
| v1.0.0 | 首版：设备总览、本机设置、网络诊断、云端管理、运行日志 |

### 开发时踩到的坑（备查）

1. **`tailscale login` 是破坏性命令**。帮助写的是 "logs this machine in"，但在**已登录**的机器上执行，
   会先清掉 node key、把状态打成 `NeedsLogin`、清空账号信息，等于直接把设备踢下线。
   要拿认证链接只能**只读** `status --json` 的 `AuthURL` 字段（前提是已经处于需登录状态）。
2. `tailscale up --json` 会触发「必须列全所有非默认设置」的检查，不能拿来做只读查询。
3. 登出状态下 `status --json` 里 `Self` 是空壳（无 ID），前端要过滤掉，否则会多出一张「无地址」的假设备卡。
4. 深色模式下，`fill` 属性写在 `<svg>` 上而不是 `<path>` 上，改色选择器别写错层级。
