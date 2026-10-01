# -*- coding: utf-8 -*-
"""
Tailscale 桌面控制台 —— 主程序

它做三件事：
  1. 在本机 127.0.0.1 上起一个 HTTP 服务（固定端口 8756，被占用就顺延），
     提供界面静态文件和一组 JSON 接口。
  2. 用 pywebview（Windows 上是 Edge WebView2 内核）开一个原生窗口来显示界面。
  3. 万一 pywebview 起不来，自动退回 Chrome / Edge 的「应用模式」窗口，保证一定可用。

安全设计：
  * 只监听 127.0.0.1，外网访问不到。
  * 每次启动生成一次性令牌，注入页面；所有写操作必须带这个令牌，防止别的网页
    偷偷调用本机接口动你的网络。
  * 校验 Host 头，防 DNS rebinding。
  * 所有 tailscale 写操作的参数都走白名单（见 tailscale_cli.SETTABLE_FLAGS）。
"""
from __future__ import annotations

import json
import mimetypes
import os
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import tailscale_cli as ts

APP_NAME = "Tailscale 控制台"
APP_VERSION = "1.2.1"

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"

DOWNLOAD_URL = "https://tailscale.com/download"
LOGIN_START_URL = "https://login.tailscale.com/start"
ADMIN_MACHINES_URL = "https://console.tailscale.com/admin/machines"
CONSOLE_URL = "https://console.tailscale.com/"

# 打包成 exe 后，资源被解到临时目录；源码运行时就是脚本所在目录
if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    BASE_DIR = Path(__file__).resolve().parent

WEB_DIR = BASE_DIR / "web"
PREFERRED_PORT = 8756
TOKEN = secrets.token_urlsafe(24)

# 配置目录：Windows 看 USERPROFILE，macOS/Linux 看 HOME，都没有才回落到 Path.home()
CONFIG_DIR = Path(
    os.environ.get("USERPROFILE") or os.environ.get("HOME") or str(Path.home())
) / ".tailscale-console"
CONFIG_FILE = CONFIG_DIR / "config.json"
ERROR_LOG = CONFIG_DIR / "error.log"

API_BASE = "https://api.tailscale.com/api/v2"


def _append_log(text: str) -> str:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with ERROR_LOG.open("a", encoding="utf-8") as fh:
            fh.write(text)
        return str(ERROR_LOG)
    except Exception:
        return text


def log_note(where: str, message: str) -> None:
    """记一条普通日志（用来还原启动过程）。"""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _append_log(f"[{stamp}] {where}: {message}\n")


def log_error(where: str, exc: BaseException) -> str:
    """把异常写进日志文件。

    打包成 exe 后是 --windowed，没有控制台，出错时什么都看不到；
    所以任何异常都必须落盘，否则用户只能看到一个窗口一闪而过。
    """
    import traceback
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    text = f"\n===== {stamp} [{where}] =====\n{traceback.format_exc()}"
    return _append_log(text)


# --------------------------------------------------------------------------- #
# 本地配置（云端 API Key 等）
# --------------------------------------------------------------------------- #

def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return value[:3] + "***"
    return f"{value[:10]}…{value[-4:]}"


# --------------------------------------------------------------------------- #
# 登录会话
#
# 这里校验的是「本机 Tailscale 客户端真实登录了哪个账号」——
# 也就是说，能通过登录的前提是这台机器上确实用该账号登录了 Tailscale。
# 会话本身只存本地（config.json），注销即清除；它不是密码，不承担抗暴力破解的职责，
# 真正的身份凭证始终在 tailscaled 手里。
# --------------------------------------------------------------------------- #

def get_session() -> dict:
    sess = load_config().get("session") or {}
    return sess if sess.get("login") else {}


def is_logged_in() -> bool:
    return bool(get_session().get("login"))


def set_session(account_info: dict, method: str) -> dict:
    cfg = load_config()
    sess = {
        "login": account_info.get("login", ""),
        "name": account_info.get("name") or account_info.get("login", ""),
        "pic": account_info.get("pic", ""),
        "since": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "method": method or "current",
    }
    cfg["session"] = sess
    save_config(cfg)
    return sess


def clear_session() -> None:
    cfg = load_config()
    cfg.pop("session", None)
    save_config(cfg)


_VERSION_CACHE = {"at": 0.0, "value": ""}


def client_version() -> str:
    """Tailscale 客户端版本，带 10 分钟缓存（登录页会轮询，别每次都起进程）。"""
    now = time.time()
    if _VERSION_CACHE["value"] and now - _VERSION_CACHE["at"] < 600:
        return _VERSION_CACHE["value"]
    res = ts.version()
    lines = [ln.strip() for ln in (res.get("out") or "").splitlines() if ln.strip()]
    _VERSION_CACHE["value"] = lines[0] if lines else ""
    _VERSION_CACHE["at"] = now
    return _VERSION_CACHE["value"]


def meta_payload() -> dict:
    return {
        "app": {"name": APP_NAME, "version": APP_VERSION},
        "client": {
            "installed": bool(ts.TS_EXE),
            "version": client_version() or "未检测到",
            "exe": ts.TS_EXE or "",
        },
        "links": {
            "download": DOWNLOAD_URL,
            "login": LOGIN_START_URL,
            "admin": ADMIN_MACHINES_URL,
            "console": CONSOLE_URL,
        },
    }


# --------------------------------------------------------------------------- #
# Tailscale 云端 API（可选功能，需要用户自己填 API Key）
# --------------------------------------------------------------------------- #

def cloud_request(path: str, api_key: str, method: str = "GET", payload: dict | None = None,
                  timeout: int = 25) -> dict:
    """调用 api.tailscale.com。先试系统代理，失败再直连。"""
    import urllib.error
    import urllib.request

    url = API_BASE + path
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    last_err = None

    for use_proxy in (True, False):
        request = urllib.request.Request(url, data=body, method=method)
        request.add_header("Authorization", f"Bearer {api_key}")
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        handler = urllib.request.ProxyHandler() if use_proxy else urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(handler)
        try:
            with opener.open(request, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                data = json.loads(raw) if raw.strip() else {}
                return {"ok": True, "status": resp.status, "data": data}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"message": raw[:400]}
            return {
                "ok": False,
                "status": exc.code,
                "err": parsed.get("message") or f"HTTP {exc.code}",
                "data": parsed,
            }
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue

    return {"ok": False, "status": 0, "err": f"网络请求失败：{last_err}"}


# --------------------------------------------------------------------------- #
# 端口选择
# --------------------------------------------------------------------------- #

def pick_port(preferred: int = PREFERRED_PORT) -> int:
    """尽量用固定端口（换端口会让页面存储域变化），被占了就往后找。"""
    for port in [preferred, *range(preferred + 1, preferred + 20)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# --------------------------------------------------------------------------- #
# HTTP 处理
# --------------------------------------------------------------------------- #

class Handler(BaseHTTPRequestHandler):
    server_version = "TailscaleConsole/1.0"
    protocol_version = "HTTP/1.1"

    # ---------- 基础工具 ---------- #

    def log_message(self, fmt, *args):  # 静音：别往控制台刷日志
        pass

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost", "[::1]", "")

    def _token_ok(self) -> bool:
        return self.headers.get("X-TS-Token") == TOKEN

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, val in (extra or {}).items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0 or length > 2_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8", "replace"))
        except Exception:
            return {}

    def _need_session(self) -> bool:
        """未登录时拒绝访问，并让前端知道该弹登录页。"""
        if is_logged_in():
            return True
        self._json({"ok": False, "err": "尚未登录", "need_login": True}, 401)
        return False

    # ---------- 路由 ---------- #

    def do_GET(self):  # noqa: N802
        if not self._host_ok():
            self._json({"ok": False, "err": "Host 校验失败"}, 403)
            return
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._serve_index()
            elif path.startswith("/static/"):
                self._serve_static(path[len("/static/"):])
            elif path == "/api/meta":
                self._json(self.api_meta())
            elif path == "/api/auth/state":
                self._json(self.api_auth_state())
            elif path == "/api/bootstrap":
                if self._need_session():
                    self._json(self.api_bootstrap())
            elif path == "/api/live":
                if self._need_session():
                    self._json(self.api_live())
            else:
                self._json({"ok": False, "err": "未知路径"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "err": f"服务端异常：{exc}"}, 500)

    def do_POST(self):  # noqa: N802
        if not self._host_ok():
            self._json({"ok": False, "err": "Host 校验失败"}, 403)
            return
        if not self._token_ok():
            self._json({"ok": False, "err": "令牌校验失败，请重启程序"}, 403)
            return
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            # --- 无需登录 ---
            if path == "/api/auth/login":
                self._json(self.api_auth_login(body))
            elif path == "/api/auth/open":
                self._json(self.api_auth_open(body))
            elif path == "/api/start-client":
                self._json(self.api_start_client(body))
            # --- 需要登录 ---
            elif path == "/api/auth/logout":
                if self._need_session():
                    self._json(self.api_auth_logout(body))
            elif path == "/api/control":
                if self._need_session():
                    self._json(self.api_control(body))
            elif path == "/api/ping":
                if self._need_session():
                    self._json(self.api_ping(body))
            elif path == "/api/netcheck":
                if self._need_session():
                    self._json(self.api_netcheck())
            elif path == "/api/config":
                if self._need_session():
                    self._json(self.api_config(body))
            elif path == "/api/cloud/devices":
                if self._need_session():
                    self._json(self.api_cloud_devices(body))
            elif path == "/api/cloud/op":
                if self._need_session():
                    self._json(self.api_cloud_op(body))
            elif path == "/api/open":
                if self._need_session():
                    self._json(self.api_open(body))
            else:
                self._json({"ok": False, "err": "未知路径"}, 404)
        except ValueError as exc:
            self._json({"ok": False, "err": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "err": f"服务端异常：{exc}"}, 500)

    # ---------- 静态文件 ---------- #

    def _serve_index(self) -> None:
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("__TS_TOKEN__", TOKEN).replace("__APP_VERSION__", APP_VERSION)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _serve_static(self, rel: str) -> None:
        target = (WEB_DIR / rel).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            self._json({"ok": False, "err": "文件不存在"}, 404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    # ---------- 接口实现 ---------- #

    def api_meta(self) -> dict:
        return {"ok": True, **meta_payload()}

    def api_auth_state(self) -> dict:
        """登录页和主界面都会轮询这个接口。无需登录即可访问。"""
        acct = ts.account()
        sess = get_session()

        # 本机 Tailscale 换了账号 -> 旧会话作废，强制重新登录
        logins = [a.get("login", "").lower() for a in acct.get("accounts", [])]
        if sess and logins and sess.get("login", "").lower() not in logins:
            clear_session()
            sess = {}

        return {
            "ok": True,
            "logged_in": bool(sess),
            "session": sess or None,
            "tailscale": acct,
            "meta": meta_payload(),
        }

    def api_auth_login(self, body: dict) -> dict:
        method = str(body.get("method") or "current").strip()
        acct = ts.account()

        # 本机 Tailscale 没登录：引导去浏览器完成认证，不能凭空放行
        if not acct.get("logged_in"):
            return {
                "ok": False,
                "need_browser_auth": True,
                "auth_url": acct.get("auth_url") or LOGIN_START_URL,
                "backend_state": acct.get("backend_state"),
                "err": "本机 Tailscale 尚未登录，请先在浏览器里完成认证。",
            }

        accounts = acct.get("accounts") or []
        if not accounts:
            return {"ok": False, "err": "读不到本机 Tailscale 账号信息，请确认 Tailscale 服务正在运行。"}

        if method == "email":
            email = str(body.get("email") or "").strip().lower()
            if not email:
                raise ValueError("请输入邮箱地址")
            hit = next((a for a in accounts if (a.get("login") or "").lower() == email), None)
            if not hit:
                return {
                    "ok": False,
                    "err": f"本机 Tailscale 登录的不是这个账号。当前账号：{accounts[0].get('login', '')}",
                    "hint": accounts[0].get("login", ""),
                }
            chosen = hit
        else:
            chosen = accounts[0]

        sess = set_session(chosen, method)
        return {"ok": True, "session": sess, "tailscale": acct}

    def api_auth_logout(self, body: dict) -> dict:
        mode = str(body.get("mode") or "lock").strip()
        who = get_session().get("login", "")
        clear_session()

        if mode == "tailscale":
            res = ts.logout()
            res["mode"] = "tailscale"
            res["who"] = who
            return res

        return {
            "ok": True,
            "mode": "lock",
            "who": who,
            "cmd": "清除本控制台的登录会话（未触碰 Tailscale）",
            "out": "已注销。设备仍留在 tailnet 中，Tailscale 连接不受影响。",
        }

    def api_start_client(self, body: dict) -> dict:
        """拉起 Tailscale 客户端，让 tailscaled 守护进程恢复运行。无需登录。

        场景：BackendState=Stopped（守护进程停了）时，前端会显示
        「启动 Tailscale 客户端」按钮，点击调这个接口。

        为什么必须分平台写：这个功能是 mac 侧加的，原实现硬编码了
        /Applications/Tailscale.app 并调用 macOS 专有的 `open -a`，
        在 Windows 上必然报"未找到"。三家的启动方式完全不同：
          macOS   -> open -a /Applications/Tailscale.app
          Windows -> tailscale-ipn.exe（GUI 托盘程序，会自己拉起 tailscaled）
          Linux   -> systemctl start tailscaled
        """
        # ---------- macOS ----------
        if IS_MACOS:
            app_path = "/Applications/Tailscale.app"
            if not os.path.exists(app_path):
                return {
                    "ok": False,
                    "err": "未找到 /Applications/Tailscale.app，请先安装 Tailscale 客户端。",
                }
            try:
                # open -a 是异步的，立即返回；Tailscale.app 会自己拉起 tailscaled
                subprocess.Popen(
                    ["open", "-a", app_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {
                    "ok": True,
                    "msg": "已尝试启动 Tailscale 客户端，守护进程正在就绪，请稍候。",
                }
            except Exception as e:
                return {"ok": False, "err": f"启动失败：{e}"}

        # ---------- Windows ----------
        if IS_WINDOWS:
            # tailscale-ipn.exe 是带托盘图标的 GUI 客户端，启动它会拉起 tailscaled。
            # 优先从已探测到的 tailscale.exe 同目录推导，这样自定义安装路径也能命中。
            candidates = []
            if ts.TS_EXE:
                candidates.append(Path(ts.TS_EXE).with_name("tailscale-ipn.exe"))
            candidates += [
                Path(r"C:\Program Files\Tailscale\tailscale-ipn.exe"),
                Path(r"C:\Program Files (x86)\Tailscale\tailscale-ipn.exe"),
            ]
            seen, target = set(), None
            for c in candidates:
                key = str(c).lower()
                if key in seen:
                    continue
                seen.add(key)
                if c.is_file():
                    target = c
                    break
            if not target:
                return {
                    "ok": False,
                    "err": (
                        "未找到 Tailscale 客户端（tailscale-ipn.exe）。"
                        "请确认已安装 Tailscale，或手动启动后再点「刷新状态」。"
                    ),
                }
            try:
                subprocess.Popen(
                    [str(target)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=ts.CREATE_NO_WINDOW,  # 不弹黑框
                )
                return {
                    "ok": True,
                    "msg": "已尝试启动 Tailscale 客户端，守护进程正在就绪，请稍候。",
                }
            except Exception as e:
                return {"ok": False, "err": f"启动失败：{e}"}

        # ---------- Linux ----------
        try:
            subprocess.Popen(
                ["systemctl", "start", "tailscaled"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"ok": True, "msg": "已尝试启动 tailscaled 服务，请稍候。"}
        except Exception as e:
            return {"ok": False, "err": f"启动失败：{e}"}

    def api_auth_open(self, body: dict) -> dict:
        """打开 Tailscale 官方页面。只允许 tailscale.com 域名，防止被当成任意跳板。"""
        kind = str(body.get("kind") or "").strip()
        urls = {
            "login": LOGIN_START_URL,
            "download": DOWNLOAD_URL,
            "admin": ADMIN_MACHINES_URL,
            "console": CONSOLE_URL,
        }
        url = urls.get(kind, "")
        if kind == "auth":
            url = str(body.get("url") or "")
            if not url.startswith("https://login.tailscale.com/"):
                raise ValueError("认证地址不合法")
        if not url:
            raise ValueError("未知的链接类型")
        webbrowser.open(url)
        return {"ok": True, "url": url}

    def api_bootstrap(self) -> dict:
        stat = ts.status()
        pref = ts.prefs()
        cfg = load_config()
        return {
            "ok": True,
            "app": {"name": APP_NAME, "version": APP_VERSION},
            "exe": ts.TS_EXE,
            "cli_version": client_version(),
            "session": get_session() or None,
            "meta": meta_payload(),
            "status": stat.get("data"),
            "status_raw": stat.get("out", ""),
            "status_err": None if stat.get("data") else (stat.get("err") or "无法获取设备状态"),
            "prefs": pref.get("data"),
            "prefs_err": None if pref.get("data") else pref.get("err"),
            "cloud": {
                "has_key": bool(cfg.get("api_key")),
                "key_masked": masked(cfg.get("api_key", "")),
                "tailnet": cfg.get("tailnet", "-") or "-",
            },
        }

    def api_live(self) -> dict:
        stat = ts.status()
        pref = ts.prefs()
        return {
            "ok": bool(stat.get("data")),
            "status": stat.get("data"),
            "prefs": pref.get("data"),
            "err": stat.get("err") or pref.get("err"),
        }

    def api_control(self, body: dict) -> dict:
        action = (body.get("action") or "").strip()
        if action == "connect":
            return ts.connect()
        if action == "disconnect":
            return ts.disconnect()
        if action == "set":
            pairs = body.get("flags")
            if not isinstance(pairs, list):
                raise ValueError("flags 必须是数组")
            clean = []
            for item in pairs:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    raise ValueError("flags 每项格式应为 [名称, 取值]")
                clean.append((str(item[0]), item[1]))
            return ts.set_flags(clean)
        raise ValueError(f"不支持的操作：{action}")

    def api_ping(self, body: dict) -> dict:
        target = str(body.get("target") or "").strip()
        if not target:
            raise ValueError("缺少 target")
        ts.ping_targets(target)  # 保留扩展点
        return ts.ping(target)

    def api_netcheck(self) -> dict:
        result = ts.netcheck()
        result["report"] = parse_netcheck(result.get("out", ""))
        return result

    def api_config(self, body: dict) -> dict:
        cfg = load_config()
        if "api_key" in body:
            key = str(body.get("api_key") or "").strip()
            if key and not key.startswith("tskey-"):
                raise ValueError("API Key 应以 tskey- 开头")
            cfg["api_key"] = key
        if "tailnet" in body:
            cfg["tailnet"] = str(body.get("tailnet") or "-").strip() or "-"
        save_config(cfg)
        return {"ok": True, "has_key": bool(cfg.get("api_key")),
                "key_masked": masked(cfg.get("api_key", "")),
                "tailnet": cfg.get("tailnet", "-")}

    def api_cloud_devices(self, body: dict) -> dict:
        cfg = load_config()
        api_key = str(body.get("api_key") or cfg.get("api_key") or "").strip()
        tailnet = str(body.get("tailnet") or cfg.get("tailnet") or "-").strip() or "-"
        if not api_key:
            return {"ok": False, "err": "还没有填写 API Key", "need_key": True}
        # 先确认这把 key 属于哪个 tailnet
        who = cloud_request("/tailnet/-/devices?fields=all&limit=1", api_key)
        path = f"/tailnet/{tailnet}/devices?fields=all"
        res = cloud_request(path, api_key)
        if not res["ok"] and res.get("status") == 404 and tailnet != "-":
            res = cloud_request("/tailnet/-/devices?fields=all", api_key)
        res["who_ok"] = who.get("ok")
        return res

    def api_cloud_op(self, body: dict) -> dict:
        cfg = load_config()
        api_key = str(body.get("api_key") or cfg.get("api_key") or "").strip()
        if not api_key:
            return {"ok": False, "err": "还没有填写 API Key", "need_key": True}
        op = str(body.get("op") or "").strip()
        device_id = str(body.get("device_id") or "").strip()
        if not device_id:
            raise ValueError("缺少 device_id")

        if op == "expire":
            return cloud_request(f"/device/{device_id}/expire", api_key, "POST", {})
        if op == "delete":
            if body.get("confirm") != device_id:
                raise ValueError("删除操作需要二次确认")
            return cloud_request(f"/device/{device_id}", api_key, "DELETE")
        if op == "rename":
            name = str(body.get("name") or "").strip()
            if not name:
                raise ValueError("缺少新名称")
            return cloud_request(f"/device/{device_id}/name", api_key, "POST", {"name": name})
        if op == "authorize":
            return cloud_request(f"/device/{device_id}/authorized", api_key, "POST",
                                 {"authorized": bool(body.get("authorized", True))})
        if op == "routes":
            routes = body.get("routes") or []
            if not isinstance(routes, list):
                raise ValueError("routes 必须是数组")
            return cloud_request(f"/device/{device_id}/routes", api_key, "POST", {"routes": routes})
        if op == "device":
            return cloud_request(f"/device/{device_id}", api_key)
        raise ValueError(f"不支持的操作：{op}")

    def api_open(self, body: dict) -> dict:
        """在系统默认浏览器里打开链接（只允许 tailscale 相关域名）。"""
        url = str(body.get("url") or "").strip()
        allow = ("https://login.tailscale.com/", "https://console.tailscale.com/",
                 "https://tailscale.com/", "http://100.", "https://100.")
        if not url.startswith(allow):
            raise ValueError("出于安全考虑，只允许打开 Tailscale 相关地址")
        webbrowser.open(url)
        return {"ok": True, "url": url}


def parse_netcheck(text: str) -> dict:
    """把 netcheck 的文本报告拆成结构化数据，方便界面展示。"""
    info: dict = {"derp": [], "raw": text}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("* UDP:"):
            info["udp"] = line.split(":", 1)[1].strip()
        elif line.startswith("* IPv4:"):
            info["ipv4"] = line.split(":", 1)[1].strip()
        elif line.startswith("* IPv6:"):
            info["ipv6"] = line.split(":", 1)[1].strip()
        elif line.startswith("* MappingVariesByDestIP:"):
            info["mapping_varies"] = line.split(":", 1)[1].strip()
        elif line.startswith("* Nearest DERP:"):
            info["nearest_derp"] = line.split(":", 1)[1].strip()
        elif line.startswith("* PortMapping:"):
            rest = line.split(":", 1)[1].strip()
            if rest:
                info.setdefault("port_mapping", []).append(rest)
        elif line.startswith("- ") and "ms" in line:
            code = line[2:].split(":", 1)[0].strip()
            try:
                ms = float(line.split(":", 1)[1].strip().split("ms")[0].strip())
            except (ValueError, IndexError):
                continue
            info["derp"].append({"code": code, "ms": ms})
    info["derp"].sort(key=lambda item: item["ms"])
    return info


# --------------------------------------------------------------------------- #
# 启动
# --------------------------------------------------------------------------- #

def start_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def open_in_app_window(url: str) -> bool:
    """退回方案：用 Chrome / Edge 的应用模式开一个无地址栏窗口（跨平台）。"""
    if IS_MACOS:
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    elif IS_WINDOWS:
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ]
    else:
        candidates = [Path(p) for p in (
            "/usr/bin/google-chrome", "/usr/bin/chromium",
            "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge",
        )]
    profile = CONFIG_DIR / "browser-profile"
    profile.mkdir(parents=True, exist_ok=True)
    for exe in candidates:
        if exe.is_file():
            try:
                subprocess.Popen([
                    str(exe), f"--app={url}", f"--user-data-dir={profile}",
                    "--window-size=1280,860", "--no-first-run", "--no-default-browser-check",
                ])
                return True
            except Exception:
                continue
    return False


def main() -> int:
    log_note("main", (
        f"启动 frozen={getattr(sys, 'frozen', False)} "
        f"BASE_DIR={BASE_DIR} WEB_DIR={WEB_DIR} web_exists={WEB_DIR.is_dir()} "
        f"ts_exe={ts.TS_EXE}"
    ))
    if not WEB_DIR.is_dir():
        print(f"找不到界面目录：{WEB_DIR}")
        log_note("main", "缺少界面目录，退出")
        return 1

    port = pick_port()
    url = f"http://127.0.0.1:{port}/"
    start_server(port)
    log_note("main", f"服务已启动 {url}")

    if not ts.TS_EXE:
        print("提示：未找到 tailscale.exe，界面仍会启动，但设备信息为空。")

    # 排障用：只起服务不开窗口
    if os.environ.get("TS_CONSOLE_SERVER_ONLY") == "1":
        print(f"[server-only] {url}")
        try:
            while True:
                threading.Event().wait(3600)
        except KeyboardInterrupt:
            pass
        return 0

    opened = False
    if os.environ.get("TS_CONSOLE_NO_GUI") != "1":
        try:
            import webview

            options = {}
            # Windows 认 .ico；macOS 认 .icns（都没有就不传，窗口照样能开）
            icon_name = "app.icns" if IS_MACOS else "app.ico"
            icon_file = WEB_DIR / icon_name
            if icon_file.is_file():
                options["icon"] = str(icon_file)
            try:
                window = webview.create_window(
                    f"{APP_NAME}  ·  v{APP_VERSION}",
                    url,
                    width=1320,
                    height=880,
                    min_size=(1000, 640),
                    text_select=True,
                    **options,
                )
            except TypeError:
                # 个别版本不接受 icon 参数
                window = webview.create_window(
                    f"{APP_NAME}  ·  v{APP_VERSION}",
                    url,
                    width=1320,
                    height=880,
                    min_size=(1000, 640),
                    text_select=True,
                )
            del window
            webview.start(private_mode=False, storage_path=str(CONFIG_DIR / "webview"), debug=False)
            opened = True
            log_note("main", "webview.start() 已返回（窗口被关闭），程序退出")
        except Exception as exc:  # noqa: BLE001
            log_error("webview", exc)
            print(f"原生窗口启动失败（{type(exc).__name__}: {exc}），改用浏览器窗口。")

    if not opened:
        if not open_in_app_window(url):
            webbrowser.open(url)
            print("已用默认浏览器打开界面。关闭本窗口即结束程序。")
        else:
            print("已用 Chrome/Edge 应用窗口打开界面。关闭本窗口即结束程序。")
        try:
            while True:
                threading.Event().wait(3600)
        except KeyboardInterrupt:
            pass

    return 0


if __name__ == "__main__":
    # 全局兜底：任何未捕获异常都写进 error.log，方便排障
    def _hook(exc_type, exc_value, exc_tb):
        path = log_error("uncaught", exc_value)
        sys.stderr.write(f"程序异常，详情见：{path}\n")

    sys.excepthook = _hook
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        path = log_error("main", exc)
        sys.stderr.write(f"启动失败，详情见：{path}\n")
        sys.exit(1)
