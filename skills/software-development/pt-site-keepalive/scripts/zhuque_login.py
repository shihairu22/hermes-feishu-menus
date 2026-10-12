#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""朱雀 ZHUQUE 登录 v6 —— 兼容 LAST_2FA_VALID。

  1. 取 x-csrf-token
  2. POST /api/user/send2fa {username, password}
       SEND_2FA_SUCCESS  → 等新邮件取码
       LAST_2FA_VALID    → 回读最近一封朱雀邮件的码（10 分钟有效期内直接用）
  3. POST /api/user/login {username, password, _2fa}
  4. 核对 cookie + /api/user/getInfo
"""
import os  # 家目录展开（去敏时可移植化）
import email
import email.utils
import imaplib
import json
import re
import time
from email.header import decode_header

from camoufox.sync_api import Camoufox

MT_ENV = os.path.expanduser("~/.pt-sessions/.env")
PROFILE = os.path.expanduser("~/.pt-sessions/zhuque-login-session")
SITE = "https://zhuque.in"
LOGIN = SITE + "/entry/login"
out = {"site": "zhuque", "v": 6}

CALL = """async ([url, csrf, body, method]) => {
     try {
       const res = await fetch(url, {
         method: method,
         headers: Object.assign({'Content-Type': 'application/json'}, csrf ? {'X-Csrf-Token': csrf} : {}),
         credentials: 'include',
         body: (method === 'POST' && body) ? JSON.stringify(body) : undefined
       });
       const txt = await res.text();
       return {status: res.status, body: txt.slice(0, 400)};
     } catch (e) { return {error: String(e).slice(0, 200)}; }
   }"""


def read_env(p):
    d = {}
    for line in open(p, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def _dh(v):
    return "".join(p.decode(e or "utf-8", errors="replace") if isinstance(p, bytes) else p
                   for p, e in decode_header(v or ""))


def scan_mail(host, port, user, pwd, since=None, limit=25):
    """扫最近的朱雀验证码邮件；since 为 None 时不过滤时间。返回 (code, age_sec, info)。"""
    box = None
    try:
        box = imaplib.IMAP4_SSL(host, port)
        box.login(user, pwd)
        box.select("INBOX")
        typ, data = box.search(None, "ALL")
        for mid in reversed((data[0] or b"").split()[-limit:]):
            typ, raw = box.fetch(mid, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])
            subj = _dh(msg.get("Subject", ""))
            if not re.search(r"朱雀|zhuque", subj, re.I):
                continue
            st = email.utils.parsedate_to_datetime(msg.get("Date", ""))
            age = time.time() - st.timestamp() if st else 99999
            if since is not None and st and st.timestamp() < since - 20:
                continue
            parts = msg.walk() if msg.is_multipart() else [msg]
            texts = []
            for p in parts:
                if p.get_content_type() in ("text/plain", "text/html"):
                    try:
                        texts.append(p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", errors="replace"))
                    except Exception:  # noqa: BLE001
                        pass
            blob = "\n".join(texts)
            m = re.search(r"验证码[：:\s]*([A-Za-z0-9]{6,12})", blob)
            if not m:
                m = re.search(r"(?<![0-9A-Za-z])([0-9a-f]{8})(?![0-9A-Za-z])", blob)
            if m:
                return m.group(1), age, {"subj": subj[:50], "at": str(st)[:19]}
        return None, None, None
    finally:
        try:
            if box:
                box.logout()
        except Exception:  # noqa: BLE001
            pass


env = read_env(MT_ENV)
USER, PWD = env.get("MTEAM_USERNAME", ""), env.get("MTEAM_PASSWORD", "")
EMU, EMP = env.get("MTEAM_EMAIL_USER", ""), env.get("MTEAM_EMAIL_APP_PASSWORD", "")
EMH = env.get("MTEAM_EMAIL_IMAP_HOST", "imap.qq.com")
EMPT = int(env.get("MTEAM_EMAIL_IMAP_PORT", "993") or 993)

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=PROFILE, locale="zh-CN") as browser:
    page = browser.new_page()
    page.set_default_timeout(45000)
    page.goto(LOGIN, wait_until="commit", timeout=60000)
    page.wait_for_selector("#form_item_username", timeout=60000)
    time.sleep(4)

    csrf = page.evaluate("""() => (document.querySelector("meta[name='x-csrf-token']")||{}).content || ''""")
    out["csrf_len"] = len(csrf or "")

    t0 = time.time()
    s = page.evaluate(CALL, ["/api/user/send2fa", csrf, {"username": USER, "password": PWD}, "POST"])
    out["send2fa"] = s
    code, age, info = None, None, None
    try:
        scode = json.loads(s.get("body") or "{}").get("code", "")
    except Exception:  # noqa: BLE001
        scode = ""

    if scode == "SEND_2FA_SUCCESS":
        # 等新邮件
        for _ in range(30):
            code, age, info = scan_mail(EMH, EMPT, EMU, EMP, since=t0)
            if code:
                break
            time.sleep(6)
    else:
        # LAST_2FA_VALID 或其它：直接回读最近一封
        code, age, info = scan_mail(EMH, EMPT, EMU, EMP, since=None)

    out["code_len"] = len(code or "")
    out["code_age_sec"] = round(age) if age else None
    out["mail_info"] = info
    if not code:
        out["error"] = "没拿到验证码"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    r = page.evaluate(CALL, ["/api/user/login", csrf, {"username": USER, "password": PWD, "_2fa": code}, "POST"])
    out["login_resp"] = r
    time.sleep(3)
    out["getInfo"] = page.evaluate(CALL, ["/api/user/getInfo", csrf, None, "GET"])

    try:
        page.goto(SITE + "/index", wait_until="commit", timeout=45000)
        time.sleep(10)
        t = re.sub(r"\s+", " ", page.inner_text("body"))
        out["final_url"] = (page.url or "")[:110]
        out["body_head"] = t[:700]
        out["loggedIn"] = "/entry/login" not in (page.url or "")
    except Exception as exc:  # noqa: BLE001
        out["final_err"] = str(exc)[:130]
    page.screenshot(path="/tmp/zhuque_after_login6.png", full_page=False)
    try:
        out["cookies"] = sorted({c["name"] for c in browser.cookies()})
    except Exception:  # noqa: BLE001
        pass

print(json.dumps(out, ensure_ascii=False, indent=2))
