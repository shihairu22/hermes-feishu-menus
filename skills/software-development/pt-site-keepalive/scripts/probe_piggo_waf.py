#!/usr/bin/env python3
"""在浏览器里过掉 CF 后，抓取 PigGo 的 SafeLine 挑战细节（只读，不登录）。

用途：确认 SafeLine challenge v2 的 issue/verify 链路与 calc.wasm 是否正常执行。
输出：请求/响应清单 + 页面里的 SafeLine 脚本片段。
"""
import os  # 家目录展开（去敏时可移植化）
import json
import re
import time

from camoufox.sync_api import Camoufox

CAPTURED = []

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True,
              user_data_dir=os.path.expanduser('~/.pt-sessions/piggo-login-session')) as browser:
    page = browser.new_page()

    def on_request(req):
        u = req.url
        if any(k in u for k in ('.safeline', 'challenge', 'waf', 'sl-')):
            CAPTURED.append(('REQ', req.method, u, (req.post_data or '')[:300]))

    def on_response(resp):
        u = resp.url
        if any(k in u for k in ('.safeline', 'challenge')):
            try:
                body = resp.text()[:400]
            except Exception:
                body = '<no body>'
            CAPTURED.append(('RESP', resp.status, u, body))

    page.on('request', on_request)
    page.on('response', on_response)

    print('打开 https://piggo.me/login.php ...', flush=True)
    t0 = time.time()
    try:
        page.goto('https://piggo.me/login.php', wait_until="domcontentloaded", timeout=90000)
    except Exception as exc:
        print('  导航异常: %s' % str(exc)[:120], flush=True)
    for i in range(12):
        page.wait_for_timeout(10000)
        try:
            txt = page.evaluate('() => (document.body && document.body.innerText) || ""')
        except Exception:
            txt = ''
        t = re.sub(r'\s+', ' ', txt)
        print('  [%3ds] URL=%s  文本长度=%d  %s' % (
            int(time.time() - t0), page.url[:60], len(t),
            '⚠ 仍见 Client Verifying' if 'Verifying' in t else '✓ 已过验证层'), flush=True)
        if 'Verifying' not in t:
            break

    print(flush=True)
    print('=== 捕获到的 safeline/challenge 流量 ===', flush=True)
    for kind, a, u, body in CAPTURED[:25]:
        print('  [%s] %s %s' % (kind, a, u[:110]), flush=True)
        if body:
            print('        %s' % re.sub(r'\s+', ' ', body)[:220], flush=True)

    print(flush=True)
    print('=== 页面里的 SafeLine 脚本 ===', flush=True)
    html = page.content()
    for m in re.finditer(r'(<script[^>]*>[^<]{0,300}(?:safeline|challenge|SafeLine)[^<]{0,300}</script>)', html, re.I):
        print('  %s' % re.sub(r'\s+', ' ', m.group(1))[:400], flush=True)
    for m in re.finditer(r'(SafeLineChallenge\([^)]*\))', html):
        print('  ★ %s' % m.group(1), flush=True)
    page.screenshot(path='/tmp/piggo_waf_probe.png')
