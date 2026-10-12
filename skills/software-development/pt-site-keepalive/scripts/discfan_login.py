#!/usr/bin/env python3
"""DiscFan（discfan.net）登录 + 签到 —— 纯 Python（urllib），无需浏览器。

两阶段验证码：脚本导出验证码图到 /tmp/discfan_captcha.png 并打印点阵，
然后阻塞等待 /tmp/discfan_captcha_answer.txt 被写入答案。

关键点（踩过的坑）：
  1) response = HMAC_SHA256(key=challenge, msg=sha256(secret + sha256(password)))
     ← 站点 common.js 的 hmacSha256(key,message) 封装会让人把参数写反
  2) 取验证码图必须带图片类 Accept 头，否则验证码必被判「圖片代碼無效」
  3) 验证码错不扣尝试次数（可放心重读）；凭据错才扣（10 次封 IP）

用法：MTEAM_NO_DELAY=1 <venv>/bin/python discfan_login.py
"""
import os, re, sys, json, time, hashlib, hmac, subprocess
import urllib.request, urllib.parse, http.cookiejar

ENV = os.environ.get('MTEAM_ENV', os.path.expanduser('~/.pt-sessions/.env'))
BASE = 'https://discfan.net/'
CJFILE = os.environ.get('DISCFAN_COOKIE',
                        os.path.expanduser('~/.pt-sessions/state/discfan_cookies.txt'))
PNG = '/tmp/discfan_captcha.png'
ANSWER = '/tmp/discfan_captcha_answer.txt'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
IMG_ACCEPT = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
HTML_ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'

def load_env(path):
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

env = load_env(ENV)
USER, PWD = env['MTEAM_USERNAME'], env['MTEAM_PASSWORD']

cj = http.cookiejar.LWPCookieJar(CJFILE)
if os.path.exists(CJFILE):
    try:
        cj.load(ignore_discard=True)
    except Exception:
        pass
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9')]

def get(url, ref=None, accept=None):
    h = {}
    if ref: h['Referer'] = ref
    if accept: h['Accept'] = accept
    return opener.open(urllib.request.Request(url, headers=h), timeout=45).read()

def post(url, data, ref, js=False):
    body = json.dumps(data).encode() if js else urllib.parse.urlencode(data).encode()
    h = {'Referer': ref, 'Origin': BASE.rstrip('/'),
         'Accept': 'application/json, text/javascript, */*; q=0.01' if js else HTML_ACCEPT,
         'Content-Type': 'application/json' if js else 'application/x-www-form-urlencoded'}
    return opener.open(urllib.request.Request(url, data=body, headers=h), timeout=45).read()

def text(b):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', b.decode('utf-8', 'ignore')))

# ---------- 先试已保存的会话 ----------
logged = False
if os.path.exists(CJFILE):
    try:
        if '歡迎回來' in text(get(BASE + 'index.php', accept=HTML_ACCEPT)):
            print('[i] 复用已保存会话成功，跳过登录', flush=True)
            logged = True
    except Exception as e:
        print('[i] 会话复用失败(%s)，重新登录' % type(e).__name__, flush=True)

# ---------- 登录（两阶段验证码） ----------
for rnd in range(1, 5):
    if logged:
        break
    print('===== 登录第 %d 轮 =====' % rnd, flush=True)
    html = get(BASE + 'login.php', accept=HTML_ACCEPT).decode('utf-8', 'ignore')
    m = re.search(r'name=["\']imagehash["\'][^>]*value=["\']([a-f0-9]{32})["\']', html)
    if not m:
        print('  !! 未拿到 imagehash，退出'); sys.exit(1)
    IH = m.group(1)
    raw = get(BASE + 'image.php?action=regimage&imagehash=%s&secret=' % IH,
              ref=BASE + 'login.php', accept=IMG_ACCEPT)
    open(PNG, 'wb').write(raw)
    if os.path.exists(ANSWER):
        os.remove(ANSWER)
    subprocess.run(['/usr/bin/python3', '-c', '''
from PIL import Image
import numpy as np
im = Image.open("%s").convert("RGB")
w, h = im.size
d = np.array(im.convert("L")).astype(int) < 100
d[:, 0] = False; d[:, 1] = False; d[:, w-1] = False; d[:, w-2] = False
cols = d.sum(axis=0); strong = cols >= 3
runs, inrun = [], None
for x in range(w):
    if strong[x] and inrun is None: inrun = x
    elif not strong[x] and inrun is not None:
        runs.append((inrun, x)); inrun = None
if inrun is not None: runs.append((inrun, w))
merged = []
for r in runs:
    if merged and r[0] - merged[-1][1] < 4: merged[-1] = (merged[-1][0], r[1])
    else: merged.append(r)
print("字符分段:", merged)
for i, (a, b) in enumerate(merged):
    x0, x1 = max(0, a-2), min(w, b+2)
    print("--- 字符 %%d (列 %%d-%%d) ---" %% (i+1, a, b))
    for y in range(10, 27):
        seg = "".join("#" if d[y, x] else "." for x in range(x0, x1))
        if seg.count("#") >= 1: print("   " + seg)
''' % PNG], timeout=90)
    print('CAPTCHA_READY → %s ；把答案写入 %s' % (PNG, ANSWER), flush=True)

    t0, code = time.time(), None
    while time.time() - t0 < 420:
        if os.path.exists(ANSWER):
            code = open(ANSWER).read().strip()
            if code: break
        time.sleep(0.15)
    if not code:
        print('  !! 等答案超时'); sys.exit(1)

    cd = json.loads(post(BASE + 'api/challenge', {'username': USER}, BASE + 'login.php', js=True).decode())
    if cd.get('ret') != 0:
        print('  !! challenge 失败:', cd.get('msg')); sys.exit(1)
    ch, sec = str(cd['data']['challenge']), str(cd['data']['secret'])
    chp = hashlib.sha256(PWD.encode()).hexdigest()
    ssh_ = hashlib.sha256((sec + chp).encode()).hexdigest()
    resp = hmac.new(ch.encode(), ssh_.encode(), hashlib.sha256).hexdigest()   # key=challenge

    body = post(BASE + 'takelogin.php',
                {'secret': '', 'username': USER, 'two_step_code': '', 'imagestring': code,
                 'imagehash': IH, 'response': resp}, BASE + 'login.php')
    p = text(body)
    if '圖片代碼' in p:
        print('  验证码无效（不扣次数）→ 换图重试', flush=True); continue
    if '歡迎回來' in p or '退出' in p:
        logged = True
        cj.save(ignore_discard=True)
        print('  登录成功（第 %d 轮），会话已存 %s' % (rnd, CJFILE), flush=True)
        break
    print('  登录失败:', p[:220], flush=True)
    break

if not logged:
    print('!! 未能登录'); sys.exit(1)

# ---------- 签到（打开即签） ----------
print('\n===== 签到 =====', flush=True)
at = text(get(BASE + 'attendance.php', ref=BASE + 'index.php', accept=HTML_ACCEPT))
i = at.find('簽到成功')
if i >= 0:
    print('  ' + at[i:i+200], flush=True)
else:
    j = at.find('簽到')
    print('  未检出「簽到成功」，页面片段:', at[max(0, j-60):j+180] if j >= 0 else at[:200], flush=True)

idx = text(get(BASE + 'index.php', accept=HTML_ACCEPT))
k = idx.find('歡迎回來')
print('\n用户栏: ' + idx[k:k+200], flush=True)
cj.save(ignore_discard=True)
