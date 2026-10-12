#!/usr/bin/env python3
"""MonikaDesign（monikadesign.uk）纯 HTTP 登录（仅保活，无签到）。UNIT3D / Laravel。

- 流程：GET /login 取 _token（CSRF）→ POST /login（_token/username/password/remember）
- 成功判据：cookie 出现 monikadesign_session / remember_web_* + 页面出现用户数据
  （⚠️ 勿用「登出/退出」字样判定；URL 可能停在 /login，不单独作判据）
- cookie 持久化：~/.pt-sessions/state/monika_cookies.txt
解释器：/usr/bin/python3
"""
import os  # 家目录展开（去敏时可移植化）
import re
import sys
import ssl
import urllib.request
import urllib.parse
import http.cookiejar

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://monikadesign.uk/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/monika_cookies.txt')
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


def cookie_names(cj):
    return [c.name for c in cj]


def main():
    user, pwd = creds()
    cj = http.cookiejar.LWPCookieJar(COOKIES)
    try:
        cj.load(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9')]

    # 0) 登录态探测
    home = op.open(BASE, timeout=40).read().decode('utf-8', 'ignore')
    logged = (user in home) and ('/login' not in home.split('</head>')[0])

    if logged:
        print('① 登录: 已是登录态（cookie 有效）')
    else:
        # 1) 取 CSRF token
        login_html = op.open(BASE + 'login', timeout=40).read().decode('utf-8', 'ignore')
        m = re.search(r'name="_token"[^>]*value="([^"]+)"', login_html)
        if not m:
            m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', login_html)
        if not m:
            print('⚠ 未取到 _token，登录页结构可能变了'); return 1
        token = m.group(1)

        # 2) 提交登录
        data = urllib.parse.urlencode({
            '_token': token, 'username': user, 'password': pwd, 'remember': 'on',
        }).encode()
        r = op.open(BASE + 'login', data=data, timeout=40)
        html = r.read().decode('utf-8', 'ignore')
        names = cookie_names(cj)
        has_sess = any('session' in n for n in names)
        body_ok = ('分享率' in html) or ('上传' in html) or (user in html)
        ok = has_sess and body_ok
        print('① 登录: %s (URL=%s) | cookies: %s' % (
            '✅ 成功' if ok else '❌ 失败', r.geturl(), ','.join(names[:6])))
        if not ok:
            print('   →', clean(html)[:220])
            return 1
        home = html

    cj.save(ignore_discard=True, ignore_expires=True)

    # 3) 账号状态（保活完成）
    def grab(pat, src):
        m = re.search(pat, src, re.S)
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip() if m else None

    print('② 账号: %s | 分享率 %s | 上传 %s | BON %s' % (
        user,
        grab(r'分享率[：:][^\d]{0,10}([\d.,]+)', home),
        grab(r'上传量[^\d]{0,20}([\d.,]+\s*[KMGT]?i?B)', home),
        grab(r'BON[^\d]{0,60}([\d.,]+)', home)))
    print('③ 本站无签到 → 登录保活完成 ✅')
    return 0


if __name__ == '__main__':
    sys.exit(main())
