#!/usr/bin/env python3
"""HDU（pt.hdupt.com）纯 HTTP 登录（无浏览器）。NexusPHP 深度定制。

关键（2026-09-30 修正版结论）：
- 之前 curl 登不上 = 没保持 cookie 会话（「你需要启用cookies才能登录」）+ 验证码与
  imagehash/会话绑定。urllib + LWPCookieJar 即解。
- 验证码时效 ≤60 秒（memcached）→ stage1 取图后立即净化识读、尽快提交。
- 登录页无 CF；表单 POST takelogin.php（username/password/imagestring/imagehash + 隐藏项自动收集）。

  --stage1                取验证码 → /tmp/hdu_captcha.png → CAPTCHA_READY
  --stage2 <验证码>        立即提交（目标：距 stage1 ≤60 秒）
  --stage3                （发现用）拉 index.php 打印 qiandao 入口 JS 上下文

cookie：~/.pt-sessions/state/hdu_cookies.txt ；状态：~/.pt-sessions/state/hdu_state.json
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
BASE = 'https://pt.hdupt.com/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/hdu_cookies.txt')
STATE = os.path.expanduser('~/.pt-sessions/state/hdu_state.json')
CAPTCHA_PNG = '/tmp/hdu_captcha.png'
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


def hidden_fields(html, form_action_pat='takelogin'):
    """收集登录表单里的 hidden input（自动适配站点改动）。"""
    m = re.search(r'<form[^>]*%s[^>]*>(.*?)</form>' % form_action_pat, html, re.S | re.I)
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
    open('/tmp/hdu_login_page.html', 'w').write(html)
    if 'name="username"' not in html:
        print('⚠ 登录页异常（可能已是登录态/结构变化）len=%d' % len(html))
    m = re.search(r'name="imagehash"[^>]*value="([^"]+)"', html)
    if not m:
        print('⚠ 未取到 imagehash'); return 1
    imagehash = m.group(1)
    img = op.open(BASE + 'image.php?action=regimage&imagehash=' + imagehash, timeout=45).read()
    open(CAPTCHA_PNG, 'wb').write(img)
    json.dump({'imagehash': imagehash}, open(STATE, 'w'))
    cj.save(ignore_discard=True, ignore_expires=True)
    print('imagehash=%s | 验证码 %d 字节 → %s' % (imagehash[:12] + '...', len(img), CAPTCHA_PNG))
    print('CAPTCHA_READY (提交窗口 ≤60 秒)')
    return 0


def stage2(code):
    user, pwd = creds()
    cj = load_cj()
    op = opener(cj)
    st = json.load(open(STATE))
    html_page = open('/tmp/hdu_login_page.html').read()
    fields = hidden_fields(html_page)
    data = dict(fields)
    data.update({'username': user, 'password': pwd,
                 'imagestring': code, 'imagehash': st['imagehash']})
    r = op.open(BASE + 'takelogin.php', data=urllib.parse.urlencode(data).encode(), timeout=45)
    html = r.read().decode('utf-8', 'ignore')
    url = r.geturl()
    ok = ('欢迎回来' in html or '欢迎回來' in html or ('退出' in html and 'logout' in html.lower())) \
        and 'name="username"' not in html
    print('① 登录: %s (%s)' % ('✅ 成功' if ok else '❌ 失败', url))
    if not ok:
        t = clean(html)
        for kw in ('图片代码', '驗證碼', '验证码', '密码', '密碼', '用户名', 'cookies', '拒绝', '失敗', '失败'):
            i = t.find(kw)
            if i >= 0:
                print('   →', t[max(0, i - 70):i + 150][:230])
                break
        return 1
    cj.save(ignore_discard=True, ignore_expires=True)
    idx = html if '欢迎回来' in html else op.open(BASE + 'index.php', timeout=45).read().decode('utf-8', 'ignore')
    ti = clean(idx)

    def grab(pat):
        m = re.search(pat, ti)
        return m.group(1) if m else None

    print('② 账号: %s | 分享率 %s | 上传 %s | 魔力值 %s | 签到次数 %s' % (
        user, grab(r'分享率[：:]? ?([\d.,]+)'), grab(r'(?:上传量|上传)[^\d]{0,12}([\d.,]+ ?[KMGTP]?B)'),
        grab(r'魔力值[^\d]{0,40}([\d,.]+)'), grab(r'签到次数[：:]? ?(\d+)')))
    # 签到入口状态
    if '[已签到]' in idx or '已签到' in ti[:2000]:
        print('③ 签到: 已是 [已签到]（今天已签）')
    elif 'qiandao' in idx:
        print('③ 签到: 存在 qiandao 入口（未签到状态）')
    return 0


def stage3():
    cj = load_cj()
    op = opener(cj, BASE + 'index.php')
    idx = op.open(BASE + 'index.php', timeout=45).read().decode('utf-8', 'ignore')
    open('/tmp/hdu_index.html', 'w').write(idx)
    for m in re.finditer(r'qiandao', idx):
        i = m.start()
        seg = idx[max(0, i - 400):i + 400].replace('\n', ' ')
        print('--- ctx@%d ---' % i)
        print(seg[:700])
        print()
        break
    # 找 function qiandao 定义
    m = re.search(r'function\s+qiandao[\s\S]{0,1200}?\}', idx)
    if m:
        print('=== function qiandao ===')
        print(m.group(0)[:1200])
    else:
        print('function qiandao 定义未内联，可能在外部 js；列 js 引用：')
        for mm in re.finditer(r'<script[^>]*src="([^"]+)"', idx):
            print('  js:', mm.group(1)[:140])
    return 0


def stage4():
    """HDU 签到：common.js `function qiandao() → ajax.post('added.php', ..., 'action='+action)`"""
    cj = load_cj()
    op = opener(cj, BASE + 'index.php')
    idx = op.open(BASE + 'index.php', timeout=45).read().decode('utf-8', 'ignore')
    if '[已签到]' in idx:
        print('✅ 今天已经签到过（[已签到]）'); return 0
    r = op.open(BASE + 'added.php', data=b'action=qiandao', timeout=45)
    txt = r.read().decode('utf-8', 'ignore')
    print('① 签到响应:', clean(txt)[:160])
    cj.save(ignore_discard=True, ignore_expires=True)
    idx2 = op.open(BASE + 'index.php', timeout=45).read().decode('utf-8', 'ignore')
    m = re.search(r'签到次数[：:]? ?(\d+)', clean(idx2))
    print('② 复核:', ('✅ [已签到]' if '[已签到]' in idx2 else '⚠ 仍未见 [已签到]'),
          '| 签到次数', m.group(1) if m else '?')
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
    if cmd == '--stage4':
        sys.exit(stage4())
    print('参数错误，见文档'); sys.exit(2)
