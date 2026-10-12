#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TTG (totheglory.im) 登录 —— Camoufox + 馒头同款凭据。

注意：TTG 只有 6 次登录机会，6 次失败封 IP。
本脚本只提交一次；失败即停止并报告，不自动重试。
若出现双重验证（2FA）步骤，则停下打印 NEED_2FA，等外部提供动态码。
"""
import json
import os
import re
import time

from camoufox.sync_api import Camoufox

ENV = os.path.expanduser("~/.pt-sessions/.env")
PROFILE = os.path.expanduser("~/.pt-sessions/ttg-login-session")
LOGIN_URL = "https://totheglory.im/login.php"
INDEX_URL = "https://totheglory.im/index.php"
TFA_FILE = "/tmp/ttg_2fa_code.txt"
out = {"site": "ttg", "method": "camoufox + mteam credentials"}


def body(page):
    try:
        return re.sub(r"\s+", " ", page.inner_text("body"))
    except Exception:  # noqa: BLE001
        return ""


creds = {}
with open(ENV, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            creds[k.strip()] = v.strip().strip('"').strip("'")
USER = creds.get("MTEAM_USERNAME", "")
PWD = creds.get("MTEAM_PASSWORD", "")
out["username"] = USER
out["pwd_len"] = len(PWD)

if os.path.exists(TFA_FILE):
    os.remove(TFA_FILE)

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=PROFILE, locale="zh-CN") as browser:
    page = browser.new_page()
    page.set_default_timeout(60000)

    # 1) 打开登录页（若已是登录态则直接成功）
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    time.sleep(3)
    t = body(page)
    out["login_page_title"] = page.title()[:70]
    out["already_logged_in"] = ("退出" in t) and ("登录" not in t[:200])
    out["attempts_hint"] = (re.search(r"你还有 ?(\d+) ?次登录机会", t) or [None, ""])[1]
    out["cf_challenge"] = ("security verification" in t.lower() or "正在进行安全验证" in t)

    if not out["already_logged_in"]:
        # 2) 在 lang=0（简体）的表单内填表
        ok = page.evaluate(
            """([u, p]) => {
                 const forms = [...document.querySelectorAll('form[action*="takelogin"]')];
                 const f = forms.find(x => { const l = x.querySelector("input[name='lang']");
                                             return l && l.value === '0'; }) || forms[0];
                 if (!f) return false;
                 const un = f.querySelector("input[name='username']");
                 const pw = f.querySelector("input[name='password']");
                 const pa = f.querySelector("input[name='passan']");
                 if (!un || !pw) return false;
                 un.value = u; pw.value = p; if (pa) pa.value = '';
                 window.__ttgForm = f;
                 return true;
               }""",
            [USER, PWD],
        )
        out["filled"] = ok
        out["pwd_len_in_form"] = page.evaluate(
            """() => { const f = window.__ttgForm; const p = f && f.querySelector("input[name='password']");
                       return p ? p.value.length : -1; }"""
        )

        # 3) 提交（只一次）
        try:
            page.evaluate("""() => { const f = window.__ttgForm;
                                     const s = f.querySelector("input[type='submit']");
                                     if (s) s.click(); else f.submit(); }""")
        except Exception as exc:  # noqa: BLE001
            out["submit_error"] = str(exc)[:200]
        try:
            page.wait_for_load_state("domcontentloaded", timeout=60000)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5)
        out["url_after"] = page.url
        t2 = body(page)
        out["body_after"] = t2[:500]
        out["title_after"] = page.title()[:70]

        # 4) 判定
        out["loggedIn"] = ("退出" in t2) or ("我的" in t2 and "登录" not in t2[:150])
        m = re.search(r"(登录失败|用户名或密码错误|密码错误|验证码|错误[^ ]{0,20}|你还有 ?\d+ ?次|禁止|双重验证|两步验证|安全验证|动态码|认证)", t2)
        out["message"] = m.group(0) if m else ""
        out["attempts_after"] = (re.search(r"你还有 ?(\d+) ?次登录机会", t2) or [None, ""])[1]

        # 5) 若出现 2FA 步骤
        needs_2fa = bool(re.search(r"双重验证|两步验证|动态码|认证器|2FA|authenticator", t2, re.I))
        out["needs_2fa"] = needs_2fa
        if needs_2fa and not out["loggedIn"]:
            print("NEED_2FA " + json.dumps({"msg": out["message"]}, ensure_ascii=False), flush=True)
            code = ""
            for _ in range(60):      # 最多等 300 秒
                if os.path.exists(TFA_FILE):
                    code = open(TFA_FILE, encoding="utf-8").read().strip()
                    if code:
                        break
                time.sleep(5)
            out["tfa_code_len"] = len(code)
            if code:
                try:
                    page.fill("input[type='text']:visible, input[name*='code' i], input[name*='2fa' i]", code)
                    page.keyboard.press("Enter")
                    time.sleep(6)
                    t3 = body(page)
                    out["loggedIn_after_2fa"] = ("退出" in t3)
                    out["body_after_2fa"] = t3[:300]
                except Exception as exc:  # noqa: BLE001
                    out["tfa_error"] = str(exc)[:200]

    # 6) 登录成功后抓首页数据
    if out.get("loggedIn") or out.get("loggedIn_after_2fa"):
        page.goto(INDEX_URL, wait_until="domcontentloaded")
        time.sleep(4)
        t4 = body(page)
        out["index_snippet"] = t4[:700]
        stats = {}
        for key, pat in (("上传量", r"上传量[^0-9]{0,10}([\d\.,]+ ?[KMGTP]?B)"),
                         ("下载量", r"下载量[^0-9]{0,10}([\d\.,]+ ?[KMGTP]?B)"),
                         ("分享率", r"分享率[^0-9]{0,10}([\d\.,]+)"),
                         ("积分", r"积分[^0-9]{0,10}([\d\.,]+)"),
                         ("魔力值", r"魔力值[^0-9]{0,10}([\d\.,]+)"),
                         ("邀请", r"邀请[^0-9]{0,10}(\d+)"),
                         ("做种", r"做种[^0-9]{0,10}(\d+)")):
            mm = re.search(pat, t4)
            if mm:
                stats[key] = mm.group(1)
        out["stats"] = stats
        page.screenshot(path="/tmp/ttg_index.png", full_page=True)
        out["index_screenshot"] = "/tmp/ttg_index.png"

    out["cookies"] = [c["name"] for c in browser.cookies()][:12]
    page.screenshot(path="/tmp/ttg_final.png", full_page=True)
    out["final_screenshot"] = "/tmp/ttg_final.png"

print(json.dumps(out, ensure_ascii=False, indent=2))
