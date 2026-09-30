# -*- coding: utf-8 -*-
"""
Tailscale 桌面控制台 —— 命令行封装层

职责：只调用官方 tailscale.exe，不直接读写任何 Tailscale 配置文件。

命令选用原则（重要）：
  * 连接 / 断开      -> `tailscale up`（无参数）/ `tailscale down`
                       官方说明：无参数的 up 只把网络拉起来，不改任何设置。
  * 修改单项设置     -> `tailscale set --xxx`
                       set 不会重置未提到的设置；而带参数的 up 会要求"完整设置集"，
                       容易把出口节点等配置冲掉，所以一律不用。
  * 只读信息         -> `status --json` / `debug prefs` / `ip` / `version` / `netcheck`

★★★ 绝对不要在已登录状态下调用 `tailscale login`（2026-09-30 实测踩坑）★★★
    帮助文本写的是"logs this machine in"，看起来人畜无害。
    但在**已经登录**的机器上执行它，会先清掉当前 node key、把状态打成
    `NeedsLogin`、清空 Self 与 User，再返回一个认证链接 —— 也就是**直接把设备踢下线**。
    实测：18:52 执行 `tailscale login`，BackendState 立刻从 Running 变成 NeedsLogin。
    要拿认证链接请只读 `status --json` 的 `AuthURL` 字段；要重新认证请走官方网页流程。
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"

# Windows 下隐藏子进程控制台窗口，避免闪黑框（macOS/Linux 没有这个参数）
CREATE_NO_WINDOW = 0x08000000

# tailscale 命令行工具的常见安装位置（按平台分别探测）
_CANDIDATES_WIN = (
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
)
_CANDIDATES_MAC = (
    "/usr/local/bin/tailscale",
    "/opt/homebrew/bin/tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    "/opt/local/bin/tailscale",
)
_CANDIDATES_UNIX = (
    "/usr/bin/tailscale",
    "/usr/sbin/tailscale",
    "/usr/local/bin/tailscale",
    "/usr/local/sbin/tailscale",
)


def find_exe() -> str | None:
    """定位 tailscale 命令行工具（跨平台）。

    macOS 说明：App Store 版 Tailscale 不带 CLI。若这里返回 None，
    请先 `brew install tailscale`，或用官方 Standalone 版里的
    「Install Tailscale CLI」菜单项安装命令行工具。
    """
    if IS_WINDOWS:
        paths = _CANDIDATES_WIN
    elif IS_MACOS:
        paths = _CANDIDATES_MAC
    else:
        paths = _CANDIDATES_UNIX
    for path in paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("tailscale")


TS_EXE = find_exe()


def run(args: list[str], timeout: int = 30) -> dict:
    """执行一条 tailscale 命令，返回结构化结果。永不抛异常。"""
    label = "tailscale " + " ".join(args)
    if not TS_EXE:
        hint = ("未找到 tailscale 命令行工具。"
                + ("macOS 请先执行 brew install tailscale" if IS_MACOS else "")
                + "（客户端下载：https://tailscale.com/download）")
        return {
            "ok": False, "code": -1, "cmd": label, "out": "",
            "err": hint,
        }
    try:
        # creationflags 只有 Windows 认，其他平台传了会报错
        extra = {"creationflags": CREATE_NO_WINDOW} if IS_WINDOWS else {}
        proc = subprocess.run(
            [TS_EXE, *args],
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            **extra,
        )
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "cmd": label,
            "out": (proc.stdout or "").strip(),
            "err": (proc.stderr or "").strip(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -2, "cmd": label, "out": "",
                "err": f"执行超时（超过 {timeout} 秒）"}
    except Exception as exc:  # noqa: BLE001 - 兜底，界面需要看到原因
        return {"ok": False, "code": -3, "cmd": label, "out": "",
                "err": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------- #
# 只读查询
# --------------------------------------------------------------------------- #

def version() -> dict:
    return run(["version"], timeout=15)


def status() -> dict:
    """`tailscale status --json`，返回体里带 data 字段（已解析的 JSON）。"""
    res = run(["status", "--json"], timeout=25)
    if res["ok"] and res["out"]:
        try:
            res["data"] = json.loads(res["out"])
        except json.JSONDecodeError as exc:
            res["ok"] = False
            res["err"] = f"status --json 返回内容无法解析：{exc}"
    return res


# prefs 里只保留界面需要的字段，避免把内部密钥类内容带到前端
_PREFS_KEEP = (
    "RouteAll", "ExitNodeID", "ExitNodeIP", "ExitNodeAllowLANAccess",
    "CorpDNS", "WantRunning", "ShieldsUp", "RunSSH", "RunWebClient",
    "AdvertiseRoutes", "AdvertiseTags", "LoggedOut", "ControlURL",
    "AutoUpdate", "Hostname", "NoStatefulFiltering",
)


def prefs() -> dict:
    """读取本机偏好。用的是 `debug prefs`（官方未开放正式只读命令）。"""
    res = run(["debug", "prefs"], timeout=20)
    if res["ok"] and res["out"]:
        try:
            raw = json.loads(res["out"])
        except json.JSONDecodeError:
            return res
        res["data"] = {key: raw.get(key) for key in _PREFS_KEEP}
        res["out"] = ""  # 原始文本含内部密钥字段，不外传
    return res


def netcheck() -> dict:
    """网络环境体检。实测约 3~10 秒。"""
    return run(["netcheck"], timeout=50)


def ping(target: str, count: int = 3, timeout: str = "3s") -> dict:
    """Tailscale 层面 ping，能看到走直连还是走中继。"""
    return run(
        ["ping", f"--c={count}", f"--timeout={timeout}", "--until-direct=false", target],
        timeout=40,
    )


def ping_targets(target: str) -> list[str]:
    """把设备可能的名字都列出来，ping 时依次尝试。"""
    return [target]


# --------------------------------------------------------------------------- #
# 写操作（全部通过白名单校验，杜绝参数注入）
# --------------------------------------------------------------------------- #

def connect() -> dict:
    """无参数 up：拉起网络，不动任何设置。"""
    return run(["up"], timeout=60)


def disconnect() -> dict:
    return run(["down"], timeout=40)


def logout() -> dict:
    """从 Tailscale 登出：网络下线 + 当前节点密钥作废。

    ★ 破坏性操作 ★ 设备会离开 tailnet，必须重新认证才能回来。
    只有用户在界面上明确二次确认后才允许调用。
    """
    return run(["logout"], timeout=40)


def account() -> dict:
    """从只读的 status --json 里取本机 Tailscale 的登录账号信息。

    注意：这里绝不调用 `tailscale login`（详见模块顶部警告）。
    未登录时 auth_url 会是 tailscaled 自己给的认证地址。
    """
    res = status()
    data = res.get("data") or {}
    users = data.get("User") or {}
    accounts = [
        {
            "login": u.get("LoginName", ""),
            "name": u.get("DisplayName", ""),
            "pic": u.get("ProfilePicURL", ""),
        }
        for u in users.values()
    ]
    backend = data.get("BackendState") or "Unknown"
    return {
        "ok": bool(res.get("data")),
        "backend_state": backend,
        "logged_in": backend == "Running",
        "auth_url": data.get("AuthURL") or "",
        "accounts": accounts,
        "hostname": (data.get("Self") or {}).get("HostName", ""),
        "err": res.get("err"),
    }


# 允许修改的偏好项：名字 -> 值类型
SETTABLE_FLAGS: dict[str, str] = {
    "exit-node": "str",
    "exit-node-allow-lan-access": "bool",
    "accept-routes": "bool",
    "accept-dns": "bool",
    "shields-up": "bool",
    "ssh": "bool",
    "advertise-exit-node": "bool",
    "advertise-routes": "str",
    "hostname": "str",
    "nickname": "str",
    "update-check": "bool",
    "auto-update": "bool",
    "unattended": "bool",
    "webclient": "bool",
}


def _safe_str(value: str) -> str:
    """值里不允许出现会改变参数结构的东西。"""
    text = str(value).strip()
    if text.startswith("-"):
        raise ValueError("取值不能以减号开头")
    for ch in ('"', "'", "\n", "\r", "\t", "&", "|", "^", "<", ">", "%", "`"):
        if ch in text:
            raise ValueError(f"取值不能包含字符 {ch!r}")
    if len(text) > 200:
        raise ValueError("取值过长")
    return text


def set_flags(pairs: list[tuple[str, object]]) -> dict:
    """按白名单执行 `tailscale set --flag=value`。

    pairs 例如 [("accept-routes", True), ("exit-node", "100.106.223.27")]
    """
    args: list[str] = []
    for name, value in pairs:
        kind = SETTABLE_FLAGS.get(name)
        if kind is None:
            raise ValueError(f"不允许修改的设置项：{name}")
        if kind == "bool":
            flag = "true" if value in (True, "true", "True", 1, "1") else "false"
        else:
            flag = _safe_str(value)
        args.append(f"--{name}={flag}")
    if not args:
        raise ValueError("没有要修改的设置项")
    return run(["set", *args], timeout=45)
