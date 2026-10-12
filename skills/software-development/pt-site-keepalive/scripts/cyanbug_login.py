#!/usr/bin/env python3
"""大青虫（cyanbug.net）Camoufox 登录 + 签到探测。

站点用 challenge-response（/api/challenge + sha256/hmac）且对纯脚本 POST 无响应，
用真实浏览器执行它的 JS 即可；**无图形验证码**，可全自动。
"""
import os  # 家目录展开（去敏时可移植化）
import re, os, sys
from camoufox.sync_api import Camoufox

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://cyanbug.net/'
UD = os.path.expanduser('~/.pt-sessions/bug-login-session')

env = {}
for line in open(ENV):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
USER, PWD = env['MTEAM_USERNAME'], env['MTEAM_PASSWORD']
os.makedirs(UD, exist_ok=True)

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=UD) as browser:
    page = browser.new_page()
    page.goto(BASE + 'login.php', wait_until="commit", timeout=60000)
    page.wait_for_timeout(6000)
    # ★ 坑：已有持久登录态时 login.php 不再渲染登录表单，死等 wait_for_selector 会白等 45s 超时
    has_form = page.evaluate("() => !!document.querySelector('input[name=\"username\"]')")
    body = page.evaluate('() => document.body.innerText').replace('\n', ' ')
    if not has_form and re.search(r'退出|歡迎回來|欢迎回来|控制面板', body):
        print('① 已有登录态，跳过登录')
        ok = True
    else:
        page.wait_for_selector('input[name="username"]', state="attached", timeout=45000)
        page.wait_for_timeout(1500)
        print('① 登录页已开 | webdriver=%s' % page.evaluate('() => navigator.webdriver'))

        page.fill('#login-form input[name="username"]', USER)
        page.type('#login-form input[name="password"]', PWD, delay=55)
        # ★ 不勾 securelogin（站点标签「限制只能使用本IP登录」）—— 用户明确要求一律不勾

        # 点击 type=button 的登录按钮（由站点 JS 走 challenge-response）
        page.click('#login-form input[type="button"]')
        page.wait_for_timeout(7000)

        url = page.url
        body = page.evaluate('() => document.body.innerText').replace('\n', ' ')
        ok = ('index.php' in url) and ('欢迎' in body or '退出' in body)
        print('② 登录: %s (URL=%s)' % ('✅ 成功' if ok else '❌ 失败', url))
        if not ok:
            print('   页面文本(前 300):', re.sub(r'\s+', ' ', body)[:300])
            sys.exit(1)

    i = body.find('欢迎')
    print('③ 用户栏:', body[max(0, i - 10):i + 240] if i >= 0 else body[:240])
    for lb, pat in [('上传', r'上传量?[：:]?\s*([\d.,]+\s*[KMGT]?i?B)'), ('下载', r'下载量?[：:]?\s*([\d.,]+\s*[KMGT]?i?B)'),
                    ('分享率', r'分享率[：:]?\s*([\d.]+)'), ('魔力值', r'魔力值[^\d]{0,20}([\d.,]+)'),
                    ('做种', r'做种[^\d]{0,20}(\d+)')]:
        m = re.search(pat, body)
        if m:
            print('   %s: %s' % (lb, m.group(1)))

    print('\n④ 签到入口探测:')
    for p in ('attendance.php', 'mybonus.php', 'qiandao.php'):
        try:
            r = page.goto(BASE + p, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(1200)
            b = re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))
            st = r.status if r else '?'
            if '签到' in b:
                j = b.find('签到')
                print('   %-16s HTTP %-4s 含「签到」→ %s' % (p, st, b[max(0, j - 50):j + 110]))
            else:
                print('   %-16s HTTP %-4s %s' % (p, st, b[:70]))
        except Exception as e:
            print('   %-16s 异常 %s' % (p, type(e).__name__))
    # 回首页看有没有签到按钮
    page.goto(BASE + 'index.php', wait_until="domcontentloaded", timeout=35000)
    page.wait_for_timeout(1500)
    links = page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a=>[a.innerText.trim().slice(0,20), a.getAttribute('href')||'']).filter(x=>/签|sign|attendance|bonus/i.test(x[0]+' '+x[1]))""")
    print('   首页签到相关链接:', links[:8] if links else '（无）')
