#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UBits（ubits.club）专用登录 + 签到 —— 「Turnstile 令牌未就绪绝不提交」。

为什么单独写：通用 nexusphp_login.py 只等 60 秒令牌；实测 UBits 的 Turnstile
widget 在 DOM 里要 ~30 秒才渲染出 token，CF 挑战慢时通用脚本会带着长度 0 的令牌
盲提交，换回「人机验证未通过」，白耗一次尝试（UBits 连续 6 次失败封 IP）。

安全设计：
  1. 先判登录态，已登录直接进签到
  2. 等表单 + 等 Turnstile token 长度 > 20，最多 180 秒
  3. ★ 令牌没就绪 → 直接中止，**不提交**
  4. 提交后按「退出/欢迎回来」判成功，失败不重试

cookie 存 ~/.pt-sessions/state/ubits_cookies.txt
"""
import json
import os
import re
import sys
import time

from camoufox.sync_api import Camoufox

ENV = os.path.expanduser('~/.pt-sessions/.env')
PROFILE = os.path.expanduser('~/.pt-sessions/ubits-login-session')
BASE = 'https://ubits.club/'
LOGIN = BASE + 'login.php'
OUT = os.path.expanduser('~/.pt-sessions/state/ubits_state.json')
TOKEN_WAIT = 180          # 等 Turnstile 令牌的最长秒数
res = {'site': 'ubits'}


def env():
    d = {}
    for line in open(ENV):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def txt(page, tries=25):
    for _ in range(tries):
        try:
            if page.evaluate('() => !!document.body'):
                return re.sub(r'\s+', ' ', page.evaluate('() => document.body.innerText'))
        except Exception:
            pass
        page.wait_for_timeout(400)
    return ''


def tok(page):
    try:
        return page.evaluate(
            """() => (document.querySelector('input[name="cf-turnstile-response"]') || {}).value || ''""")
    except Exception:
        return ''


def main():
    e = env()
    USER, PWD = e.get('MTEAM_USERNAME', ''), e.get('MTEAM_PASSWORD', '')
    res['cred'] = {'user_len': len(USER), 'pwd_len': len(PWD)}
    with Camoufox(headless=False, humanize=True, os='windows',
                  persistent_context=True, user_data_dir=PROFILE) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(BASE + 'index.php', wait_until='domcontentloaded', timeout=90000)
        page.wait_for_timeout(5000)
        t = txt(page)
        if '退出' in t or '欢迎回来' in t:
            print('[i] 已保存会话仍有效，跳过登录', flush=True)
            res['already_in'] = True
        else:
            page.goto(LOGIN, wait_until='domcontentloaded', timeout=90000)
            # 等表单
            for _ in range(60):
                if page.evaluate("""() => !!document.querySelector('input[name="username"]')"""):
                    break
                page.wait_for_timeout(1000)
            print('  ③ 登录页:', page.url, flush=True)
            # ★ 等 Turnstile 令牌就绪
            t0, token = time.time(), ''
            while time.time() - t0 < TOKEN_WAIT:
                token = tok(page)
                if len(token) > 20:
                    break
                page.wait_for_timeout(2000)
            print('  ⑤ Turnstile 令牌长度=%d（等待 %ds）' % (len(token), int(time.time() - t0)), flush=True)
            if len(token) <= 20:
                print('  ⛔ 令牌未就绪 → 中止，不提交（不白耗尝试次数）', flush=True)
                return 'no_token'
            page.fill('input[name="username"]', USER)
            page.fill('input[name="password"]', PWD)
            page.wait_for_timeout(500)
            if len(tok(page)) <= 20:
                print('  ⛔ 填表后令牌失效 → 中止，不提交', flush=True)
                return 'no_token'
            print('  ⑥ 令牌就绪，提交', flush=True)
            page.evaluate("""() => {
                const b = document.querySelector('input[type="submit"], button[type="submit"]')
                       || [...document.querySelectorAll('input,button')].find(x => /登\\s*录|登录/i.test(x.value || x.innerText || ''));
                if (b) b.click();
            }""")
            page.wait_for_timeout(9000)
            t2 = txt(page)
            still = page.evaluate("""() => !!document.querySelector('input[name="username"]')""")
            ok = (not still) and ('退出' in t2 or '欢迎回来' in t2)
            print('  ⑦ 登录：%s | URL=%s' % ('✅ 成功' if ok else '❌ 失败', page.url), flush=True)
            if not ok:
                print('     片段：%s' % t2[:240], flush=True)
                res['login_ok'] = False
                json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=2)
                return 'login_failed'
            res['login_ok'] = True
        # 签到：首页用户栏 [签到得U币]
        t3 = txt(page)
        m = re.search(r'\[签到已得([^\]]*)\]', t3)
        if m:
            print('  ⑧ 已签到过：签到已得%s' % m.group(1), flush=True)
            res['signin'] = 'already'
        else:
            page.goto(BASE + 'attendance.php', wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(4000)
            t4 = txt(page)
            for kw in ('签到成功', '已签到', '获得', 'U币'):
                i = t4.find(kw)
                if i >= 0:
                    print('  ⑧ 签到页：%s' % t4[max(0, i - 50):i + 150], flush=True)
                    res['signin'] = t4[max(0, i - 50):i + 150]
                    break
            else:
                print('  ⑧ 签到页未见签到文字：%s' % t4[:200], flush=True)
                res['signin'] = 'unknown'
        page.goto(BASE + 'index.php', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(3000)
        t5 = txt(page)
        for kw in ('分享率', '上传量', '魔力值', '签到已得'):
            i = t5.find(kw)
            if i >= 0:
                res.setdefault('bar', '')
                res['bar'] += t5[max(0, i - 30):i + 120] + ' | '
        print('  ⑨ 用户栏:', res.get('bar', '')[:400], flush=True)
        page.screenshot(path='/tmp/ubits_after_login.png')
        json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=2)
    return 'ok'


if __name__ == '__main__':
    sys.exit(0 if main() in ('ok', 'no_token') else 1)
