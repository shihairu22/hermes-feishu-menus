#!/usr/bin/env python3
"""OpenCD（www.open.cd）纯 HTTP 登录 + 签到（无浏览器）。无 CF；登录与签到各带一个图形验证码。

三段式（验证码双路读准后提交，登录验证码读错不扣次数）：
  --stage1             取登录验证码 → /tmp/ocd_captcha.png → 打印 CAPTCHA_READY
  --stage2 <验证码>     提交登录 → 账号数据 → 若未签到则取签到验证码 → SIGNIN_READY
  --stage3 <验证码>     提交签到 → 解析 JSON/用户栏/魔力值 → 复核签到记录页

cookie：~/.pt-sessions/state/opencd_cookies.txt
解释器：/usr/bin/python3
"""
import os  # 家目录展开（去敏时可移植化）
import re
import sys
import json
import urllib.request
import urllib.parse
import http.cookiejar

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://www.open.cd/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/opencd_cookies.txt')
STATE = os.path.expanduser('~/.pt-sessions/state/opencd_state.json')
CAPTCHA_PNG = '/tmp/ocd_captcha.png'
SIGN_PNG = '/tmp/ocd_sign_captcha.png'
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


def opener(cj):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', BASE + 'login.php')]
    return op


def load_cj():
    cj = http.cookiejar.LWPCookieJar(COOKIES)
    try:
        cj.load(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    return cj


def fetch_captcha(op, imagehash, path):
    url = BASE + 'image.php?action=regimage&imagehash=' + urllib.parse.quote(imagehash)
    data = op.open(url, timeout=40).read()
    open(path, 'wb').write(data)
    return len(data)


def stage1():
    cj = load_cj()
    op = opener(cj)
    html = op.open(BASE + 'login.php', timeout=40).read().decode('utf-8', 'ignore')
    if ('退出' in html) and ('name="username"' not in html):
        print('① 已是登录态（cookie 有效）——无需验证码，直接跑 --stage2 check')
    m = re.search(r'name="imagehash"[^>]*value="([^"]+)"', html)
    if not m:
        print('⚠ 未取到 imagehash，登录页结构可能变了'); return 1
    imagehash = m.group(1)
    n = fetch_captcha(op, imagehash, CAPTCHA_PNG)
    json.dump({'imagehash': imagehash}, open(STATE, 'w'))
    cj.save(ignore_discard=True, ignore_expires=True)
    hint = re.search(r'你還有 ?\[?(\d+)\]? ?次嘗試機會|你还有 ?\[?(\d+)\]? ?次尝试机会', clean(html))
    print('imagehash=%s | 验证码图 %d 字节 → %s%s' % (
        imagehash[:12] + '...', n, CAPTCHA_PNG, ' | 剩余尝试: %s' % (hint.group(1) or hint.group(2)) if hint else ''))
    print('CAPTCHA_READY')
    return 0


def stage2(code):
    user, pwd = creds()
    cj = load_cj()
    op = opener(cj)
    st = json.load(open(STATE))
    data = urllib.parse.urlencode({
        'username': user, 'password': pwd,
        'imagestring': code, 'imagehash': st['imagehash'],
    }).encode()
    r = op.open(BASE + 'takelogin.php', data=data, timeout=40)
    html = r.read().decode('utf-8', 'ignore')
    ok = ('退出' in html or '歡迎回來' in html or '欢迎回来' in html) and 'name="username"' not in html
    print('① 登录: %s (%s)' % ('✅ 成功' if ok else '❌ 失败', r.geturl()))
    if not ok:
        t = clean(html)
        for kw in ('登錄失敗', '登录失败', '用戶名或密碼', '用户名或密码', '驗證碼', '验证码', '你還有', '你还有', '禁用'):
            if kw in t:
                i = t.find(kw)
                print('   →', t[max(0, i - 60):i + 120][:180])
                break
        return 1
    cj.save(ignore_discard=True, ignore_expires=True)

    idx = op.open(BASE + 'index.php', timeout=40).read().decode('utf-8', 'ignore')
    ti = clean(idx)

    def grab(pat):
        m = re.search(pat, ti)
        return m.group(1) if m else None

    print('② 账号: %s | 分享率 %s | 上传 %s | 魔力值 %s' % (
        user, grab(r'分享率[：:]? ?([\d.,]+)'), grab(r'上傳量[^\d]{0,12}([\d.,]+ ?[KMGTP]?B)'),
        grab(r'魔力值[^\d]{0,40}([\d,.]+)')))

    signed = ('查看簽到記錄' in idx) or ('查看签到记录' in idx)
    if signed:
        print('③ 签到: ✅ 今天已是签到状态（用户栏显示 查看簽到記錄），无需再签')
        return 0

    # 未签 → 取签到验证码
    plugin = op.open(BASE + 'plugin_sign-in.php', timeout=40).read().decode('utf-8', 'ignore')
    m = re.search(r'name="imagehash"[^>]*value="([^"]+)"', plugin)
    if not m:
        print('③ ⚠ 插件页未取到 imagehash →', clean(plugin)[:200])
        return 2
    imagehash = m.group(1)
    n = fetch_captcha(op, imagehash, SIGN_PNG)
    st2 = dict(st); st2['sign_imagehash'] = imagehash
    json.dump(st2, open(STATE, 'w'))
    cj.save(ignore_discard=True, ignore_expires=True)
    print('③ 签到验证码图 %d 字节 → %s' % (n, SIGN_PNG))
    print('SIGNIN_READY')
    return 0


def stage3(code):
    cj = load_cj()
    op = opener(cj)
    st = json.load(open(STATE))

    def magic():
        try:
            t = clean(op.open(BASE + 'index.php', timeout=40).read().decode('utf-8', 'ignore'))
            m = re.search(r'魔力值[^\d]{0,40}([\d,.]+)', t)
            return m.group(1) if m else '?'
        except Exception:
            return '?'

    before = magic()
    data = urllib.parse.urlencode({
        'imagehash': st.get('sign_imagehash', ''), 'imagestring': code,
    }).encode()
    r = op.open(BASE + 'plugin_sign-in.php?cmd=signin', data=data, timeout=40)
    body = r.read().decode('utf-8', 'ignore')
    jm = re.search(r'\{[^{}]*"state"[^{}]*\}', body)
    print('① 签到响应: %s | %s' % (r.geturl(), (jm.group(0) if jm else clean(body)[:160])))
    after = magic()
    print('② 魔力值: %s → %s' % (before, after))

    # 铁证复核：签到记录页看当天日期
    try:
        log = op.open(BASE + 'plugin_sign-in.php?cmd=show-log', timeout=40).read().decode('utf-8', 'ignore')
        import time as _t
        today = _t.strftime('%Y-%m-%d')
        rows = [clean(x)[:120] for x in re.findall(r'<tr[^>]*>(.*?)</tr>', log, re.S) if today in x]
        if rows:
            print('③ 记录页铁证: %s' % rows[0])
        else:
            print('③ 记录页未见到当天行（可能分页/格式变化），以魔力值与用户栏为准')
    except Exception as exc:
        print('③ 记录页读取失败:', str(exc)[:120])
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    if sys.argv[1] == '--stage1':
        sys.exit(stage1())
    if sys.argv[1] == '--stage2':
        if len(sys.argv) < 3:
            print('用法: --stage2 <验证码>'); sys.exit(2)
        sys.exit(stage2(sys.argv[2].strip()))
    if sys.argv[1] == '--stage3':
        if len(sys.argv) < 3:
            print('用法: --stage3 <验证码>'); sys.exit(2)
        sys.exit(stage3(sys.argv[2].strip()))
    print('未知参数'); sys.exit(2)
