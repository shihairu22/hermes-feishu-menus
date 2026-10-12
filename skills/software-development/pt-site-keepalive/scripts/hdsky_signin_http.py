#!/usr/bin/env python3
"""HDSky 签到（showup 弹层）—— 纯 HTTP 版（无浏览器，秒级完成）。

端点是 2026-10-04 从站点 common.js 的 `initshowupajax()` / `#showup` click 处理里读出来的：
  ① POST image_code_ajax.php  data={action:new}          → {"success":true,"code":"<32位imagehash>"}
  ② GET  image.php?action=regimage&imagehash=<code>      → 验证码图（低饱和深色文字+彩噪 → captcha_dotmatrix.py lowsat）
  ③ POST showup.php           data={action:showup,imagehash:<code>,imagestring:<验证码>}
                                                          → {"success":true,"message":N}（N=本次魔力）

用法：
  /usr/bin/python3 scripts/hdsky_signin_http.py --stage1        # 取图 + 打点阵 + 存 imagehash（零消耗，可反复）
  /usr/bin/python3 scripts/hdsky_signin_http.py --stage2 <验证码>

注意：登录态走 ~/.pt-sessions/state/hdsky_cookies.txt（`hdsky_http.py` 那套持久 cookie）；
      已签到时 showup.php 会回 message 或页面显示「已签到(Showed Up)」，不要重复提交。
实测 2026-10-04：双路一致 D49985 → 一次过 +12 魔力。
"""
import os  # 家目录展开（去敏时可移植化）
import sys, re, json, subprocess, urllib.request, urllib.parse, http.cookiejar

BASE = 'https://hdsky.me/'
CJ = os.path.expanduser('~/.pt-sessions/state/hdsky_cookies.txt')
PNG = '/tmp/hdsky_signin_captcha.png'
STATE = os.path.expanduser('~/.pt-sessions/state/hdsky_signin_state.json')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def opener():
    cj = http.cookiejar.LWPCookieJar(CJ)
    try:
        cj.load(ignore_discard=True)
    except Exception:
        pass
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', BASE + 'index.php')]
    return op, cj


def stage1():
    op, cj = opener()
    r = op.open(urllib.request.Request(BASE + 'image_code_ajax.php',
               data=urllib.parse.urlencode({'action': 'new'}).encode()), timeout=45)
    body = r.read().decode('utf-8', 'ignore')
    print('image_code_ajax →', body[:200])
    try:
        d = json.loads(body)
    except Exception:
        print('❌ 响应非 JSON'); return 1
    code = d.get('code') or ''
    if not code:
        print('❌ 未取到 imagehash'); return 1
    img = op.open(BASE + 'image.php?action=regimage&imagehash=' + code, timeout=45).read()
    open(PNG, 'wb').write(img)
    json.dump({'imagehash': code}, open(STATE, 'w'))
    print('验证码图 %d 字节 → %s  imagehash=%s' % (len(img), PNG, code))
    subprocess.run(['/usr/bin/python3',
                    os.path.expanduser('~/.hermes/skills/software-development/pt-site-keepalive/scripts/captcha_dotmatrix.py'),
                    PNG, 'lowsat'])
    print('CAPTCHA_READY')
    return 0


def stage2(ans):
    st = json.load(open(STATE))
    op, cj = opener()
    data = urllib.parse.urlencode({'action': 'showup', 'imagehash': st['imagehash'], 'imagestring': ans}).encode()
    r = op.open(urllib.request.Request(BASE + 'showup.php', data=data), timeout=45)
    body = r.read().decode('utf-8', 'ignore')
    print('showup.php →', body[:300])
    if '"success":true' in body.replace(' ', ''):
        m = re.search(r'"message":(\d+)', body)
        print('✅ 签到成功 魔力 +%s' % (m.group(1) if m else '?'))
    else:
        print('❌ 未成功')
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--stage1':
        sys.exit(stage1())
    if len(sys.argv) > 2 and sys.argv[1] == '--stage2':
        sys.exit(stage2(sys.argv[2]))
    print('用法: --stage1 | --stage2 <验证码>')
