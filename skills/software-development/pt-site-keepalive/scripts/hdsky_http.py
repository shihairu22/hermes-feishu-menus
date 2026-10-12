#!/usr/bin/env python3
"""HDSky（hdsky.me）纯 HTTP 登录（无浏览器）。NexusPHP 定制。

关键：登录验证码难读（历史视觉model判错 CD1PBF/C98D15）→ 按既定纪律：
  captcha_clean.py 净化放大 → **发给用户代读** → 用户回 6 位 → 立刻提交。
  10 次失败额度，用户读完才提交，绝不自动猜。
无 CF。登录页 /login.php；表单 POST takelogin.php（username/password/imagestring/
imagehash/oneCode + 隐藏项）；成功判据 index.php + 欢迎回来 + 退出。

  --stage1                取验证码 → /tmp/hdsky_captcha.png → CAPTCHA_READY
  --stage2 <验证码>        提交登录
  --stage3                发现用：拉 index.php 打印 #showup 签到入口上下文

cookie：~/.pt-sessions/state/hdsky_cookies.txt ；状态：~/.pt-sessions/state/hdsky_state.json
解释器：/usr/bin/python3
"""
import os  # 家目录展开（去敏时可移植化）
import re
import sys
import json
import ssl
import urllib.request
import urllib.parse
import http.cookiejar

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://hdsky.me/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/hdsky_cookies.txt')
STATE = os.path.expanduser('~/.pt-sessions/state/hdsky_state.json')
CAPTCHA_PNG = '/tmp/hdsky_captcha.png'
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


def hidden_fields(html):
    m = re.search(r'<form[^>]*takelogin[^>]*>(.*?)</form>', html, re.S | re.I)
    form = m.group(1) if m else html
    out = {}
    for mm in re.finditer(r'<input[^>]*type="hidden"[^>]*>', form, re.I):
        tag = mm.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n:
            out[n.group(1)] = v.group(1) if v else ''
    return out


def stage1():
    cj = load_cj()
    op = opener(cj)
    html = op.open(BASE + 'login.php', timeout=45).read().decode('utf-8', 'ignore')
    open('/tmp/hdsky_login_page.html', 'w').write(html)
    m = re.search(r'name="imagehash"[^>]*value="([^"]+)"', html)
    if not m:
        print('⚠ 未取到 imagehash len=%d' % len(html)); return 1
    imagehash = m.group(1)
    img = op.open(BASE + 'image.php?action=regimage&imagehash=' + imagehash, timeout=45).read()
    open(CAPTCHA_PNG, 'wb').write(img)
    json.dump({'imagehash': imagehash}, open(STATE, 'w'))
    cj.save(ignore_discard=True, ignore_expires=True)
    print('imagehash=%s | 验证码 %d 字节 → %s' % (imagehash[:12] + '...', len(img), CAPTCHA_PNG))
    print('CAPTCHA_READY')
    return 0


def stage2(code):
    user, pwd = creds()
    cj = load_cj()
    op = opener(cj)
    st = json.load(open(STATE))
    fields = hidden_fields(open('/tmp/hdsky_login_page.html').read())
    data = dict(fields)
    data.update({'username': user, 'password': pwd, 'oneCode': '',
                 'imagestring': code, 'imagehash': st['imagehash']})
    r = op.open(BASE + 'takelogin.php', data=urllib.parse.urlencode(data).encode(), timeout=45)
    html = r.read().decode('utf-8', 'ignore')
    url = r.geturl()
    ok = ('欢迎回来' in html or ('退出' in html and 'logout' in html.lower())) and 'name="username"' not in html
    print('① 登录: %s (%s)' % ('✅ 成功' if ok else '❌ 失败', url))
    if not ok:
        t = clean(html)
        for kw in ('验证码', '图片代码', '密码', '密碼', '用户名', '禁止', '拒绝'):
            i = t.find(kw)
            if i >= 0:
                print('   →', t[max(0, i - 70):i + 160][:240])
                break
        return 1
    cj.save(ignore_discard=True, ignore_expires=True)
    idx = html if '欢迎回来' in html else op.open(BASE + 'index.php', timeout=45).read().decode('utf-8', 'ignore')
    ti = clean(idx)

    def grab(pat):
        m = re.search(pat, ti)
        return m.group(1) if m else None

    print('② 账号: %s | 分享率 %s | 上传 %s | 魔力值 %s' % (
        user, grab(r'分享率[：:]? ?([\d.,]+)'), grab(r'(?:上传量|上传)[^\d]{0,12}([\d.,]+ ?[KMGTP]?B)'),
        grab(r'魔力值[^\d]{0,40}([\d,.]+)')))
    if '已签到' in idx:
        print('③ 签到入口: 疑似 [已签到]')
    elif 'showup' in idx.lower() or '签到' in idx:
        print('③ 签到入口: 存在（未签到状态）')
    return 0


def stage3():
    cj = load_cj()
    op = opener(cj, BASE + 'index.php')
    idx = op.open(BASE + 'index.php', timeout=45).read().decode('utf-8', 'ignore')
    open('/tmp/hdsky_index.html', 'w').write(idx)
    for kw in ('showup', 'showupbutton', 'showupimg'):
        i = idx.lower().find(kw)
        if i >= 0:
            print('--- %s ctx @%d ---' % (kw, i))
            print(idx[max(0, i - 500):i + 700].replace('\n', ' ')[:1100])
            print()
    m = re.search(r'function\s+showup[\s\S]{0,1500}?\n\}', idx)
    if m:
        print('=== function showup ===')
        print(m.group(0)[:1500])
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    cmd = sys.argv[1]
    if cmd == '--stage1':
        sys.exit(stage1())
    if cmd == '--stage2' and len(sys.argv) > 2:
        sys.exit(stage2(sys.argv[2].strip()))
    if cmd == '--stage3':
        sys.exit(stage3())
    print('参数错误，见文档'); sys.exit(2)
