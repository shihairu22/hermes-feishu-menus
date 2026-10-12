#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CnLang 重试（2026-10-03）：登录 + 签到页 CF 重试 + 余额读取
基于 2026-09-26 成功的 cnlang_camoufox_native.py 改造：
  - 凭据改读 ~/.pt-sessions/.env；会话改 ~/.pt-sessions/cnlang-login-session
  - 签到页等待加长（~150 秒，赌 IP 信誉恢复）；仍拦则试一次拟人点击
  - 追加读「大洋」余额；结果落盘 JSON
"""
import base64
import json
import os
import re
import time

from camoufox.sync_api import Camoufox

SCRATCH = os.path.expanduser("~/.hermes/cache/scratch")
ENV = os.path.expanduser("~/.pt-sessions/.env")
PROFILE = os.path.expanduser("~/.pt-sessions/cnlang-login-session")
SIGN_PAGE = "https://cnlang.org/dsu_paulsign-sign.html?mobile=no"
POST_URL = "https://cnlang.org/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1"
CREDIT_URL = "https://cnlang.org/home.php?mod=spacecp&ac=credit&showcredit=1"
CAPTCHA_PNG = SCRATCH + "/cnlang_captcha.png"
ANSWER = SCRATCH + "/cnlang_captcha_answer.txt"
RESULT = SCRATCH + "/cnlang_retry_result.json"

out = {"site": "cnlang", "ts": time.strftime("%Y-%m-%d %H:%M:%S")}

creds = {}
with open(ENV, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            creds[k.strip()] = v.strip().strip('"').strip("'")
USER = creds.get("CNLANG_USERNAME", "")
PWD = creds.get("CNLANG_PASSWORD", "")
LOGIN_URL = creds.get("CNLANG_LOGIN_URL") or "https://cnlang.org/member.php?mod=logging&action=login"
out["username"] = USER
out["pwd_len"] = len(PWD)
assert USER and PWD, "凭据缺失"

if os.path.exists(ANSWER):
    os.remove(ANSWER)


def t(page):
    try:
        return page.title() or ""
    except Exception:
        return ""


def challengish(title):
    tl = title.lower()
    return any(k in tl for k in ("just a moment", "请稍候", "请稍等", "attention required", "challenge"))


def body(page, limit=400):
    try:
        return re.sub(r"\s+", " ", page.inner_text("body"))[:limit]
    except Exception:
        return ""


login_post_bodies = []

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=PROFILE,
              locale="zh-CN") as browser:
    page = browser.new_page()
    page.set_default_timeout(60000)

    def on_response(resp):
        try:
            if "loginsubmit=yes" in resp.url:
                txt = resp.text()[:1500]
                login_post_bodies.append({"status": resp.status, "body": txt})
        except Exception:
            pass

    page.on("response", on_response)

    # ① 登录页
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    cf_ok = False
    for i in range(30):
        time.sleep(3)
        if not challengish(t(page)):
            cf_ok = True
            break
    out["login_page_cf_ok"] = cf_ok
    out["login_page_title"] = t(page)[:80]
    print("STEP login-page cf_ok=%s title=%s" % (cf_ok, out["login_page_title"][:60]), flush=True)
    if not cf_ok:
        out["abort"] = "login page stuck on CF"
        json.dump(out, open(RESULT, "w"), ensure_ascii=False, indent=1)
        print("DONE-ABORT", flush=True)
        raise SystemExit(0)

    # ② 填表
    info = page.evaluate("""() => {
        const q = s => document.querySelector(s);
        const u = q("input[name^='username']");
        const p = q("input[name^='password']");
        const c = q("input[name^='seccodeverify']");
        const ct = q("input[name='cookietime']");
        const imgs = [...document.querySelectorAll('img')].map(i => i.src).filter(s => /seccode|misc\\.php/i.test(s));
        return {has_user: !!u, has_pwd: !!p, has_captcha: !!c, has_cookietime: !!ct, img_srcs: imgs.slice(0,3)};
    }""")
    out["form_fields"] = info
    page.fill("input[name^='username']", USER)
    page.fill("input[name^='password']", PWD)
    if info.get("has_cookietime"):
        try:
            page.check("input[name='cookietime']")
            out["cookietime_checked"] = True
        except Exception as e:
            out["cookietime_error"] = str(e)[:80]

    # ③ 验证码导出
    png = page.evaluate("""() => {
        const img = [...document.querySelectorAll('img')].find(i => /seccode|misc\\.php/i.test(i.src));
        if (!img) return null;
        const c = document.createElement('canvas');
        c.width = img.naturalWidth; c.height = img.naturalHeight;
        c.getContext('2d').drawImage(img, 0, 0);
        return c.toDataURL('image/png');
    }""")
    if png:
        open(CAPTCHA_PNG, "wb").write(base64.b64decode(png.split(",", 1)[1]))
        out["captcha_ready"] = True
        print("CAPTCHA_READY " + CAPTCHA_PNG, flush=True)
    else:
        out["captcha_ready"] = False
        print("CAPTCHA_MISSING", flush=True)

    # ④ 等答案（最多 ~600 秒）
    ans = ""
    for _ in range(120):
        if os.path.exists(ANSWER):
            ans = open(ANSWER, encoding="utf-8").read().strip()
            if ans:
                break
        time.sleep(5)
    out["captcha_answer_len"] = len(ans)
    print("ANSWER len=%d" % len(ans), flush=True)
    if not ans:
        out["abort"] = "no captcha answer"
        json.dump(out, open(RESULT, "w"), ensure_ascii=False, indent=1)
        print("DONE-ABORT", flush=True)
        raise SystemExit(0)

    # ⑤ 提交
    if info.get("has_captcha"):
        page.fill("input[name^='seccodeverify']", ans)
    time.sleep(0.6)
    page.click("button[name='loginsubmit'], input[name='loginsubmit'], #loginformsubmit")
    logged = False
    for i in range(15):
        time.sleep(3)
        b = body(page)
        if "退出" in b or USER in b:
            logged = True
            break
    out["loggedIn"] = logged
    out["login_msg_page"] = body(page, 300)
    out["login_responses"] = login_post_bodies[-2:]
    print("LOGIN %s | %s" % (logged, out["login_msg_page"][:120]), flush=True)
    try:
        page.screenshot(path=SCRATCH + "/cnlang_login.png", full_page=True)
    except Exception:
        pass

    # ⑥ 签到页尝试
    if logged:
        page.goto(SIGN_PAGE, wait_until="domcontentloaded")
        passed = False
        for i in range(50):     # 最多 ~150 秒
            time.sleep(3)
            if not challengish(t(page)):
                passed = True
                break
        out["sign_cf_passed"] = passed
        out["sign_cf_wait_s"] = (i + 1) * 3
        out["sign_title"] = t(page)[:80]
        out["sign_snippet"] = body(page, 260)
        print("SIGN cf_passed=%s wait=%ds title=%s" % (passed, out["sign_cf_wait_s"], out["sign_title"]), flush=True)
        if not passed:
            try:
                page.mouse.move(265, 312, steps=25)
                time.sleep(0.4)
                page.mouse.down()
                time.sleep(0.12)
                page.mouse.up()
                time.sleep(15)
                out["click_retry_state"] = "challenge" if challengish(t(page)) else "passed"
                if not challengish(t(page)):
                    passed = True
                    out["sign_cf_passed"] = True
                print("SIGN click-retry -> %s" % out.get("click_retry_state"), flush=True)
            except Exception as e:
                out["click_retry_err"] = str(e)[:80]
        try:
            page.screenshot(path=SCRATCH + "/cnlang_sign.png", full_page=True)
        except Exception:
            pass
        if passed:
            fh = page.evaluate("""() => { const i = document.querySelector("input[name='formhash']"); return i ? i.value : ''; }""")
            out["formhash_len"] = len(fh or "")
            if fh:
                res = page.evaluate("""async ([url, fh]) => {
                    const b = new URLSearchParams({formhash: fh, qdxq: 'kx', qdmode: '1', todaysay: '签到啦', fastreply: '0'});
                    const r = await fetch(url, {method:'POST', credentials:'include', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body: b.toString()});
                    const t = await r.text();
                    return {status: r.status, text: t.slice(0, 1500)};
                }""", [POST_URL, fh])
                out["post_status"] = res.get("status")
                plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", res.get("text", "")))
                out["post_text"] = plain[:500]
                print("SIGNPOST status=%s text=%s" % (out["post_status"], out["post_text"][:150]), flush=True)

    # ⑦ 读余额（大洋）
    try:
        page.goto(CREDIT_URL, wait_until="domcontentloaded")
        for i in range(20):
            time.sleep(3)
            if not challengish(t(page)):
                break
        ct = body(page, 2000)
        m = re.search(r"大洋[：: ]*([0-9,]+)", ct) or re.search(r"([0-9,]+)\s*大洋", ct)
        out["dayang"] = m.group(1) if m else None
        mk = re.search(r"积分[：: ]*([0-9,]+)", ct)
        out["points"] = mk.group(1) if mk else None
        print("BALANCE 大洋=%s 积分=%s" % (out.get("dayang"), out.get("points")), flush=True)
    except Exception as e:
        out["balance_err"] = str(e)[:100]

json.dump(out, open(RESULT, "w"), ensure_ascii=False, indent=1)
print("DONE", flush=True)
print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)
