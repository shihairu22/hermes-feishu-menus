#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PTHOME (www.pthome.net) 登录 —— NexusPHP + Cloudflare 挑战。

流程：
  1. Camoufox 过 CF 挑战，打开 /login.php
  2. 填用户名/密码，导出图形验证码 → 打印 CAPTCHA_READY
  3. 轮询 /tmp/pthome_captcha_answer.txt：
       "RELOAD"  → 换一张验证码
       字符答案   → 填入并提交（只提交一次）
  4. 成功判据：跳到 index.php 且出现用户栏（欢迎回来/退出/用户名）
"""
import base64
import json
import os
import re
import time

from camoufox.sync_api import Camoufox

MT_ENV = os.path.expanduser("~/.pt-sessions/.env")
PROFILE = os.path.expanduser("~/.pt-sessions/pthome-login-session")
SITE = "https://www.pthome.net"
LOGIN = SITE + "/login.php"
CAPTCHA_PNG = "/tmp/pthome_captcha.png"
ANS = "/tmp/pthome_captcha_answer.txt"
out = {"site": "pthome"}

EXPORT_JS = """() => { const img = document.querySelector("img[src*='regimage']")
                        || document.querySelector("#captcha_img")
                        || [...document.querySelectorAll('img')].find(i => /image\\.php/.test(i.src||''));
                 if (!img || !img.complete || img.naturalWidth < 20) return null;
                 const c = document.createElement('canvas');
                 c.width = img.naturalWidth; c.height = img.naturalHeight;
                 c.getContext('2d').drawImage(img, 0, 0);
                 return c.toDataURL('image/png'); }"""

RELOAD_JS = """() => { const img = document.querySelector("img[src*='regimage']")
                       || [...document.querySelectorAll('img')].find(i => /image\\.php/.test(i.src||''));
                if (!img) return 'no-img';
                img.click();
                return 'clicked'; }"""


def body(page, timeout=25000):
    try:
        return re.sub(r"\s+", " ", page.inner_text("body", timeout=timeout))
    except Exception:  # noqa: BLE001
        return ""


def read_env(path):
    d = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d


env = read_env(MT_ENV)
USER = env.get("MTEAM_USERNAME", "")
PWD = env.get("MTEAM_PASSWORD", "")
out["cred"] = {"user_len": len(USER), "pwd_len": len(PWD)}
if not USER or not PWD:
    print(json.dumps({**out, "error": "凭据缺失"}, ensure_ascii=False, indent=2))
    raise SystemExit(1)

for p in (CAPTCHA_PNG, ANS):
    if p and os.path.exists(p):
        os.remove(p)

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=PROFILE, locale="zh-CN") as browser:
    page = browser.new_page()
    page.set_default_timeout(45000)

    page.goto(LOGIN, wait_until="commit", timeout=60000)
    # 等 CF 挑战通过
    for i in range(12):
        time.sleep(5)
        try:
            t = page.title() or ""
        except Exception:  # noqa: BLE001
            t = ""
        if t and "Just a moment" not in t:
            out["cf_passed_at"] = (i + 1) * 5
            break
    page.wait_for_selector("input[name='username']", timeout=60000)
    time.sleep(2)

    t = body(page)
    out["tries_before"] = (re.search(r"你还有\s*\[?(\d+)\]?\s*次尝试", t) or [None, "?"])[1]
    out["already_in"] = bool(re.search(r"(退出|登出|Logout)", t))

    page.fill("input[name='username']", USER)
    page.fill("input[name='password']", PWD)
    out["imagehash"] = page.evaluate(
        """() => { const e = document.querySelector("input[name='imagehash']"); return e ? e.value : null; }"""
    )

    ans = ""
    for rnd in range(1, 16):
        png = page.evaluate(EXPORT_JS)
        if png:
            with open(CAPTCHA_PNG, "wb") as f:
                f.write(base64.b64decode(png.split(",", 1)[1]))
        out["captcha_round"] = rnd
        print("CAPTCHA_READY " + json.dumps({"png": CAPTCHA_PNG, "round": rnd}, ensure_ascii=False), flush=True)

        ans = ""
        for _ in range(60):        # 每张最多等 300 秒
            if os.path.exists(ANS):
                ans = open(ANS, encoding="utf-8").read().strip()
                if ans:
                    break
            time.sleep(5)
        if not ans:
            out["captcha_timeout"] = True
            break
        if ans.upper() == "RELOAD":
            os.remove(ANS)
            out.setdefault("reloads", []).append(page.evaluate(RELOAD_JS))
            time.sleep(3)
            continue
        break

    out["captcha_answer"] = ans
    if ans and ans.upper() != "RELOAD":
        page.fill("input[name='imagestring']", ans)
        time.sleep(0.5)
        filled = page.evaluate(
            """() => ({u: (document.querySelector("input[name='username']")||{}).value,
                        p: ((document.querySelector("input[name='password']")||{}).value||"").length,
                        c: (document.querySelector("input[name='imagestring']")||{}).value})"""
        )
        out["filled"] = filled
        problems = []
        if filled.get("u") != USER:
            problems.append("username 不符")
        if filled.get("p") != len(PWD):
            problems.append("password 长度不符")
        if (filled.get("c") or "").strip() != ans.strip():
            problems.append("captcha 未填入")
        if problems:
            out["abort"] = problems
            print(json.dumps(out, ensure_ascii=False, indent=2))
            raise SystemExit(1)

        try:
            out["submit"] = page.evaluate(
                """() => { const f = document.querySelector("form[action*='takelogin']")
                                  || [...document.querySelectorAll('form')].find(x => x.querySelector("input[name='password']"));
                           if (!f) return 'no-form';
                           const b = f.querySelector("input[type='submit'], button[type='submit']");
                           if (b) { b.click(); return 'clicked'; }
                           f.submit(); return 'submitted'; }"""
            )
        except Exception as exc:  # noqa: BLE001
            out["submit_error"] = str(exc)[:180]
        time.sleep(9)

        out["url_after"] = (page.url or "")[:110]
        out["title_after"] = (page.title() or "")[:70]
        t2 = body(page)
        out["body_after"] = t2[:500]
        out["loggedIn"] = bool(re.search(r"(欢迎回来|退出|登出|Logout|我的|個人|个人)", t2)) and "login.php" not in (page.url or "")
        out["msg"] = (re.search(r"(登录失败|密碼錯誤|密码错误|验证码|驗證碼|不正确|錯誤|失败|已禁用|banned)", t2) or [None, ""])[1]
        out["tries_after"] = (re.search(r"你还有\s*\[?(\d+)\]?\s*次尝试", t2) or [None, "?"])[1]
        page.screenshot(path="/tmp/pthome_after_login.png", full_page=False)
        out["screenshot"] = "/tmp/pthome_after_login.png"

print(json.dumps(out, ensure_ascii=False, indent=2))
