#!/usr/bin/env python3
"""U2（u2.dmhy.org）纯 HTTP 登录 + 签到（无浏览器）。

要点（2026-09-30 实探）：
- 登录用「旧设备入口」portalbc.php（无 JS，专给 legacy devices），表单 action=takelogin.php
  字段：login_type=email / username=邮箱 / password / otp_code(2FA) / captcha(4位)
  验证码图 captcha.php?sid=<hex> 可直接下载（108×40，与 u2 净化器同规格）
  ⚠ 不发 logout / securelogin（复选框一律不带）
- 2FA 动态码由用户提供（写 /tmp/u2_2fa_code.txt 或命令行传入）
- 签到 showup.php：POST ?action=show，字段 _csrf / message(≥5字) / req / hash / form
  + 点选的 captcha_<md5>=<作品名>（4 个按钮，每局随机名）；题目图 image.php?action=adbc2&req=...
  圆点题解法见 u2.md（本地绿点扫描 u2_dot_locate.py + 视觉辨认所在侧封面）

cookie：~/.pt-sessions/state/u2_cookies.txt ；状态：~/.pt-sessions/state/u2_state.json
解释器：/usr/bin/python3
"""
import os  # 家目录展开（去敏时可移植化）
import re
import sys
import json
import time
import urllib.request
import urllib.parse
import http.cookiejar

ENV = os.path.expanduser('~/.pt-sessions/.env')
BASE = 'https://u2.dmhy.org/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/u2_cookies.txt')
STATE = os.path.expanduser('~/.pt-sessions/state/u2_state.json')
CAPTCHA_PNG = '/tmp/u2_captcha.png'
PUZZLE_PNG = '/tmp/u2_puzzle.png'
OTP_FILE = '/tmp/u2_2fa_code.txt'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def creds():
    env = {}
    for line in open(ENV):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env['U2_EMAIL'], env['U2_PASSWORD']


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
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', referer or BASE + 'portalbc.php')]
    return op


def stage1():
    cj = load_cj()
    op = opener(cj)
    html = op.open(BASE + 'portalbc.php', timeout=40).read().decode('utf-8', 'ignore')
    if 'form-login' not in html and 'takelogin.php' not in html:
        print('① 可能已是登录态（无登录表单）→ 可直接跑 --stage3')
        return 0
    m = re.search(r'captcha\.php\?sid=([0-9a-f]+)', html)
    if not m:
        print('⚠ 未找到 captcha.php?sid=，页面结构可能变了'); return 1
    sid = m.group(1)
    img = op.open(BASE + 'captcha.php?sid=' + sid, timeout=40).read()
    open(CAPTCHA_PNG, 'wb').write(img)
    json.dump({'sid': sid}, open(STATE, 'w'))
    cj.save(ignore_discard=True, ignore_expires=True)
    print('captcha sid=%s | 验证码图 %d 字节 → %s' % (sid, len(img), CAPTCHA_PNG))
    print('CAPTCHA_READY')
    return 0


def stage2(captcha, otp=''):
    user, pwd = creds()
    if not otp:
        # 等 2FA 文件（最多 120 秒）
        for _ in range(60):
            try:
                otp = open(OTP_FILE, encoding='utf-8').read().strip()
            except Exception:
                otp = ''
            if otp:
                break
            time.sleep(2)
    if not otp:
        print('⚠ 未拿到 2FA 动态码（/tmp/u2_2fa_code.txt 或命令行第 3 参）'); return 2

    cj = load_cj()
    op = opener(cj)
    data = urllib.parse.urlencode({
        'login_type': 'email', 'username': user, 'password': pwd,
        'otp_code': otp, 'captcha': captcha,
    }).encode()
    r = op.open(BASE + 'takelogin.php', data=data, timeout=40)
    html = r.read().decode('utf-8', 'ignore')
    url = r.geturl()
    t = clean(html)
    ok = ('欢迎回来' in t or '歡迎回來' in t or '退出' in t or 'logout.php' in html) and 'form-login' not in html
    print('① 登录: %s (%s)' % ('✅ 成功' if ok else '❌ 失败', url))
    if not ok:
        for kw in ('验证码', '驗證碼', '密码', '密碼', 'attempts', 'banned', '2FA', 'otp', 'credential'):
            i = t.lower().find(kw.lower())
            if i >= 0:
                print('   →', t[max(0, i - 80):i + 140][:200])
                break
        return 1
    cj.save(ignore_discard=True, ignore_expires=True)

    idx = html if '欢迎回来' in t else op.open(BASE + 'index.php', timeout=40).read().decode('utf-8', 'ignore')
    ti = clean(idx)

    def grab(pat):
        m = re.search(pat, ti)
        return m.group(1) if m else None

    print('② 账号: 分享率 %s | 上传 %s | UCoin %s' % (
        grab(r'分享率[：:]? ?([\d.,]+)'), grab(r'上传量[^\d]{0,16}([\d.,]+ ?[KMGT]?i?B)'),
        grab(r'UCoin[^\d]{0,20}([\d,]+)')))
    return 0


def stage3():
    cj = load_cj()
    op = opener(cj, BASE + 'showup.php')
    html = op.open(BASE + 'showup.php', timeout=40).read().decode('utf-8', 'ignore')
    if 'form-login' in html or 'takelogin.php' in html[:3000] and 'showup' not in html.lower():
        print('❌ 未登录（被送回登录页）→ 先跑 --stage1/--stage2'); return 2
    t = clean(html)
    if '已签到' in t and '立即签到' not in t:
        print('✅ 今天已经签到过：[已签到] 标记存在')
        return 0
    if 'showup.php?action=show' not in html and 'name="_csrf"' not in html:
        print('⚠ 页面无签到表单 →', t[:240]); return 0

    def h(name):
        m = re.search(r'name="%s"[^>]*value="([^"]*)"' % name, html)
        return m.group(1) if m else ''

    csrf, req, hsh, form = h('_csrf'), h('req'), h('hash'), h('form')
    # 4 个选项按钮：name="captcha_<md5>" value="作品名"
    # ★ 同时记下 name→value 映射：showup.php 每次加载都出新题，
    #   必须用「同一次页面加载」里的按钮名提交，否则选项对不上（旧版的坑）。
    opts, pairs = [], []
    for tag in re.findall(r'<(?:button|input)\b[^>]*captcha_[0-9a-f]+[^>]*>', html):
        nm = re.search(r'name="(captcha_[0-9a-f]+)"', tag)
        vm = re.search(r'value="([^"]*)"', tag)
        if nm and vm:
            pairs.append([nm.group(1), vm.group(1)])
            opts.append(vm.group(1))
    pm = re.search(r'(image\.php\?action=adbc2&(?:amp;)?req=[^"\']+)', html)
    img_ok = False
    if pm:
        img = op.open(BASE + pm.group(1).replace('&amp;', '&'), timeout=40).read()
        open(PUZZLE_PNG, 'wb').write(img)
        img_ok = len(img) > 1000

    json.dump({'csrf': csrf, 'req': req, 'hash': hsh, 'form': form,
               'options': opts, 'pairs': pairs},
              open(STATE, 'w'), ensure_ascii=False)
    print('PUZZLE_READY ' + json.dumps({
        'img': PUZZLE_PNG if img_ok else None,
        'options': opts, 'csrf_ok': bool(csrf)}, ensure_ascii=False, indent=1))
    return 0


def stage4(ans):
    cj = load_cj()
    op = opener(cj, BASE + 'showup.php')
    st = json.load(open(STATE))
    opts = st.get('options', [])
    # 选项定位：1-4 序号 或 作品名片段
    pick = None
    if ans.strip().isdigit() and 1 <= int(ans.strip()) <= len(opts):
        pick = opts[int(ans.strip()) - 1]
    else:
        key = ans.strip()
        for o in opts:
            if key in o or o in key:
                pick = o
                break
    if not pick:
        print('NO_MATCH ans=%s options=%s' % (ans, json.dumps(opts, ensure_ascii=False)))
        return 1

    # 找到该选项对应的 captcha_<md5> 名称
    # ★ 不重新拉页面：showup.php 每次加载都出新题，重拉会让选项名对不上（旧版的坑）。
    #   直接用 --stage3 同一次页面加载里抓到的 name→value 映射。
    name = None
    for nm, val in st.get('pairs', []):
        if val == pick:
            name = nm
            break
    if not name:
        for nm, val in st.get('pairs', []):
            if pick in val or val in pick:
                name = nm
                break
    if not name:
        print('⚠ 未找到该选项的按钮名（题目可能已过期，重跑 --stage3 取新题）'); return 1

    data = {
        '_csrf': st['csrf'], 'message': '签到打卡，感谢分享！',
        'req': st['req'], 'hash': st['hash'], 'form': st['form'],
        name: pick,
    }
    r = op.open(BASE + 'showup.php?action=show', data=urllib.parse.urlencode(data).encode(), timeout=40)
    html2 = r.read().decode('utf-8', 'ignore')
    t = clean(html2)
    cj.save(ignore_discard=True, ignore_expires=True)
    m = re.search(r'(感谢[^。]*。|已签到[^。]*。?|[Uu]Coin[^\d]{0,24}\d+[^。]{0,40}|奖励[^\d]{0,16}\d[^。]{0,20}|回答(?:正确|错误)[^。]*。)', t)
    if m:
        print('① 签到结果: ✅ %s' % m.group(0)[:160])
    elif '已签到' in t:
        print('① 签到结果: ✅ [已签到]')
    else:
        print('① 签到结果: 未见明确标记 →', t[:240])
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    cmd = sys.argv[1]
    if cmd == '--stage1':
        sys.exit(stage1())
    if cmd == '--stage2' and len(sys.argv) > 2:
        sys.exit(stage2(sys.argv[2].strip(), sys.argv[3].strip() if len(sys.argv) > 3 else ''))
    if cmd == '--stage3':
        sys.exit(stage3())
    if cmd == '--stage4' and len(sys.argv) > 2:
        sys.exit(stage4(sys.argv[2].strip()))
    print('参数错误，见文档'); sys.exit(2)
