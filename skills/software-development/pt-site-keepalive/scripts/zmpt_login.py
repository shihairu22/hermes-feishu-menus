#!/usr/bin/env python3
"""织梦 zmpt.cc 登录 + 签到 —— 必须 Camoufox（Cloudflare JS 挑战，curl 403）。

站点：无图形验证码、无 challenge-response（DOM 无 response 字段，按钮是 input[type=submit]）
→ 填表直接提交即可。

用法：MTEAM_NO_DELAY=1 xvfb-run -a <venv>/bin/python zmpt_login.py
"""
import os, re, sys
ENV = os.environ.get('MTEAM_ENV', os.path.expanduser('~/.pt-sessions/.env'))
BASE = 'https://zmpt.cc/'
UD = os.environ.get('ZMPT_PROFILE', os.path.expanduser('~/.pt-sessions/zm-session'))
os.makedirs(UD, exist_ok=True)

def load_env(path):
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

env = load_env(ENV)
USER, PWD = env['MTEAM_USERNAME'], env['MTEAM_PASSWORD']

from camoufox.sync_api import Camoufox

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=UD) as browser:
    page = browser.new_page()

    # 先看是否已有登录态（先穿 CF）
    page.goto(BASE + 'index.php', wait_until="domcontentloaded", timeout=60000)
    for i in range(10):
        page.wait_for_timeout(2500)
        if page.evaluate("() => !!document.querySelector('input[name=\"username\"]') || document.body.innerText.includes('退出')"):
            break
    t = page.evaluate('() => document.body.innerText')
    logged = ('退出' in t) and ('username' not in page.url)

    if not logged:
        print('===== 登录 =====', flush=True)
        page.goto(BASE + 'login.php', wait_until="domcontentloaded", timeout=60000)
        for i in range(12):
            page.wait_for_timeout(2500)
            if page.evaluate("() => !!document.querySelector('input[name=\"username\"]')"):
                break
        page.fill('input[name="username"]', USER)
        page.type('input[type="password"]', PWD, delay=45)
        try:
            pass  # ★ 不勾 securelogin（站点标签「限制只能使用本IP登录」）—— 用户明确要求一律不勾
        except Exception:
            pass
        page.click('input[type="submit"]')
        page.wait_for_timeout(9000)
        tt = re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))
        if '退出' in tt or '欢迎回来' in tt:
            logged = True
            print('  登录成功 →', page.url, flush=True)
        else:
            print('  !! 登录失败:', tt[:350], flush=True)
            sys.exit(1)
    else:
        print('[i] 已有登录态，跳过登录', flush=True)

    # 签到（打开即签）
    page.goto(BASE + 'attendance.php', wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    at = re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))
    i = at.find('签到成功')
    print('\n===== 签到 =====', flush=True)
    print('  ' + (at[i:i+220] if i >= 0 else '未检出「签到成功」: ' + at[:200]), flush=True)

    # 账号状态
    page.goto(BASE + 'index.php', wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    idx = re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))
    j = idx.find(USER)
    print('\n===== 用户栏 =====\n  ' + idx[max(0, j-20):j+240], flush=True)
    for lb, pat in [('上传', r'(?:上传量|上傳量)[：:]?\s*([\d.,]+\s*[KMGT]?i?B)'),
                    ('下载', r'(?:下载量|下載量)[：:]?\s*([\d.,]+\s*[KMGT]?i?B)'),
                    ('分享率', r'分享率[：:]?\s*([\d.]+)'),
                    ('电力值', r'电力值[^\d]{0,12}([\d.,]+)')]:
        m = re.search(pat, idx)
        if m:
            print('  %s: %s' % (lb, m.group(1)), flush=True)
