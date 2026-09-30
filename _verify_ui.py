# -*- coding: utf-8 -*-
"""渲染核对：登录页 + 主界面，抓控制台错误并截图。"""
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8756/"
OUT = Path(__file__).resolve().parent / "_shots"
OUT.mkdir(exist_ok=True)
CFG = Path.home() / ".tailscale-console" / "config.json"

errors: list[str] = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-proxy-server"])
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.on("console", lambda m: errors.append(f"[console.{m.type}] {m.text}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(1200)

    print("---- 登录页 ----")
    print("登录页可见:", page.is_visible("#loginView"))
    print("主界面隐藏:", page.is_hidden("#appRoot"))
    print("提示文案:", page.inner_text("#loginNotice").replace("\n", " | "))
    print("控制台版本:", page.inner_text("#loginAppVer"))
    print("客户端版本:", page.inner_text("#loginCliVer"))
    print("下载链接:", page.inner_text("#loginDownload").replace("\n", " "))
    page.screenshot(path=str(OUT / "login-light.png"))

    # 登录页上没有主题按钮，直接改根节点属性来验证深色样式
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / "login-dark.png"))
    print("shot: login-dark")
    page.evaluate("document.documentElement.dataset.theme = 'light'")
    page.wait_for_timeout(300)

    # SHOT_LOGIN_ONLY=1 时只拍登录页，不伪造会话（否则 config.json 会留下假登录态）
    if os.environ.get("SHOT_LOGIN_ONLY") == "1":
        browser.close()
        print("---- 控制台错误 ----")
        print("\n".join(errors) if errors else "(无)")
        sys.exit(0)

    # ---------- 伪造一个会话，检查主界面 ----------
    cfg = {}
    if CFG.is_file():
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
    cfg["session"] = {
        "login": "zcshi1234567@gmail.com",
        "name": "ZC Shi",
        "pic": "",
        "since": "2026-09-30T18:50:00",
        "method": "email",
    }
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(1800)

    print("---- 主界面 ----")
    print("登录页隐藏:", page.is_hidden("#loginView"))
    print("主界面可见:", page.is_visible("#appRoot"))
    print("账号名:", page.inner_text("#accountName"))
    print("账号邮箱:", page.inner_text("#accountLogin"))
    print("底部版本:", page.inner_text("#footAppVer"), "/", page.inner_text("#footCliVer"))
    print("底部账号:", page.inner_text("#footAccount"))
    print("底部下载:", page.inner_text("#footDownload").replace("\n", " "))
    print("设备卡片数:", page.eval_on_selector_all(".dev", "els => els.length"))
    page.screenshot(path=str(OUT / "app-devices.png"))

    for tab in ("settings", "cloud", "logs"):
        page.click(f'.tab[data-tab="{tab}"]')
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / f"app-{tab}.png"))
        print("shot: app-" + tab)

    page.click('.tab[data-tab="settings"]')
    page.wait_for_timeout(300)
    print("设置-控制台版本:", page.inner_text("#verApp"))
    print("设置-客户端版本:", page.inner_text("#verClient"))
    print("设置-客户端路径:", page.inner_text("#verExe"))

    # 注销弹窗
    page.click("#btnLogout")
    page.wait_for_timeout(600)
    print("注销弹窗可见:", page.is_visible("#logoutModal"))
    print("注销弹窗账号:", page.inner_text("#logoutWho"))
    page.screenshot(path=str(OUT / "logout-modal.png"))
    print("shot: logout-modal")

    browser.close()

print("---- 控制台错误 ----")
print("\n".join(errors) if errors else "(无)")
sys.exit(0)
