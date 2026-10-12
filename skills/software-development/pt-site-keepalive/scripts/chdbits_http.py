#!/usr/bin/env python3
"""CHDBits（ptchdbits.co）纯 HTTP 登录 + 答题签到（无浏览器）。无 CF。

  --stage1              取登录验证码 → /tmp/chdbits_captcha.png → CAPTCHA_READY
  --stage2 <验证码>      提交登录 → 账号数据
  --stage3              读 bakatest.php 题目 → QUESTION_READY {questionid, question, options}
  --stage4 <选项文案>    提交答题（SKIP=不会 / CHANGE=换一题 / 其他=匹配选项文案）
                        → 结果（成功判据「连续N天签到,获得X点魔力值」）

cookie：~/.pt-sessions/state/chdbits_cookies.txt
⚠ 选项顺序每次刷新随机、value 只是槽位——必须按「文案归一化精确匹配」，绝不见 value 硬编码。
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
BASE = 'https://ptchdbits.co/'
COOKIES = os.path.expanduser('~/.pt-sessions/state/chdbits_cookies.txt')
STATE = os.path.expanduser('~/.pt-sessions/state/chdbits_state.json')
CAPTCHA_PNG = '/tmp/chdbits_captcha.png'
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
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', referer or BASE + 'login.php')]
    return op


def stage1():
    cj = load_cj()
    op = opener(cj)
    html = op.open(BASE + 'login.php', timeout=40).read().decode('utf-8', 'ignore')
    if ('退出' in html) and ('name="username"' not in html):
        print('① 已是登录态（cookie 有效）——可直接跑 --stage3')
        return 0
    m = re.search(r'name="imagehash"[^>]*value="([^"]+)"', html)
    if not m:
        print('⚠ 未取到 imagehash，登录页结构可能变了'); return 1
    imagehash = m.group(1)
    url = BASE + 'image.php?action=regimage&imagehash=' + urllib.parse.quote(imagehash)
    data = op.open(url, timeout=40).read()
    open(CAPTCHA_PNG, 'wb').write(data)
    json.dump({'imagehash': imagehash}, open(STATE, 'w'))
    cj.save(ignore_discard=True, ignore_expires=True)
    hint = re.search(r'连续\s*(\d+)\s*次登录失败|你还有 ?\[?(\d+)\]?|(\d+)\s*次登录失败', clean(html))
    print('imagehash=%s | 验证码图 %d 字节 → %s' % (imagehash[:12] + '...', len(data), CAPTCHA_PNG))
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
    ok = ('退出' in html or '欢迎回来' in html or '歡迎回來' in html) and 'name="username"' not in html
    print('① 登录: %s (%s)' % ('✅ 成功' if ok else '❌ 失败', r.geturl()))
    if not ok:
        t = clean(html)
        for kw in ('密码', '密碼', '用户名', '用戶名', '验证码', '驗證碼', '尝试', '嘗試', '禁用', '拒绝', '拒絕'):
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
        user, grab(r'分享率[：:]? ?([\d.,]+)'), grab(r'上传量[^\d]{0,12}([\d.,]+ ?[KMGTP]?B)'),
        grab(r'魔力值[^\d]{0,40}([\d,.]+)')))
    return 0


def stage3():
    import time as _t
    cj = load_cj()
    op = opener(cj, BASE + 'bakatest.php')
    html = op.open(BASE + 'bakatest.php', timeout=40).read().decode('utf-8', 'ignore')
    if 'login.php' in html and 'name="username"' in html:
        print('❌ 未登录（cookie 失效）→ 先跑 --stage1/--stage2'); return 2
    t = clean(html)
    if '已经签过到' in t or '已經簽到過' in t:
        print('✅ 今天已经签过到了（多日签到记录里核对连续天数）')
        return 0
    if 'questionid' not in html:
        print('⚠ 页面无答题表单（可能已签完/额度用尽）→', t[:200]); return 0

    form_m = re.search(r'<form[^>]*>(.*?)</form>', html, re.S)
    form = form_m.group(1) if form_m else html
    qid_m = re.search(r'name=[\'"]questionid[\'"][^>]*value=[\'"]([^\'"]+)[\'"]', form)
    qid = qid_m.group(1) if qid_m else ''

    # 题目文字：questionid 输入之前/周围的可见文本
    head = form[:qid_m.start()] if qid_m else ''
    qtext = clean(head)[-500:]

    # 选项：每个 radio 之后的文字直到下一个 radio / <br>
    opts = []
    matches = list(re.finditer(r'<input[^>]*name=[\'"]choice\[\][\'"][^>]*>', form))
    for i, m in enumerate(matches):
        v = re.search(r'value=[\'"]([^\'"]*)[\'"]', m.group(0))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(form), start + 400)
        label = clean(form[start:end])[:120]
        opts.append({'value': v.group(1) if v else '', 'label': label})

    # 按钮 value
    buttons = {}
    for n in ('submit', 'wantchange', 'wantskip'):
        bm = re.search(r'<input[^>]*name=[\'"]%s[\'"][^>]*value=[\'"]([^\'"]*)[\'"]' % n, form)
        if bm:
            buttons[n] = bm.group(1)

    json.dump({'questionid': qid, 'options': opts, 'buttons': buttons}, open(STATE, 'w'), ensure_ascii=False)
    print('QUESTION_READY ' + json.dumps({
        'questionid': qid, 'question': qtext, 'options': opts, 'buttons': buttons,
        'server_time': _t.strftime('%H:%M:%S')}, ensure_ascii=False, indent=1))
    return 0


def stage4(ans):
    cj = load_cj()
    op = opener(cj, BASE + 'bakatest.php')
    st = json.load(open(STATE))
    data = {'questionid': st['questionid']}
    a = ans.strip()
    if a.upper() == 'SKIP':
        data['wantskip'] = st['buttons'].get('wantskip', '不会')
        print('→ 选择「不会」')
    elif a.upper() == 'CHANGE':
        data['wantchange'] = st['buttons'].get('wantchange', '换一题')
        print('→ 选择「换一题」')
    else:
        key = re.sub(r'\s+', '', a)
        hit = None
        for o in st['options']:
            lab = re.sub(r'\s+', '', o['label'])
            if lab == key or (key and key in lab):
                hit = o
                break
        if not hit:
            print('NO_MATCH ans=%s options=%s' % (a, json.dumps(st['options'], ensure_ascii=False)))
            return 1
        data['choice[]'] = hit['value']
        data['submit'] = st['buttons'].get('submit', '提交')
        print('→ 选中: %s (value=%s)' % (hit['label'][:60], hit['value']))

    r = op.open(BASE + 'bakatest.php', data=urllib.parse.urlencode(data).encode(), timeout=40)
    html = r.read().decode('utf-8', 'ignore')
    cj.save(ignore_discard=True, ignore_expires=True)
    t = clean(html)
    m = re.search(r'连续\s*\d+\s*天签到[^。]*。?|獲得[^，。]{0,30}|获得[^，。]{0,30}', t)
    if m:
        print('① 提交结果: ✅ %s' % m.group(0)[:120])
    elif '已经签过到' in t or '已經簽到過' in t:
        print('① 提交结果: ✅ 已签到过（连续记录见页面）')
    else:
        # 出下一题 / 表单消失等
        if 'questionid' in html:
            print('① 提交结果: 页面仍显示答题表单（可能出了下一题或答错重考）→', t[:200])
        else:
            print('① 提交结果: 表单消失（当日额度用尽）→', t[:200])
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
    if cmd == '--stage4' and len(sys.argv) > 2:
        sys.exit(stage4(sys.argv[2].strip()))
    print('参数错误，见文档'); sys.exit(2)
