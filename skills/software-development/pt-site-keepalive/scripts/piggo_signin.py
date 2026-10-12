#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PigGo 签到（两阶段：过 SafeLine WAF + 公告弹窗 → 等 2FA 动态码 → 提交签到）

答案文件：/tmp/piggo_2fa_answer.txt（写入 6 位动态码）
注意：SafeLine WAF 很慢（可能 9 分钟以上），不要因为没输出就杀进程。
"""
import json
import os
import re
import sys
import time

ANS = '/tmp/piggo_2fa_answer.txt'
UD = os.path.expanduser('~/.pt-sessions/piggo-login-session')
URL = 'https://piggo.me/attendance.php'

from camoufox.sync_api import Camoufox


def brief(s, n=900):
    return re.sub(r'\s+', ' ', s or '')[:n]


if os.path.exists(ANS):
    os.remove(ANS)

with Camoufox(headless=False, os="windows", humanize=True,
              persistent_context=True, user_data_dir=UD) as browser:
    page = browser.new_page()
    page.goto(URL, wait_until='domcontentloaded', timeout=180000)

    # 等页面真正就绪（SafeLine 质询会自动过）
    for _ in range(50):
        page.wait_for_timeout(3000)
        try:
            b = page.inner_text('body')
        except Exception:
            b = ''
        if '签到' in b or '公告' in b or '二级验证' in b or '两步' in b:
            break
    print('page_ready title=%s url=%s' % (page.title(), page.url), flush=True)

    # ★ 干净会话（cookie 被清）下，attendance.php 会 302 到 login.php?returnto=attendance.php，
    #   而登录表单本身就带 two_step_code 字段 → 下面的「2FA 表单检测」会把登录页误报成 NEED_2FA。
    #   此时写码 = 用空用户名/密码提交登录表单，必败还白费一个动态码。见到登录页直接退出，
    #   先去 nexusphp_login.py --site piggo 完成登录（动态码写 /tmp/nx_piggo_2fa.txt），再重跑本脚本。
    if 'login.php' in page.url:
        print(json.dumps({'state': 'need_login', 'url': page.url,
                          'note': '未登录：attendance 被重定向到登录页。先跑 nexusphp_login.py --site piggo 完成登录后重跑本脚本。'},
                         ensure_ascii=False))
        sys.exit(3)

    # 处理「重要公告」弹窗：等按钮去掉 disabled 再点
    clicked = 'none'
    for _ in range(45):
        try:
            clicked = page.evaluate("""() => {
              const btn = document.querySelector('.layui-layer-btn0');
              if (!btn) return 'none';
              if (btn.className.indexOf('disabled') >= 0) return 'disabled';
              btn.click();
              return 'clicked';
            }""")
        except Exception:
            clicked = 'err'
        if clicked == 'clicked':
            break
        page.wait_for_timeout(2000)
    print('announce_click=%s' % clicked, flush=True)
    page.wait_for_timeout(4000)

    b = page.inner_text('body')
    if '签到成功' in b or re.search(r'签到已得', b):
        print(json.dumps({'state': 'already_signed', 'title': page.title(),
                          'snippet': brief(b, 700)}, ensure_ascii=False))
        sys.exit(0)

    # 等 2FA 表单
    have = False
    for _ in range(25):
        try:
            n = page.locator('input[name="two_step_code"]').count()
        except Exception:
            n = 0
        if n > 0:
            have = True
            break
        page.wait_for_timeout(2000)
    print('two_step_form=%s' % have, flush=True)
    if not have:
        print(json.dumps({'state': 'no_2fa_form', 'title': page.title(),
                          'snippet': brief(page.inner_text('body'), 900)}, ensure_ascii=False))
        sys.exit(0)

    print('NEED_2FA', flush=True)
    code = None
    deadline = time.time() + 1800
    while time.time() < deadline:
        if os.path.exists(ANS):
            try:
                code = open(ANS, encoding='utf-8').read().strip()
            except Exception:
                code = None
            if code:
                break
        time.sleep(2)
    if not code:
        print('NO_CODE')
        sys.exit(1)

    page.fill('input[name="two_step_code"]', code)
    page.evaluate("""() => {
      const f = document.querySelector('#input-form-box form') || document.querySelector('form');
      if (!f) return;
      const btn = f.querySelector('input[type="submit"], button[type="submit"], button, input[type="button"]');
      if (btn) btn.click();
    }""")
    page.wait_for_timeout(15000)
    b2 = page.inner_text('body')
    print(json.dumps({'state': 'submitted', 'title': page.title(), 'url': page.url,
                      'snippet': brief(b2, 1000)}, ensure_ascii=False))
