#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TTG 签到 —— 点击站点自己的 #signed 链接（触发 signed.php POST），捕获弹窗消息。

机制（从页面 JS 提取）：
  $.post("signed.php", {signed_timestamp, signed_token}, cb)
  成功后 #sp_signed 变为绿色「已签到」
"""
import os  # 家目录展开（去敏时可移植化）
import json
import re
import time

from camoufox.sync_api import Camoufox

PROFILE = os.path.expanduser("~/.pt-sessions/ttg-login-session")
INDEX = "https://totheglory.im/index.php"
out = {"site": "ttg"}
dialogs = []


def body(page):
    try:
        return re.sub(r"\s+", " ", page.inner_text("body"))
    except Exception:  # noqa: BLE001
        return ""


def points(page):
    t = body(page)
    m = re.search(r"积分\s*[:：]\s*([\d,\.]+)", t)
    return m.group(1) if m else ""


with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=PROFILE, locale="zh-CN") as browser:
    page = browser.new_page()
    page.set_default_timeout(60000)
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))

    page.goto(INDEX, wait_until="domcontentloaded")
    time.sleep(4)
    out["loggedIn"] = "退出" in body(page)
    out["points_before"] = points(page)
    out["state_before"] = page.evaluate(
        """() => { const e = document.querySelector('#sp_signed'); return e ? e.innerText.trim() : ''; }"""
    )
    out["token_in_page"] = page.evaluate(
        """() => { const h = document.documentElement.innerHTML;
                   const m = h.match(/signed_token:\\s*"([0-9a-f]{16,})"/);
                   return m ? m[1].length : 0; }"""
    )

    if out["state_before"] and "已签到" in out["state_before"]:
        out["action"] = "already_signed"
    else:
        # 点击站点自己的签到链接
        try:
            page.click("a#signed", timeout=15000)
            out["clicked"] = True
        except Exception as exc:  # noqa: BLE001
            out["click_error"] = str(exc)[:200]
        time.sleep(6)
        out["dialogs"] = dialogs
        out["state_after_click"] = page.evaluate(
            """() => { const e = document.querySelector('#sp_signed'); return e ? e.innerText.trim() : ''; }"""
        )
        out["points_after"] = points(page)
        page.screenshot(path="/tmp/ttg_signed_result.png", full_page=True)
        out["screenshot"] = "/tmp/ttg_signed_result.png"

        # 若站点 JS 未生效，退回直接 POST signed.php
        if "已签到" not in (out.get("state_after_click") or ""):
            out["fallback_post"] = True
            res = page.evaluate(
                """async () => {
                     const h = document.documentElement.innerHTML;
                     const ts = (h.match(/signed_timestamp:\\s*"([^"]*)"/) || [])[1];
                     const tk = (h.match(/signed_token:\\s*"([^"]*)"/) || [])[1];
                     if (!ts || !tk) return {error: 'token-not-found'};
                     const b = new URLSearchParams({signed_timestamp: ts, signed_token: tk});
                     const r = await fetch('signed.php', {method:'POST', credentials:'include',
                       headers:{'Content-Type':'application/x-www-form-urlencoded'}, body: b.toString()});
                     const t = await r.text();
                     return {status: r.status, text: t.slice(0, 400)};
                   }"""
            )
            out["post_result"] = res
            time.sleep(3)

    # 复核
    page.goto(INDEX, wait_until="domcontentloaded")
    time.sleep(4)
    out["state_final"] = page.evaluate(
        """() => { const e = document.querySelector('#sp_signed'); return e ? e.innerText.trim() : ''; }"""
    )
    out["points_final"] = points(page)
    out["user_bar_final"] = (re.search(r"欢迎回来[^|]{0,180}", body(page)) or [None, ""])[0]
    page.screenshot(path="/tmp/ttg_signed_final.png", full_page=True)
    out["final_screenshot"] = "/tmp/ttg_signed_final.png"

print(json.dumps(out, ensure_ascii=False, indent=2))
