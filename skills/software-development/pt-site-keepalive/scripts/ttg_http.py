#!/usr/bin/env python3
"""TTG（totheglory.im）纯 HTTP 登录 + 签到（无浏览器）。

⚠ 红线：登录页写明「6 次失败登录封 IP」→ 只干净提交一次；失败即停，不重试。
状态（2026-09-30 实测）：GET login.php 无 CF 阻塞（CF JSD 被动层不挡页面）；
表单 POST takelogin.php（multipart/form-data），字段 username/password/passan(空)/
passid=0/lang=0（简体）；无验证码、无双重验证。cf_clearance 为浏览器遗留，HTTP 直连
不需要（GET 实测直达真页面）。
签到：AJAX POST signed.php {signed_timestamp, signed_token}，token 从 index.php
内联 JS 现取（每次加载页面都会变）。

  --stage1   勘察登录页（真实性校验：有 [6] 次提示 + 表单才算干净，否则停）
  --stage2   提交登录（只一次）
  --stage3   签到（已签到则只报告）

cookie：~/.pt-sessions/state/ttg_cookies.txt
解释器：/usr/bin/python3
"""
import re
import sys
import ssl
import json
import random
import urllib.request
import urllib.parse
import http.cookiejar

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://totheglory.im/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/ttg_cookies.txt')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def creds():
    env = {}
    for line in open(ENV):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env['MTEAM_USERNAME'], env['MTEAM_PASSWORD']


def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s or '')).strip()


def load_cj():
    cj = http.cookiejar.LWPCookieJar(COOKIES)
    try:
        cj.load(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    return cj


def opener(cj, referer=None):
    ctx = ssl.create_default_context()
    ctx.set_ciphers('DEFAULT@SECLEVEL=1')
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=ctx))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', referer or BASE + 'login.php')]
    return op


def multipart(fields):
    b = '----WebKitFormBoundary' + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16))
    body = b''
    for k, v in fields:
        body += ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, v)).encode()
    body += ('--%s--\r\n' % b).encode()
    return body, 'multipart/form-data; boundary=' + b


def stage1():
    # 已登录过就直接查状态
    try:
        cj = load_cj()
        op = opener(cj, BASE + 'index.php')
        idx = op.open(BASE + 'index.php', timeout=45).read().decode('utf-8', 'ignore')
        if '欢迎回来' in idx:
            print('① 已持有效会话（index 欢迎回来）→ 可直接 --stage3'); return 0
    except Exception:
        pass
    cj = load_cj()
    op = opener(cj)
    r = op.open(BASE + 'login.php', timeout=45)
    html = r.read().decode('utf-8', 'ignore')
    open('/tmp/ttg_login_page.html', 'w').write(html)
    low = html.lower()
    # CF JSD 被动层会在正常页面里内嵌 challenge-platform/scripts/jsd 片段——不算墙；
    # 硬墙特征是整页 「just a moment」 或 cf-chl- 挑战元素，或页面里根本没有登录表单。
    cf_block = ('just a moment' in low) or ('cf-chl-' in low) or ('takelogin' not in html)
    has_tries = ('次失败登录' in html and '次登录机会' in html)
    has_form = 'takelogin.php' in html and 'name="username"' in html
    print('status=%s len=%d cf_hard_block=%s tries_text=%s form=%s' % (
        r.status, len(html), cf_block, has_tries, has_form))
    if cf_block or not (has_tries and has_form):
        print('❌ 页面非真登录页 → 停止，不作为（保浏览器路径）'); return 2
    print('① 登录页干净（含额度提示+表单）→ 可以 --stage2（只提交一次）')
    return 0


def stage2():
    import os
    if not os.path.exists('/tmp/ttg_login_page.html'):
        print('⚠ 先跑 --stage1 并确认干净再提交'); return 2
    page = open('/tmp/ttg_login_page.html').read()
    if '次失败登录' not in page or 'takelogin.php' not in page:
        print('⚠ stage1 页面未通过校验，拒绝提交'); return 2
    user, pwd = creds()
    cj = load_cj()
    op = opener(cj)
    body, ctype = multipart([('username', user), ('password', pwd), ('passan', ''),
                             ('passid', '0'), ('lang', '0')])
    req = urllib.request.Request(BASE + 'takelogin.php', data=body)
    req.add_header('Content-Type', ctype)
    req.add_header('User-Agent', UA)
    req.add_header('Accept-Language', 'zh-CN,zh;q=0.9')
    req.add_header('Referer', BASE + 'login.php')
    req.add_header('Origin', BASE.rstrip('/'))
    try:
        r = op.open(req, timeout=45)
        html = r.read().decode('utf-8', 'ignore')
        url = r.geturl()
        status = r.status
    except urllib.error.HTTPError as e:
        html = e.read().decode('utf-8', 'ignore')
        url, status = e.geturl(), e.code
    low = html.lower()
    if status == 403 or 'just a moment' in low or 'challenge-platform' in low:
        print('❌ CF 拦截 POST（status=%s）→ 不重试，TTG 保持浏览器路径' % status)
        return 2
    ok = ('欢迎回来' in html or ('退出' in html and 'takelogin.php' not in html[:3000])) and status == 200
    print('① 登录: %s (status=%s url=%s)' % ('✅ 成功' if ok else '❌ 失败', status, url))
    if not ok:
        t = clean(html)
        for kw in ('密码', '密碼', '用户名', '用戶名', '安全提问', '安全問題', '尝试', '錯誤', '错误'):
            i = t.find(kw)
            if i >= 0:
                print('   →', t[max(0, i - 70):i + 160][:240])
                break
        print('⚠ 失败一次即停（剩余额度宝贵），保浏览器路径')
        return 1
    cj.save(ignore_discard=True, ignore_expires=True)
    ti = clean(html)
    m = re.search(r'欢迎回来[，, ]*([\w\u4e00-\u9fff]+)', ti)
    print('② 账号:', m.group(1) if m else user)

    def grab(pat):
        m2 = re.search(pat, ti)
        return m2.group(1) if m2 else None

    print('   分享率 %s | 上传 %s | 积分 %s | HP %s' % (
        grab(r'分享率[：:]? ?([\d.,]+)'), grab(r'(?:上传量|上传)[^\d]{0,12}([\d.,]+ ?[KMGTP]?B)'),
        grab(r'积分[：:]? ?([\d,.]+)'), grab(r'HP[：:]? ?(\d+)')))
    return 0


def stage3():
    cj = load_cj()
    op = opener(cj, BASE + 'index.php')
    idx = op.open(BASE + 'index.php', timeout=45).read().decode('utf-8', 'ignore')
    open('/tmp/ttg_index.html', 'w').write(idx)
    if '已签到' in idx and 'id="signed"' not in idx:
        print('✅ 今天已签到（用户栏 已签到）'); return 0
    m1 = re.search(r'signed_timestamp:\s*"(\d+)"', idx) or re.search(r'signed_timestamp["\']?\s*[:=]\s*["\']?(\d+)', idx)
    m2 = re.search(r'signed_token:\s*"(\w+)"', idx) or re.search(r'signed_token["\']?\s*[:=]\s*["\']?(\w+)', idx)
    if not (m1 and m2):
        print('⚠ 未在页面找到 signed_timestamp/signed_token；上下文：')
        i = idx.find('signed')
        print(idx[max(0, i - 300):i + 800].replace('\n', ' ')[:900])
        return 1
    data = urllib.parse.urlencode({'signed_timestamp': m1.group(1), 'signed_token': m2.group(1)}).encode()
    req = urllib.request.Request(BASE + 'signed.php', data=data)
    req.add_header('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8')
    req.add_header('X-Requested-With', 'XMLHttpRequest')
    req.add_header('User-Agent', UA)
    req.add_header('Referer', BASE + 'index.php')
    req.add_header('Origin', BASE.rstrip('/'))
    try:
        r = op.open(req, timeout=45)
        txt = r.read().decode('utf-8', 'ignore')
        print('① 签到响应:', clean(txt)[:200])
    except urllib.error.HTTPError as e:
        print('① 签到 HTTP 错误:', e.code, e.read().decode('utf-8', 'ignore')[:200])
        return 1
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    cmd = sys.argv[1]
    if cmd == '--stage1':
        sys.exit(stage1())
    if cmd == '--stage2':
        sys.exit(stage2())
    if cmd == '--stage3':
        sys.exit(stage3())
    print('参数错误，见文档'); sys.exit(2)
