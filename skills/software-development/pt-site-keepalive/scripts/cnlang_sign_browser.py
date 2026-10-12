#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CnLang 签到直取：URL 编码绕过 CF 规则 → 提交签到（一次，用户本账号）"""
import os  # 家目录展开（去敏时可移植化）
import json
import re
import time
import urllib.parse

from camoufox.sync_api import Camoufox

PROFILE = os.path.expanduser('~/.pt-sessions/cnlang-login-session')
BASE = 'https://cnlang.org'


def challeng(p):
    try:
        t = (p.title() or '').lower()
    except Exception:
        t = ''
    return ('just a moment' in t) or ('请稍候' in t) or ('请稍等' in t) or ('attention' in t)


with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=PROFILE,
              locale="zh-CN") as browser:
    page = browser.new_page()
    page.set_default_timeout(60000)

    # 1) 验证码后首页确认登录 + 取 formhash
    page.goto(BASE + '/home.php', wait_until='domcontentloaded')
    for _ in range(20):
        time.sleep(3)
        if not challeng(page):
            break
    fh = page.evaluate("""() => { const i = document.querySelector("input[name='formhash']"); return i ? i.value : ''; }""")
    print('formhash len=%d' % len(fh or ''), flush=True)

    # 2) 编码后取签到面板（只读）
    r1 = page.evaluate("""async ([url]) => {
        const r = await fetch(url, {credentials:'include'});
        const t = await r.text();
        return {status: r.status, cf: r.headers.get('cf-mitigated') || '',
                snip: t.replace(/\\s+/g, ' ').slice(0, 260)};
    }""", [BASE + '/plugin.php?id=%64su_paulsign:sign'])
    print('PANEL:', json.dumps(r1, ensure_ascii=False)[:420], flush=True)

    # 3) 提交签到（同样用编码绕过 CF；参数全在 query —— 与源码处理逻辑一致）
    td = urllib.parse.quote('签到啦')
    url = ('%s/plugin.php?id=%%64su_paulsign:sign&operation=qiandao&formhash=%s'
           '&qdxq=kx&qdmode=1&todaysay=%s&infloat=1&inajax=1' % (BASE, fh, td))
    print('SIGN URL: ' + url[:150], flush=True)
    r2 = page.evaluate("""async ([url]) => {
        const r = await fetch(url, {credentials:'include'});
        const t = await r.text();
        return {status: r.status, cf: r.headers.get('cf-mitigated') || '', text: t.slice(0, 1500)};
    }""", [url])
    print('SIGN RESULT:', json.dumps(r2, ensure_ascii=False)[:1400], flush=True)

    # 4) 复核：读余额
    page.goto(BASE + '/home.php?mod=spacecp&ac=credit&showcredit=1', wait_until='domcontentloaded')
    time.sleep(3)
    try:
        tx = re.sub(r'\s+', ' ', page.inner_text('body'))
        m = re.search(r'大洋[：: ]*([0-9,]+)', tx) or re.search(r'([0-9,]+)\s*大洋', tx)
        mk = re.search(r'积分[：: ]*([0-9,]+)', tx)
        print('BALANCE 大洋=%s 积分=%s' % (m.group(1) if m else '?', mk.group(1) if mk else '?'), flush=True)
    except Exception as e:
        print('balance err: %s' % str(e)[:100], flush=True)

    print('DONE', flush=True)
