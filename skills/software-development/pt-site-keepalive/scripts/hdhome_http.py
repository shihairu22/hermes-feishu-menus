#!/usr/bin/env python3
"""HDHome（hdhome.org）纯 HTTP 登录 + 签到（无浏览器、无验证码、无 CF）。

- 登录：POST takelogin.php（username/password/scode；不带任何复选框字段）
- 签到：GET attendance.php 打开即自动签
- cookie 持久化：~/.pt-sessions/state/hdhome_cookies.txt（cookie 有效时跳过登录）
解释器：/usr/bin/python3（系统 Python，含 urllib 即可）
"""
import os  # 家目录展开（去敏时可移植化）
import re
import sys
import urllib.request
import urllib.parse
import http.cookiejar

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://hdhome.org/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/hdhome_cookies.txt')
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


def main():
    user, pwd = creds()
    cj = http.cookiejar.LWPCookieJar(COOKIES)
    try:
        cj.load(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', BASE + 'login.php')]

    # 0) 登录态探测（cookie 有效则跳过登录）
    idx = op.open(BASE + 'index.php', timeout=40).read().decode('utf-8', 'ignore')
    logged = ('欢迎回来' in idx) and ('name="username"' not in idx)

    if logged:
        print('① 登录: 已是登录态（cookie 有效）')
    else:
        # 1) 冷登录
        login_html = op.open(BASE + 'login.php', timeout=40).read().decode('utf-8', 'ignore')
        if 'name="username"' not in login_html:
            print('⚠ 登录页无表单（可能页面改版或可达性问题），中止'); return 1
        data = urllib.parse.urlencode({
            'username': user, 'password': pwd, 'scode': '',
        }).encode()
        r = op.open(BASE + 'takelogin.php', data=data, timeout=40)
        html = r.read().decode('utf-8', 'ignore')
        ok = ('欢迎回来' in html) and ('name="username"' not in html) or 'index.php' in r.geturl()
        print('① 登录: %s (%s)' % ('✅ 成功' if ok else '❌ 失败', r.geturl()))
        if not ok:
            for kw in ('密码', '用户名', '尝试', '禁用', '验证'):
                if kw in html:
                    i = html.find(kw)
                    print('   →', clean(html[max(0, i - 90):i + 130])[:180])
                    break
            return 1
        idx = html if '欢迎回来' in html else op.open(BASE + 'index.php', timeout=40).read().decode('utf-8', 'ignore')

    cj.save(ignore_discard=True, ignore_expires=True)

    # 2) 账号状态
    def grab(pat, src=idx):
        m = re.search(pat, src, re.S)
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip() if m else None

    print('② 账号: %s | 分享率 %s | 上传 %s | 魔力值 %s' % (
        user,
        grab(r'分享率[：:][^\d]{0,10}([\d.,]+)'),
        grab(r'上传量[^\d]{0,20}([\d.,]+\s*[KMGT]?i?B)'),
        grab(r'魔力值[^\d]{0,40}([\d.,]+)')))

    # 3) 签到（attendance.php 打开即自动签）
    ah = op.open(BASE + 'attendance.php', timeout=40).read().decode('utf-8', 'ignore')
    m = re.search(r'这是您的第\s*(\d+)\s*次签到[^。]*。', clean(ah))
    if m:
        print('③ 签到: ✅ 第 %s 次 | %s' % (m.group(1), m.group(0)[:90]))
    elif '签到已得' in ah:
        i = ah.find('签到已得')
        print('③ 签到: ✅ 已是签到状态 →', clean(ah[max(0, i - 60):i + 80])[:120])
    elif '已经签到' in ah:
        print('③ 签到: ✅ 今天已经签到过')
    else:
        print('③ 签到: 未发现签到标记，人工核对 →', clean(ah)[:160])
    return 0


if __name__ == '__main__':
    sys.exit(main())
